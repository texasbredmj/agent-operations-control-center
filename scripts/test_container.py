"""Run the complete suite against the installed Linux wheel and real PostgreSQL."""

import os
import subprocess
from pathlib import Path

from local_env import local_env

root = Path(__file__).resolve().parents[1]
values = local_env()
env = {
    **os.environ,
    "DATABASE_URL": "postgresql://ops:" + values["POSTGRES_PASSWORD"] + "@postgres:5432/ops",
    "OPS_CREDENTIALS": values["OPS_CREDENTIALS"],
}
args = [
    "docker",
    "run",
    "--rm",
    "--network",
    "lab-ops08_default",
    "--env",
    "DATABASE_URL",
    "--env",
    "OPS_CREDENTIALS",
    "--volume",
    str(root / "tests") + ":/verification/tests:ro",
    "--volume",
    str(root / "pyproject.toml") + ":/verification/pyproject.toml:ro",
    "--volume",
    str(root / ".gates") + ":/evidence",
    "--workdir",
    "/verification",
    "--entrypoint",
    "python",
    "lab-ops08-api",
    "-m",
    "pytest",
    "-q",
    "-p",
    "no:cacheprovider",
    "--junitxml=/evidence/tests-linux.xml",
]
if os.name == "posix":
    args[3:3] = ["--user", f"{os.getuid()}:{os.getgid()}"]
raise SystemExit(subprocess.run(args, env=env, check=False).returncode)
