import json
import os
from pathlib import Path


def local_env():
    path = Path(__file__).resolve().parents[1] / ".env"
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value.strip("'")
    return values


def configure():
    values = local_env()
    os.environ["DATABASE_URL"] = (
        "postgresql://ops:" + values["POSTGRES_PASSWORD"] + "@127.0.0.1:15438/ops"
    )
    os.environ["OPS_CREDENTIALS"] = values["OPS_CREDENTIALS"]
    return json.loads(values["OPS_CREDENTIALS"])
