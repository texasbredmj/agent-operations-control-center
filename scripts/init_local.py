"""Generate new local-only credentials. Never print tokens or overwrite an existing .env."""

import json
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
rows = [
    {"name": role, "role": role, "project": "engineering-lab", "token": secrets.token_urlsafe(32)}
    for role in ("viewer", "operator", "approver")
]
password = secrets.token_urlsafe(32)
with (root / ".env").open("x", encoding="utf-8") as handle:
    handle.write("POSTGRES_PASSWORD=" + password + "\n")
    handle.write("OPS_CREDENTIALS='" + json.dumps(rows, separators=(",", ":")) + "'\n")
print("Generated .env with three distinct local roles. Credentials were not printed.")
