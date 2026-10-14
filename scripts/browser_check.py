"""Real Chromium interactions against the built dashboard and live backend."""

import json
import os
import time
import uuid
from pathlib import Path

import httpx
from local_env import local_env
from playwright.sync_api import expect, sync_playwright

rows = json.loads(local_env()["OPS_CREDENTIALS"])
keys = {r["role"]: r["token"] for r in rows}
origin = os.environ.get("OPS_ORIGIN", "http://127.0.0.1:18780")
out = Path(".gates")
out.mkdir(exist_ok=True)
client = httpx.Client(base_url=origin, timeout=10)
results = []
errors = []


def api(method, path, role="operator", body=None):
    response = client.request(
        method,
        path,
        headers={"Authorization": "Bearer " + keys[role], "Idempotency-Key": str(uuid.uuid4())},
        json=body,
    )
    assert response.is_success, (path, response.status_code)
    return response.json()


def wait_state(task_id, state):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        value = api("GET", "/api/tasks/" + task_id, "viewer")
        if value["task"]["state"] == state:
            return value
        time.sleep(0.2)
    raise AssertionError("expected " + state)


def login(page, role):
    page.goto(origin)
    page.get_by_label("Access token").fill(keys[role])
    page.get_by_role("button", name="Connect to operations").click()
    expect(page.get_by_role("heading", name="Execution overview")).to_be_visible()


def open_task(page, title):
    page.get_by_role("button", name=title, exact=True).click()
    expect(
        page.get_by_role("region", name="Task inspector").get_by_role("heading", name=title)
    ).to_be_visible()


def decide(page, action):
    page.get_by_role("button", name=action + " task", exact=True).click()
    page.get_by_label("Reason", exact=True).fill("Reviewed through real Chromium operator flow")
    page.get_by_role("button", name="Confirm " + action.lower(), exact=True).click()
    expect(page.get_by_role("dialog")).not_to_be_visible()


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(origin)
    page.get_by_label("Access token").fill("invalid-credential")
    page.get_by_role("button", name="Connect to operations").click()
    expect(page.get_by_role("alert")).to_contain_text("valid bearer credential required")
    results.append({"scenario": "invalid_login_rejected", "passed": True})
    login(page, "operator")
    title = "Browser reservation " + uuid.uuid4().hex[:6]
    page.get_by_role("button", name="+ New task").click()
    page.get_by_label("Task title").fill(title)
    page.get_by_label("Units to reserve").fill("3")
    page.get_by_role("button", name="Submit task").click()
    expect(page.get_by_role("dialog")).not_to_be_visible()
    expect(page.get_by_text("Verified receipt", exact=False)).to_be_visible(timeout=20000)
    results.append({"scenario": "create_and_inspect_verified_task", "passed": True})
    page.get_by_role("tab", name="Workflow", exact=True).click()
    expect(page.get_by_text("claimed", exact=True)).to_be_visible()
    page.get_by_role("tab", name="Tools", exact=True).click()
    expect(page.get_by_text("inventory.reserve", exact=True)).to_be_visible()
    page.get_by_role("tab", name="Traces", exact=True).click()
    expect(page.get_by_text("↳ task.verify", exact=True)).to_be_visible()
    results.append({"scenario": "inspect_workflow_tools_and_real_spans", "passed": True})
    # Cancellation stays pending until controlled, so worker timing cannot make this ambiguous.
    title_cancel = "Browser cancellation " + uuid.uuid4().hex[:6]
    cancelled = api("POST", "/api/tasks", body={"title": title_cancel, "mode": "approval"})
    page.get_by_role("button", name="Pending approvals", exact=False).click()
    open_task(page, title_cancel)
    decide(page, "Cancel")
    wait_state(cancelled["id"], "CANCELLED")
    results.append({"scenario": "cancel_from_dashboard", "passed": True})
    title_retry = "Browser retry " + uuid.uuid4().hex[:6]
    retried = api("POST", "/api/tasks", body={"title": title_retry, "mode": "transient"})
    wait_state(retried["id"], "FAILED")
    page.get_by_role("button", name="Failed tasks", exact=False).click()
    open_task(page, title_retry)
    decide(page, "Retry")
    assert wait_state(retried["id"], "SUCCEEDED")["task"]["attempts"] == 2
    results.append({"scenario": "retry_eligible_failure_from_dashboard", "passed": True})
    approval_title = "Browser approval " + uuid.uuid4().hex[:6]
    approval = api("POST", "/api/tasks", body={"title": approval_title, "mode": "approval"})
    rejection_title = "Browser rejection " + uuid.uuid4().hex[:6]
    rejection = api("POST", "/api/tasks", body={"title": rejection_title, "mode": "approval"})
    page.get_by_role("button", name="Sign out", exact=True).click()
    login(page, "approver")
    page.get_by_role("button", name="Pending approvals", exact=False).click()
    open_task(page, approval_title)
    decide(page, "Approve")
    wait_state(approval["id"], "SUCCEEDED")
    open_task(page, rejection_title)
    decide(page, "Reject")
    wait_state(rejection["id"], "REJECTED")
    results.append({"scenario": "approve_and_reject_from_dashboard", "passed": True})
    page.get_by_role("button", name="Sign out", exact=True).click()
    login(page, "viewer")
    expect(page.get_by_role("button", name="+ New task")).not_to_be_visible()
    for name in [
        "Active tasks",
        "Completed tasks",
        "Failed tasks",
        "Pending approvals",
        "Workflow history",
        "Tool-call history",
        "Execution traces",
        "Reliability metrics",
        "Resource usage",
        "Cost reports",
        "Agent status",
    ]:
        page.get_by_role("button", name=name, exact=False).click()
        expect(page.get_by_role("heading", name=name, exact=True).first).to_be_visible()
    results.append({"scenario": "all_required_views_and_viewer_restrictions", "passed": True})
    assert page.evaluate("localStorage.length") == 0
    assert page.evaluate("sessionStorage.length") == 0
    page.get_by_role("navigation").get_by_role("button", name="Overview", exact=False).click()
    if page.get_by_role("button", name="Close inspector").count():
        page.get_by_role("button", name="Close inspector").click()
    page.screenshot(path=str(out / "dashboard-desktop.png"), full_page=True)
    mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
    login(mobile, "viewer")
    assert mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    mobile.screenshot(path=str(out / "dashboard-mobile.png"), full_page=True)
    mobile.get_by_role("button", name="Sign out", exact=True).click()
    expect(mobile.get_by_label("Access token")).to_be_visible()
    results.append({"scenario": "responsive_layout_and_memory_only_session", "passed": True})
    page.get_by_role("button", name="Sign out", exact=True).click()
    expect(page.get_by_label("Access token")).to_be_visible()
    assert not errors, errors
    browser.close()

report = {
    "verified_browser": True,
    "browser": "Chromium / Playwright 1.58.0",
    "scenario_count": len(results),
    "results": results,
    "uncaught_page_errors": errors,
    "viewport_desktop": [1440, 1050],
    "viewport_mobile": [390, 844],
    "paid_model_calls": 0,
}
(out / "browser-check.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(
    json.dumps(
        {"verified_browser": True, "scenarios": len(results), "uncaught_page_errors": len(errors)}
    )
)
