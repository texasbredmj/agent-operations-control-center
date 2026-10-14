import hashlib
import json
import os
import re
import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    name: str
    role: str
    project: str


class Settings:
    def __init__(self, database_url=None, credentials=None, schema="public"):
        self.database_url = database_url or os.environ["DATABASE_URL"]
        self.credentials = credentials or json.loads(os.environ["OPS_CREDENTIALS"])
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
            raise ValueError("invalid database schema")
        self.schema = schema
        if not self.credentials:
            raise ValueError("at least one principal is required")
        names = set()
        for row in self.credentials:
            if len(row["token"]) < 32 or row["role"] not in {"viewer", "operator", "approver"}:
                raise ValueError("invalid principal credential")
            if row["name"] in names or not re.fullmatch(r"[a-z0-9-]{1,40}", row["project"]):
                raise ValueError("invalid principal identity/project")
            names.add(row["name"])
        if len({r["token"] for r in self.credentials}) != len(self.credentials):
            raise ValueError("credentials must be distinct")

    def authenticate(self, token):
        incoming = hashlib.sha256(token.encode()).digest()
        found = None
        for row in self.credentials:
            expected = hashlib.sha256(row["token"].encode()).digest()
            if secrets.compare_digest(incoming, expected):
                found = Principal(row["name"], row["role"], row["project"])
        return found
