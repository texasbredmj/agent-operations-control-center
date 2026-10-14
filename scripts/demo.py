"""Exercise real HTTP, worker processing, authorization and durable evidence."""

import json
import os
import time
import uuid
from pathlib import Path

import httpx
from local_env import configure

rows = configure()
keys = {r["role"]: r["token"] for r in rows}
origin = os.environ.get("OPS_ORIGIN", "http://127.0.0.1:18780")
client = httpx.Client(base_url=origin, timeout=10)
results = []


def request(method, path, role="operator", expected=200, **kwargs):
    headers = {"Authorization": "Bearer " + keys[role]}
    if method == "POST":
        headers["Idempotency-Key"] = str(uuid.uuid4())
    response = client.request(method, path, headers=headers, **kwargs)
    assert response.status_code == expected, (path, response.status_code, response.text)
    return response.json()


def create(mode, title):
    return request(
        "POST", "/api/tasks", expected=201, json={"title": title, "mode": mode, "quantity": 2}
    )


def wait(task, state):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        detail = request("GET", "/api/tasks/" + task["id"], "viewer")
        if detail["task"]["state"] == state:
            return detail
        time.sleep(0.2)
    raise AssertionError("worker did not reach " + state)


def act(task, action, role="operator", expected=200):
    return request(
        "POST",
        f"/api/tasks/{task['id']}/{action}",
        role,
        expected,
        json={"version": task["version"], "reason": "Reviewed in deterministic HTTP demo"},
    )


def record(scenario, detail):
    results.append(
        {
            "scenario": scenario,
            "passed": True,
            "task_id": detail["task"]["id"],
            "state": detail["task"]["state"],
            "attempts": detail["task"]["attempts"],
            "verified": bool(detail["evidence"] and detail["evidence"]["verified"]),
            "tool_calls": len(detail["tool_calls"]),
            "trace_id": detail["task"]["trace_id"],
        }
    )


assert client.get("/api/tasks").status_code == 401
normal = create("normal", "Verify inventory reservation")
done = wait(normal, "SUCCEEDED")
assert done["evidence"]["verified"] and done["evidence"]["details"]["observed_quantity"] == 2
assert {s["trace_id"] for s in done["spans"]} == {normal["trace_id"]}
record("verified_completion", done)
approval = create("approval", "Approve a controlled reservation")
act(approval, "approve", "operator", 403)
act(approval, "approve", "viewer", 403)
act(approval, "approve", "approver")
record("separate_approval", wait(approval, "SUCCEEDED"))
rejected = create("approval", "Reject an unnecessary reservation")
act(rejected, "reject", "approver")
record("rejection", wait(rejected, "REJECTED"))
cancelled = create("approval", "Cancel pending maintenance")
act(cancelled, "cancel")
record("cancellation", wait(cancelled, "CANCELLED"))
transient = create("transient", "Recover a temporary dependency failure")
failed = wait(transient, "FAILED")["task"]
act(failed, "retry", "viewer", 403)
act(failed, "retry")
retried = wait(transient, "SUCCEEDED")
assert retried["task"]["attempts"] == 2
record("eligible_retry", retried)
permanent = create("permanent", "Investigate a permanent dependency failure")
failed = wait(permanent, "FAILED")
act(failed["task"], "retry", expected=409)
record("permanent_failure", failed)
unverified = create("unverified", "Investigate a receipt mismatch")
mismatch = wait(unverified, "FAILED")
assert not mismatch["evidence"]["verified"] and mismatch["evidence"]["details"]["claimed_completed"]
act(mismatch["task"], "retry", expected=409)
record("verification_mismatch", mismatch)
# Leave a real pending item so the operations dashboard has an actionable approval view.
pending = create("approval", "Review next inventory allocation")
record("pending_approval", wait(pending, "PENDING_APPROVAL"))
overview = request("GET", "/api/overview", "viewer")
assert overview["agents"] and overview["agents"][0]["online"]
assert overview["usage"]["cost_nusd"] == 0
out = Path(".gates")
out.mkdir(exist_ok=True)
summary = {
    "verified_demo": True,
    "scenario_count": len(results),
    "results": results,
    "overview": overview,
    "paid_model_calls": 0,
    "unauthenticated_read_rejected": True,
    "direct_unauthorized_controls_rejected": True,
}
(out / "http-demo.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"verified_demo": True, "scenarios": len(results), "paid_model_calls": 0}))
