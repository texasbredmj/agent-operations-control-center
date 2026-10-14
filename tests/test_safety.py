import uuid

from conftest import control, create, detail

from ops_center.worker import Worker


def test_terminal_completion_cannot_be_cancelled(rig):
    task = create(rig).json()
    Worker(rig[1]).tick()
    completed = detail(rig, task).json()["task"]
    assert control(rig, completed, "cancel").status_code == 409
    assert detail(rig, task).json()["evidence"]["verified"]


def test_viewer_cannot_bypass_ui_controls(rig):
    task = create(rig, "approval").json()
    for action in ("approve", "reject", "cancel", "retry"):
        assert control(rig, task, action, "viewer").status_code == 403
    assert detail(rig, task).json()["task"]["state"] == "PENDING_APPROVAL"


def test_attempt_limit_and_stale_heartbeat_are_enforced(rig):
    task = create(rig, "transient").json()
    Worker(rig[1]).tick()
    with rig[1].connect() as db:
        db.execute("UPDATE tasks SET attempts=max_attempts WHERE id=%s", (task["id"],))
        db.execute("UPDATE agents SET heartbeat=now()-interval '10 seconds'")
    assert control(rig, detail(rig, task).json()["task"], "retry").status_code == 409
    overview = rig[0].get("/api/overview", headers=rig[2]["viewer"]).json()
    assert overview["agents"] and not overview["agents"][0]["online"]


def test_active_filter_is_applied_before_pagination(rig):
    active = create(rig).json()
    pending = create(rig, "approval").json()
    response = rig[0].get("/api/tasks?state=ACTIVE&limit=1", headers=rig[2]["viewer"])
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == active["id"]
    assert response.json()["items"][0]["id"] != pending["id"]


def test_mutations_require_uuid_key_and_bounded_reason(rig):
    task = create(rig, "approval").json()
    client, _, headers = rig
    path = "/api/tasks/" + task["id"] + "/cancel"
    assert (
        client.post(
            path, headers=headers["operator"], json={"version": 1, "reason": "Reviewed"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            path,
            headers={**headers["operator"], "Idempotency-Key": str(uuid.uuid4())},
            json={"version": 1, "reason": " "},
        ).status_code
        == 422
    )


def test_cancelling_pending_approval_invalidates_the_decision(rig):
    task = create(rig, "approval").json()
    cancelled = control(rig, task, "cancel").json()
    assert control(rig, cancelled, "approve", "approver").status_code == 409
    assert detail(rig, task).json()["approval"]["state"] == "CANCELLED"
