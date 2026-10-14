import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .config import Settings
from .store import Store, public_task


class CreateTask(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(min_length=1, max_length=100, pattern=r"\S")
    mode: Literal["normal", "approval", "transient", "permanent", "unverified"] = "normal"
    quantity: int = Field(ge=1, le=10, default=1)


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=300, pattern=r"\S")


def create_app(settings=None):
    settings = settings or Settings()
    store = Store(settings)

    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        yield

    app = FastAPI(
        title="Agent Operations Control Center",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.store = store
    bearer = HTTPBearer(auto_error=False)

    def principal(auth: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        user = settings.authenticate(auth.credentials) if auth else None
        if not user:
            raise HTTPException(
                401, "valid bearer credential required", headers={"WWW-Authenticate": "Bearer"}
            )
        return user

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            }
        )
        return response

    @app.get("/healthz")
    def health():
        # Deliberately exposes only readiness, no operational data or credentials.
        with store.connect() as db:
            db.execute("SELECT 1")
        return {"ready": True}

    @app.get("/api/me")
    def me(user=Depends(principal)):
        return {"name": user.name, "role": user.role, "project": user.project}

    @app.get("/api/tasks")
    def tasks(
        state: str | None = None,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0, le=1000),
        user=Depends(principal),
    ):
        allowed = {
            "ACTIVE",
            "QUEUED",
            "RUNNING",
            "PENDING_APPROVAL",
            "SUCCEEDED",
            "FAILED",
            "CANCELLED",
            "REJECTED",
        }
        if state and state not in allowed:
            raise HTTPException(422, "unknown task state")
        with store.connect() as db:
            rows = db.execute(
                "SELECT * FROM tasks WHERE project=%s AND (%s::text IS NULL OR state=%s OR (%s='ACTIVE' AND state IN ('QUEUED','RUNNING'))) ORDER BY created_at DESC,id LIMIT %s OFFSET %s",
                (user.project, state, state, state, limit, offset),
            ).fetchall()
            total = db.execute(
                "SELECT count(*) AS n FROM tasks WHERE project=%s AND (%s::text IS NULL OR state=%s OR (%s='ACTIVE' AND state IN ('QUEUED','RUNNING')))",
                (user.project, state, state, state),
            ).fetchone()["n"]
        return {
            "items": [public_task(row) for row in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    @app.get("/api/tasks/{task_id}")
    def inspect(task_id: uuid.UUID, user=Depends(principal)):
        with store.connect() as db:
            row = store.task(db, task_id, user.project)
            if not row:
                raise HTTPException(404, "task not found")
            result = {"task": public_task(row)}
            for table, key in [
                ("events", "history"),
                ("tool_calls", "tool_calls"),
                ("spans", "spans"),
            ]:
                # Names come from this fixed allowlist, never a request parameter.
                result[key] = db.execute(
                    f"SELECT * FROM {table} WHERE task_id=%s ORDER BY at,id"
                    if table != "spans"
                    else "SELECT * FROM spans WHERE task_id=%s ORDER BY at,span_id",
                    (task_id,),
                ).fetchall()
            result["approval"] = db.execute(
                "SELECT * FROM approvals WHERE task_id=%s", (task_id,)
            ).fetchone()
            result["evidence"] = db.execute(
                "SELECT * FROM evidence WHERE task_id=%s", (task_id,)
            ).fetchone()
        return result

    @app.post("/api/tasks", status_code=201)
    def create(
        body: CreateTask,
        key: Annotated[uuid.UUID, Header(alias="Idempotency-Key")],
        user=Depends(principal),
    ):
        if user.role != "operator":
            raise HTTPException(403, "operator role required")
        return store.create(user, body, key)

    @app.post("/api/tasks/{task_id}/{action}")
    def control(
        task_id: uuid.UUID,
        action: Literal["approve", "reject", "cancel", "retry"],
        body: Control,
        key: Annotated[uuid.UUID, Header(alias="Idempotency-Key")],
        user=Depends(principal),
    ):
        role = "approver" if action in {"approve", "reject"} else "operator"
        if user.role != role:
            raise HTTPException(403, role + " role required")
        return store.control(user, task_id, action, body, key)

    @app.get("/api/overview")
    def overview(user=Depends(principal)):
        with store.connect() as db:
            counts = {
                r["state"]: r["n"]
                for r in db.execute(
                    "SELECT state,count(*) AS n FROM tasks WHERE project=%s GROUP BY state",
                    (user.project,),
                ).fetchall()
            }
            usage = db.execute(
                "SELECT count(c.id) AS tool_calls,coalesce(sum(c.input_tokens),0) AS input_tokens,coalesce(sum(c.output_tokens),0) AS output_tokens,coalesce(sum(c.cost_nusd),0) AS cost_nusd,coalesce(avg(c.duration_ms),0) AS mean_tool_ms FROM tool_calls c JOIN tasks t ON c.task_id=t.id WHERE t.project=%s",
                (user.project,),
            ).fetchone()
            verification = db.execute(
                "SELECT count(*) AS checked,count(*) FILTER(WHERE e.verified) AS passed FROM evidence e JOIN tasks t ON e.task_id=t.id WHERE t.project=%s",
                (user.project,),
            ).fetchone()
            agents = db.execute(
                "SELECT id,heartbeat,processed,rss_bytes,cpu_seconds,heartbeat>now()-interval '5 seconds' AS online FROM agents ORDER BY id"
            ).fetchall()
        # Worker process resource counters are shared infrastructure, explicitly labelled.
        terminal = counts.get("SUCCEEDED", 0) + counts.get("FAILED", 0)
        return {
            "counts": counts,
            "usage": usage,
            "verification": verification,
            "agents": agents,
            "reliability": {
                "terminal_executions": terminal,
                "verified_success_rate": counts.get("SUCCEEDED", 0) / terminal
                if terminal
                else None,
            },
            "accounting": "deterministic fixtures; zero model calls; shared worker resource counters",
        }

    static = Path(os.environ.get("OPS_STATIC", "/app/frontend/dist"))
    if static.is_dir():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(static / "index.html")

    return app
