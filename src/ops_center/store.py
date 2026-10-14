import hashlib
import json
import uuid
from contextlib import contextmanager

import psycopg
from fastapi.encoders import jsonable_encoder
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def public_task(row):
    return {k: v for k, v in row.items() if k not in {"claim", "lease_until"}}


class Store:
    def __init__(self, settings):
        self.settings = settings

    @contextmanager
    def connect(self):
        with psycopg.connect(
            self.settings.database_url, row_factory=dict_row, connect_timeout=5
        ) as db:
            db.execute(
                sql.SQL("SET search_path TO {}").format(sql.Identifier(self.settings.schema))
            )
            db.execute("SET statement_timeout = '5s'")
            yield db

    def initialize(self):
        from importlib.resources import files

        with self.connect() as db:
            db.execute(files("ops_center").joinpath("schema.sql").read_text(encoding="utf-8"))

    @staticmethod
    def event(db, task_id, kind, actor, details):
        db.execute(
            "INSERT INTO events(task_id,kind,actor,details) VALUES(%s,%s,%s,%s)",
            (task_id, kind, actor, Jsonb(details)),
        )

    @staticmethod
    def task(db, task_id, project, lock=False):
        query = "SELECT * FROM tasks WHERE id=%s AND project=%s" + (" FOR UPDATE" if lock else "")
        return db.execute(query, (task_id, project)).fetchone()

    def create(self, principal, body, key):
        from fastapi import HTTPException

        payload = body.model_dump()
        hashed = fingerprint({"create": payload})
        with self.connect() as db:
            # Serialize a project's idempotency key even before the task row exists.
            db.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (principal.project + str(key),),
            )
            previous = self.replay(db, principal, key, hashed)
            if previous:
                return previous
            db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,1))", (principal.project,))
            count = db.execute(
                "SELECT count(*) AS n FROM tasks WHERE project=%s", (principal.project,)
            ).fetchone()["n"]
            if count >= 1000:
                raise HTTPException(409, "fixture project capacity reached")
            task_id = uuid.uuid4()
            state = "PENDING_APPROVAL" if body.mode == "approval" else "QUEUED"
            row = db.execute(
                "INSERT INTO tasks(id,project,title,mode,state,requested_by,quantity,trace_id) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                (
                    task_id,
                    principal.project,
                    body.title,
                    body.mode,
                    state,
                    principal.name,
                    body.quantity,
                    uuid.uuid4().hex,
                ),
            ).fetchone()
            self.event(
                db, task_id, "CREATED", principal.name, {"state": state, "quantity": body.quantity}
            )
            db.execute(
                "INSERT INTO spans(span_id,task_id,trace_id,name,duration_ms,attributes) VALUES(%s,%s,%s,'task.created',0,%s)",
                (task_id.hex[:16], task_id, row["trace_id"], Jsonb({"task.state": state})),
            )
            if state == "PENDING_APPROVAL":
                db.execute(
                    "INSERT INTO approvals(task_id,action_sha256,state) VALUES(%s,%s,'PENDING')",
                    (
                        task_id,
                        fingerprint(
                            {
                                "task_id": str(task_id),
                                "quantity": body.quantity,
                                "tool": "inventory.reserve",
                            }
                        ),
                    ),
                )
            result = public_task(row)
            self.remember(db, principal, key, hashed, result)
            return result

    @staticmethod
    def replay(db, principal, key, hashed):
        from fastapi import HTTPException

        row = db.execute(
            "SELECT * FROM commands WHERE project=%s AND key=%s", (principal.project, key)
        ).fetchone()
        if row:
            if row["actor"] != principal.name or row["request_hash"] != hashed:
                raise HTTPException(409, "idempotency key is bound to a different request")
            return row["response"]

    @staticmethod
    def remember(db, principal, key, hashed, result):
        # JSON encoding converts UUID/timestamps for exact response replay.
        value = jsonable_encoder(result)
        db.execute(
            "INSERT INTO commands(project,key,actor,request_hash,response) VALUES(%s,%s,%s,%s,%s)",
            (principal.project, key, principal.name, hashed, Jsonb(value)),
        )

    def control(self, principal, task_id, action, body, key):
        from fastapi import HTTPException

        hashed = fingerprint({"task_id": str(task_id), "action": action, **body.model_dump()})
        with self.connect() as db:
            db.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (principal.project + str(key),),
            )
            row = self.task(db, task_id, principal.project, True)
            if not row:
                raise HTTPException(404, "task not found")
            previous = self.replay(db, principal, key, hashed)
            if previous:
                return previous
            if row["version"] != body.version:
                raise HTTPException(409, "task changed; refresh before acting")
            if action in {"approve", "reject"}:
                if row["state"] != "PENDING_APPROVAL" or row["requested_by"] == principal.name:
                    raise HTTPException(409, "approval is not eligible")
                expected = fingerprint(
                    {
                        "task_id": str(task_id),
                        "quantity": row["quantity"],
                        "tool": "inventory.reserve",
                    }
                )
                approval = db.execute(
                    "SELECT * FROM approvals WHERE task_id=%s FOR UPDATE", (task_id,)
                ).fetchone()
                if (
                    not approval
                    or approval["state"] != "PENDING"
                    or approval["action_sha256"] != expected
                ):
                    raise HTTPException(409, "approval does not match the pending action")
                state = "QUEUED" if action == "approve" else "REJECTED"
                decision = "APPROVED" if action == "approve" else "REJECTED"
                db.execute(
                    "UPDATE approvals SET state=%s,decided_by=%s,reason=%s,decided_at=now() WHERE task_id=%s",
                    (decision, principal.name, body.reason, task_id),
                )
            elif action == "cancel":
                if row["state"] not in {"QUEUED", "RUNNING", "PENDING_APPROVAL"}:
                    raise HTTPException(409, "task is already terminal")
                state = "CANCELLED"
                db.execute(
                    "UPDATE approvals SET state='CANCELLED',decided_by=%s,reason=%s,decided_at=now() WHERE task_id=%s AND state='PENDING'",
                    (principal.name, body.reason, task_id),
                )
            else:
                if (
                    row["state"] != "FAILED"
                    or not row["retryable"]
                    or row["attempts"] >= row["max_attempts"]
                ):
                    raise HTTPException(409, "failure is not eligible for retry")
                state = "QUEUED"
            updated = db.execute(
                "UPDATE tasks SET state=%s,version=version+1,retryable=false,error=NULL,claim=NULL,lease_until=NULL,updated_at=now() WHERE id=%s RETURNING *",
                (state, task_id),
            ).fetchone()
            self.event(
                db,
                task_id,
                action.upper(),
                principal.name,
                {"reason": body.reason, "from": row["state"], "to": state},
            )
            result = public_task(updated)
            self.remember(db, principal, key, hashed, result)
            return result
