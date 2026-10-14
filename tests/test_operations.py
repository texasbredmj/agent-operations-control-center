import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import control, create, detail

from ops_center.worker import Worker


def test_all_operational_reads_require_auth(rig):
    client, _, _ = rig
    task = create(rig).json()
    for path in ["/api/me", "/api/tasks", "/api/overview", "/api/tasks/" + task["id"]]:
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert client.get("/healthz").json() == {"ready": True}


@pytest.mark.parametrize("role", ["viewer", "approver"])
def test_only_operator_can_create(rig, role):
    assert create(rig, role=role).status_code == 403


def test_verified_completion_has_actual_receipt_and_trace(rig):
    task = create(rig).json()
    assert Worker(rig[1]).tick()
    record = detail(rig, task).json()
    assert record["task"]["state"] == "SUCCEEDED"
    assert record["evidence"]["verified"]
    assert record["evidence"]["details"]["observed_quantity"] == 2
    assert record["tool_calls"][0]["state"] == "SUCCEEDED"
    assert {s["trace_id"] for s in record["spans"]} == {task["trace_id"]}
    assert {s["name"] for s in record["spans"]} == {
        "task.created",
        "inventory.reserve",
        "task.verify",
    }
    assert all(s["parent_span_id"] == record["spans"][0]["span_id"] for s in record["spans"][1:])
    with rig[1].connect() as db:
        effect = db.execute("SELECT * FROM effects WHERE task_id=%s", (task["id"],)).fetchone()
    assert record["evidence"]["details"]["receipt"] == str(effect["receipt"])


def test_approval_requires_separate_role_and_exact_pending_action(rig):
    task = create(rig, "approval").json()
    assert not Worker(rig[1]).tick()
    assert control(rig, task, "approve", "operator").status_code == 403
    assert control(rig, task, "approve", "viewer").status_code == 403
    assert control(rig, task, "cancel", "approver").status_code == 403
    approved = control(rig, task, "approve", "approver")
    assert approved.status_code == 200
    assert Worker(rig[1]).tick()
    assert detail(rig, task).json()["task"]["state"] == "SUCCEEDED"
    assert control(rig, approved.json(), "reject", "approver").status_code == 409


def test_rejection_is_terminal_and_has_no_effect(rig):
    task = create(rig, "approval").json()
    assert control(rig, task, "reject", "approver").json()["state"] == "REJECTED"
    assert not Worker(rig[1]).tick()
    assert not detail(rig, task).json()["tool_calls"]


def test_cancel_running_task_prevents_claimed_worker_effect(rig):
    task = create(rig).json()
    worker = Worker(rig[1])
    claimed = worker.claim()
    running = detail(rig, task).json()["task"]
    assert running["state"] == "RUNNING"
    assert control(rig, running, "cancel").json()["state"] == "CANCELLED"
    assert not worker.finish(claimed)
    with rig[1].connect() as db:
        assert db.execute("SELECT count(*) AS n FROM effects").fetchone()["n"] == 0


def test_eligible_retry_succeeds_once_and_replay_does_not_duplicate(rig):
    task = create(rig, "transient").json()
    worker = Worker(rig[1])
    worker.tick()
    failed = detail(rig, task).json()["task"]
    assert failed["state"] == "FAILED" and failed["retryable"]
    key = str(uuid.uuid4())
    first = control(rig, failed, "retry", key=key)
    second = control(rig, failed, "retry", key=key)
    assert first.json() == second.json()
    assert worker.tick() and not worker.tick()
    record = detail(rig, task).json()
    assert record["task"]["state"] == "SUCCEEDED" and record["task"]["attempts"] == 2
    assert len(record["tool_calls"]) == 2
    assert sum(h["kind"] == "RETRY" for h in record["history"]) == 1
    with rig[1].connect() as db:
        assert db.execute("SELECT count(*) AS n FROM effects").fetchone()["n"] == 1


@pytest.mark.parametrize("mode", ["permanent", "unverified"])
def test_unsafe_failures_cannot_be_retried(rig, mode):
    task = create(rig, mode).json()
    Worker(rig[1]).tick()
    record = detail(rig, task).json()
    assert record["task"]["state"] == "FAILED" and not record["task"]["retryable"]
    assert control(rig, record["task"], "retry").status_code == 409
    if mode == "unverified":
        assert not record["evidence"]["verified"]
        assert record["evidence"]["details"]["claimed_completed"]


def test_project_scope_hides_reads_controls_and_totals(rig):
    task = create(rig, "approval").json()
    assert detail(rig, task, "outsider").status_code == 404
    assert control(rig, task, "cancel", "outsider").status_code == 404
    client, _, headers = rig
    assert client.get("/api/tasks", headers=headers["outsider"]).json()["total"] == 0
    overview = client.get("/api/overview", headers=headers["outsider"]).json()
    assert overview["counts"] == {} and overview["usage"]["tool_calls"] == 0


def test_stale_versions_and_rebound_idempotency_keys_rejected(rig):
    task = create(rig, "approval").json()
    key = str(uuid.uuid4())
    assert control(rig, task, "approve", "approver", key).status_code == 200
    assert control(rig, task, "reject", "approver", key).status_code == 409
    assert control(rig, task, "cancel").status_code == 409


def test_duplicate_submission_is_one_durable_task(rig):
    client, store, headers = rig
    key = str(uuid.uuid4())
    body = {"title": "One task"}
    first = client.post(
        "/api/tasks", headers={**headers["operator"], "Idempotency-Key": key}, json=body
    )
    second = client.post(
        "/api/tasks", headers={**headers["operator"], "Idempotency-Key": key}, json=body
    )
    assert first.json() == second.json()
    with store.connect() as db:
        assert db.execute("SELECT count(*) AS n FROM tasks").fetchone()["n"] == 1
    assert (
        client.post(
            "/api/tasks",
            headers={**headers["operator"], "Idempotency-Key": key},
            json={"title": "Different"},
        ).status_code
        == 409
    )


def test_concurrent_approval_and_rejection_have_one_winner(rig):
    task = create(rig, "approval").json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda action: control(rig, task, action, "approver").status_code,
                ["approve", "reject"],
            )
        )
    assert sorted(responses) == [200, 409]
    history = detail(rig, task).json()["history"]
    assert sum(h["kind"] in {"APPROVE", "REJECT"} for h in history) == 1


def test_two_workers_cannot_claim_same_task(rig):
    create(rig)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda n: Worker(rig[1], str(n)).claim(), range(2)))
    assert sum(c is not None for c in claims) == 1


def test_expired_claim_is_fenced_and_recovered(rig):
    task = create(rig).json()
    worker = Worker(rig[1])
    old = worker.claim()
    with rig[1].connect() as db:
        db.execute(
            "UPDATE tasks SET lease_until=now()-interval '1 second' WHERE id=%s", (task["id"],)
        )
    assert not worker.finish(old)
    replacement = Worker(rig[1], "replacement")
    new = replacement.claim()
    assert new["id"] == old["id"] and new["claim"] != old["claim"]
    assert not worker.finish(old) and replacement.finish(new)
    assert detail(rig, task).json()["task"]["attempts"] == 2


def test_metrics_are_derived_from_committed_outcomes(rig):
    create(rig)
    create(rig, "permanent")
    worker = Worker(rig[1])
    worker.tick()
    worker.tick()
    overview = rig[0].get("/api/overview", headers=rig[2]["viewer"]).json()
    assert overview["counts"]["SUCCEEDED"] == overview["counts"]["FAILED"] == 1
    assert overview["reliability"]["verified_success_rate"] == 0.5
    assert overview["verification"] == {"checked": 1, "passed": 1}
    assert overview["usage"]["tool_calls"] == 2 and overview["usage"]["cost_nusd"] == 0
    assert overview["agents"][0]["rss_bytes"] > 0


def test_action_tampering_blocks_approval(rig):
    task = create(rig, "approval").json()
    with rig[1].connect() as db:
        db.execute("UPDATE tasks SET quantity=3 WHERE id=%s", (task["id"],))
    assert control(rig, task, "approve", "approver").status_code == 409
