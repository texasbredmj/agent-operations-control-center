import secrets

import pytest
from pydantic import ValidationError

from ops_center.api import Control, CreateTask
from ops_center.config import Settings


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": True},
        {"quantity": 11},
        {"quantity": "2"},
        {"mode": "shell"},
        {"extra": 1},
        {"title": " "},
    ],
)
def test_strict_task_contract(changes):
    with pytest.raises(ValidationError):
        CreateTask.model_validate({"title": "Reserve stock", **changes})


@pytest.mark.parametrize(
    "body",
    [
        {"version": 0, "reason": "ok!"},
        {"version": True, "reason": "ok!"},
        {"version": 1, "reason": " "},
        {"version": 1, "reason": "ok!", "role": "approver"},
    ],
)
def test_strict_control_contract(body):
    with pytest.raises(ValidationError):
        Control.model_validate(body)


def test_credentials_fail_closed_and_are_distinct():
    token = secrets.token_urlsafe(32)
    row = {"name": "reader", "role": "viewer", "project": "lab", "token": token}
    settings = Settings("postgresql://unused", [row])
    assert settings.authenticate(token).role == "viewer"
    assert settings.authenticate("wrong") is None
    for credentials in (
        [{**row, "token": "short"}],
        [row, {**row, "name": "other"}],
        [{**row, "role": "admin"}],
    ):
        with pytest.raises(ValueError):
            Settings("postgresql://unused", credentials)
