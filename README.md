# Agent Operations Control Center

Project 08 of AI Systems Engineering Lab. **Relay** is a functioning React operations dashboard with
a FastAPI control plane, PostgreSQL task/approval/audit storage, a deterministic worker and persisted
OpenTelemetry spans. An operator can observe work, investigate receipts and safely control execution.

This repository runs independently of Projects 01–07. Its worker performs an actual database ledger
reservation; it does not pretend to integrate their runtimes or a live model provider.

## Start the local lab

Requirements: Docker Compose and Python 3.11+. Node 22 is needed only for frontend development;
the Docker build compiles React and serves it from the API at one origin.

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.lock .
.venv/Scripts/python scripts/init_local.py
docker compose up -d --build --wait
.venv/Scripts/python scripts/demo.py
```

On Linux, replace `.venv/Scripts/python` with `.venv/bin/python`.
Open **http://127.0.0.1:18780**. `scripts/init_local.py` generates distinct viewer, operator and approver
tokens in the ignored `.env` file, refuses to overwrite it, and never prints credentials. Open that
file locally and copy the token for the role you want into the login form. Do not share or commit it.
The browser holds the token in tab memory only; sign out to clear it. There is no cookie, localStorage
or sessionStorage login. Reloading requires login again.

The demo creates eight real task scenarios and leaves one pending approval for inspection. Running
it again appends another scenario set; it does not reset the database. The configured fixture project
accepts at most 1,000 tasks, serialized in PostgreSQL. PostgreSQL binds only localhost port 15438.
`docker compose down` stops this lab and preserves its named database volume.

## Observe and control

The sidebar provides active/completed/failed tasks, pending approvals, workflow and tool-call history,
execution traces, reliability, resource usage, cost reports and agent status. Select a task to open
its inspector. History, tool calls, trace spans and independent verification evidence are separate tabs.
Status filters and pagination run on the backend; search explicitly applies to the current page.
Views refresh every 2.5 seconds. Empty and disconnected states remain visible.

| Role | Backend-authorized operations |
| --- | --- |
| Viewer | Read tasks, history, receipts, spans, aggregates and worker health for its configured project |
| Operator | Viewer access plus create tasks, cancel eligible work and retry eligible failures |
| Approver | Viewer access plus approve or reject a matching pending action |

The backend obtains identity, role and project from the credential configuration. Request bodies
cannot choose them. Each principal has one role; an initiating operator cannot approve their own task.
Cross-project task inspection and control return 404, and project aggregates exclude other projects.
Shared worker process counters are explicitly identified as infrastructure metrics.

Every mutation needs a UUID `Idempotency-Key`. Control requests also carry the inspected task
`version` and a 3–300 character reason. A stale version returns 409 so an operator must refresh.
Successful request replay returns the original response without another effect or history entry;
reusing a key for a different actor/body/action is rejected. Approval is bound to a hash of the exact
task, tool and quantity. The UI asks for a reason and confirmation, but all enforcement is server-side.

Supported fixture workflows:

- Normal reservation: worker inserts a ledger effect and independently reads the receipt to verify it.
- Approval: worker cannot claim the task until an approver accepts the pending action.
- Temporary failure: first attempt fails before any effect; an operator can explicitly retry it.
- Permanent failure: no automatic retry or operator retry is eligible.
- Receipt mismatch: the tool claims success but the ledger has the wrong quantity; verification
  fails, the task remains failed and further retry is blocked for investigation.

Cancellation and execution serialize on the task row. Cancellation before the transactional effect
prevents it; after verified completion the cancel request is rejected rather than claiming rollback.
Workers use expiring claims, row locks and bounded attempts. Old claim tokens cannot commit after
recovery. A unique ledger key and one transaction bind the fixture effect, verification and final state.
These guarantees apply to this database effect, not arbitrary external APIs.

## Verification

```powershell
.venv/Scripts/python scripts/test_local.py -q --junitxml=.gates/tests-host.xml
.venv/Scripts/python scripts/test_container.py
.venv/Scripts/python scripts/demo.py
.venv/Scripts/python scripts/verify_restart.py
docker compose --profile verification run --build --rm browser
```

The full backend suite has 35 tests against real PostgreSQL. Each integration test uses and removes
only its fresh `ops_test_...` schema. The Linux test runner uses the installed wheel with read-only
test sources; the Windows runner uses the local installation. `tests/test_contracts.py` has eleven
database-free checks for the six Windows/Linux × Python 3.11/3.12/3.14 CI policy jobs. The seventh CI
job builds the stack, runs both complete suites, eight HTTP scenarios, durable restart checks and
eight real Chromium scenarios, then uploads redacted evidence for 14 days.

Browser checks exercise login rejection, creation, receipt inspection, workflow/tools/traces, cancellation,
retry, approval/rejection, all required views, viewer restrictions, desktop/mobile layout and sign-out.
`Dockerfile.browser` is a test-only Chromium environment, sharing the API network namespace so the
browser uses a loopback origin. It is not a deployed application service.

Generated `.gates/` evidence includes JUnit, HTTP/browser/restart JSON and desktop/mobile screenshots.
[Local verification evidence](docs/evidence/local-verification.json) records confirmed results and source
hashes. CI workflow files being present does not imply remote CI has run. The portfolio records remote
results only after publication and inspection. The optional manual security workflow runs live
pip-audit and npm audit separately from deterministic correctness checks. Advisory results are only
as current as the scan time.

## Frontend development

```text
cd frontend
npm ci --ignore-scripts
npm run build
npx prettier --check src index.html package.json package-lock.json
```

The application serves the resulting `frontend/dist` at the same origin as `/api`, without CORS.
For host development set `OPS_STATIC` to the absolute `frontend/dist` path. Configure `DATABASE_URL`
and `OPS_CREDENTIALS`, then run `uvicorn ops_center.api:create_app --factory`. The Docker build already
does this; no browser-visible server credential or database connection is bundled into React.

## Scope

This is a local engineering lab with reviewed fixture workflows, fixed tools and generated static
credentials, not a production identity system. Tokens have no expiry/rotation endpoint; production
deployment needs TLS, an identity provider, secret rotation, abuse controls, backups, migrations,
separate database privileges and protected audit retention. Configuration and database administrators
are trusted; application audit history is durable, not tamperproof against a database administrator.

Reliability metrics are lifetime fixture counts, not production SLOs. CPU/memory are real shared
worker process counters, CPU is cumulative seconds and offline status follows a five-second heartbeat
threshold. Costs and model tokens are zero because no model endpoint is called; this is not an invoice
verification system. There are no arbitrary shell tools, cloud deployments or paid resources.
See [architecture](docs/architecture.md) and [threat model](docs/threat-model.md).
