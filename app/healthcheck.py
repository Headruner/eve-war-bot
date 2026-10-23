"""Docker HEALTHCHECK: healthy if the last successful cycle is recent enough."""
import sys
import time
from pathlib import Path

from .config import load_settings

s = load_settings()
limit = s.poll_interval_min * 60 * 2 + 300          # two missed cycles + 5 min grace
p = Path(s.heartbeat_file)
if not p.exists():
    sys.exit(1)
age = time.time() - int(p.read_text().strip() or 0)
sys.exit(0 if age < limit else 1)
