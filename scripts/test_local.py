import sys

import pytest
from local_env import configure

configure()
raise SystemExit(pytest.main(sys.argv[1:]))
