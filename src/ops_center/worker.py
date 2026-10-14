import argparse
import time
import uuid

import psutil
from psycopg.types.json import Jsonb

from .config import Settings
from .store import Store
from .telemetry import telemetry


class Worker:
    def __init__(self, store, worker_id="fixture-worker", lease_seconds=10):
        self.store = store
        self.id = worker_id
        self.lease_seconds = lease_seconds

    def heartbeat(self):
        process = psutil.Process()
        cpu = process.cpu_times()
        with self.store.connect() as db:
            db.execute(
                "INSERT INTO agents(id,heartbeat,rss_bytes,cpu_seconds) VALUES(%s,now(),%s,%s) "
                "ON CONFLICT(id) DO UPDATE SET heartbeat=now(),rss_bytes=excluded.rss_bytes,cpu_seconds=excluded.cpu_seconds",
                (self.id, process.memory_info().rss, cpu.user + cpu.system),
            )

    def claim(self):
        with self.store.connect() as db:
            # Expired claims may be recovered; no external side effect is replayed.
            stale = db.execute(
                "SELECT * FROM tasks WHERE state='RUNNING' AND lease_until<now() FOR UPDATE SKIP LOCKED"
            ).fetchall()
            for task in stale:
                retry = task["attempts"] < task["max_attempts"]
                db.execute(
                    "UPDATE tasks SET state=%s,retryable=false,claim=NULL,lease_until=NULL,version=version+1,error=%s,updated_at=now() WHERE id=%s",
                    ("QUEUED" if retry else "FAILED", "worker lease expired", task["id"]),
                )
                self.store.event(db, task["id"], "LEASE_EXPIRED", self.id, {"requeued": retry})
            task = db.execute(
                "SELECT * FROM tasks WHERE state='QUEUED' AND attempts<max_attempts ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"
            ).fetchone()
            if not task:
                return None
            claim = uuid.uuid4()
            task = db.execute(
                "UPDATE tasks SET state='RUNNING',attempts=attempts+1,version=version+1,claim=%s,lease_until=now()+(%s * interval '1 second'),updated_at=now() WHERE id=%s RETURNING *",
                (claim, self.lease_seconds, task["id"]),
            ).fetchone()
            self.store.event(db, task["id"], "CLAIMED", self.id, {"attempt": task["attempts"]})
            return task

    def finish(self, claimed):
        with self.store.connect() as db:
            task = db.execute(
                "SELECT * FROM tasks WHERE id=%s FOR UPDATE", (claimed["id"],)
            ).fetchone()
            if task["state"] != "RUNNING" or task["claim"] != claimed["claim"]:
                return False
            # Expired worker cannot commit even before a replacement has reclaimed it.
            if (
                db.execute(
                    "SELECT lease_until>now() AS valid FROM tasks WHERE id=%s", (task["id"],)
                ).fetchone()["valid"]
                is not True
            ):
                return False
            provider, collector, context = telemetry(task)
            tracer = provider.get_tracer("ops_center.worker", "0.1.0")
            try:
                started = time.perf_counter()
                failed = task["mode"] == "permanent" or (
                    task["mode"] == "transient" and task["attempts"] == 1
                )
                with tracer.start_as_current_span("inventory.reserve", context=context) as span:
                    if failed:
                        tool_state, details = (
                            "FAILED",
                            {
                                "error": "permanent fixture failure"
                                if task["mode"] == "permanent"
                                else "temporary fixture failure"
                            },
                        )
                    else:
                        quantity = task["quantity"] + (1 if task["mode"] == "unverified" else 0)
                        db.execute(
                            "INSERT INTO effects(task_id,quantity,receipt) VALUES(%s,%s,%s) ON CONFLICT(task_id) DO NOTHING",
                            (task["id"], quantity, uuid.uuid4()),
                        )
                        tool_state, details = "SUCCEEDED", {"claimed_completed": True}
                    span.set_attribute("tool.state", tool_state)
                    span.set_attribute("task.attempt", task["attempts"])
                duration = (time.perf_counter() - started) * 1000
                db.execute(
                    "INSERT INTO tool_calls(task_id,attempt,tool,state,duration_ms,details) VALUES(%s,%s,'inventory.reserve',%s,%s,%s)",
                    (task["id"], task["attempts"], tool_state, duration, Jsonb(details)),
                )
                if failed:
                    verified = False
                    state = "FAILED"
                    retryable = (
                        task["mode"] == "transient" and task["attempts"] < task["max_attempts"]
                    )
                    error = details["error"]
                else:
                    with tracer.start_as_current_span("task.verify", context=context) as span:
                        receipt = db.execute(
                            "SELECT * FROM effects WHERE task_id=%s", (task["id"],)
                        ).fetchone()
                        verified = receipt is not None and receipt["quantity"] == task["quantity"]
                        verification = {
                            "expected_quantity": task["quantity"],
                            "observed_quantity": receipt["quantity"] if receipt else None,
                            "receipt": str(receipt["receipt"]) if receipt else None,
                            "method": "independent ledger read",
                            "claimed_completed": True,
                        }
                        span.set_attribute("verification.passed", verified)
                        db.execute(
                            "INSERT INTO evidence(task_id,verified,details) VALUES(%s,%s,%s) "
                            "ON CONFLICT(task_id) DO UPDATE SET verified=excluded.verified,details=excluded.details,at=now()",
                            (task["id"], verified, Jsonb(verification)),
                        )
                    state, retryable, error = (
                        ("SUCCEEDED", False, None)
                        if verified
                        else (
                            "FAILED",
                            False,
                            "verification mismatch; manual investigation required",
                        )
                    )
                db.execute(
                    "UPDATE tasks SET state=%s,retryable=%s,error=%s,version=version+1,claim=NULL,lease_until=NULL,updated_at=now() WHERE id=%s",
                    (state, retryable, error, task["id"]),
                )
                self.store.event(
                    db, task["id"], state, self.id, {"verified": verified, "retryable": retryable}
                )
                db.execute("UPDATE agents SET processed=processed+1 WHERE id=%s", (self.id,))
            finally:
                provider.shutdown()
            for span in collector.rows:
                db.execute(
                    "INSERT INTO spans(span_id,task_id,trace_id,parent_span_id,name,duration_ms,attributes) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    (
                        span["span_id"],
                        task["id"],
                        span["trace_id"],
                        span["parent_span_id"],
                        span["name"],
                        span["duration_ms"],
                        Jsonb(span["attributes"]),
                    ),
                )
            return True

    def tick(self):
        self.heartbeat()
        task = self.claim()
        return self.finish(task) if task else False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    store = Store(Settings())
    store.initialize()
    worker = Worker(store)
    while True:
        worker.heartbeat()
        task = worker.claim()
        if task:
            time.sleep(1)  # A cancellation window between claim and transactional effect.
            worker.finish(task)
        if args.once:
            break
        time.sleep(0.5)


if __name__ == "__main__":
    main()
