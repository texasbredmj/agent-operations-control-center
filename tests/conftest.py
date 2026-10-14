import os
import secrets
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from ops_center.api import create_app
from ops_center.config import Settings


@pytest.fixture
def rig():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.fail("DATABASE_URL required for real PostgreSQL integration checks")
    schema = "ops_test_" + uuid.uuid4().hex
    credentials = [
        {"name": role, "role": role, "project": "lab-a", "token": secrets.token_urlsafe(32)}
        for role in ("viewer", "operator", "approver")
    ] + [
        {
            "name": "outsider",
            "role": "operator",
            "project": "lab-b",
            "token": secrets.token_urlsafe(32),
        }
    ]
    with psycopg.connect(url, autocommit=True) as db:
        db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    settings = Settings(url, credentials, schema)
    app = create_app(settings)
    try:
        with TestClient(app) as client:
            yield (
                client,
                app.state.store,
                {r["name"]: {"Authorization": "Bearer " + r["token"]} for r in credentials},
            )
    finally:
        # Only the fresh per-test schema is dropped, never the public application schema.
        assert schema.startswith("ops_test_") and len(schema) == 41
        with psycopg.connect(url, autocommit=True) as db:
            db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def create(rig, mode="normal", role="operator", **updates):
    client, _, headers = rig
    return client.post(
        "/api/tasks",
        headers={**headers[role], "Idempotency-Key": str(uuid.uuid4())},
        json={"title": "Inventory fixture", "mode": mode, "quantity": 2, **updates},
    )


def control(rig, task, action, role="operator", key=None, version=None):
    client, _, headers = rig
    return client.post(
        f"/api/tasks/{task['id']}/{action}",
        headers={**headers[role], "Idempotency-Key": key or str(uuid.uuid4())},
        json={"version": version or task["version"], "reason": "Reviewed fixture operation"},
    )


def detail(rig, task, role="viewer"):
    return rig[0].get("/api/tasks/" + task["id"], headers=rig[2][role])
