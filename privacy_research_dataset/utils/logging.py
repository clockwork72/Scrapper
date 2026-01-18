from __future__ import annotations
import sys
from datetime import datetime

def log(msg: str) -> None:
    ts = datetime.utcnow().isoformat(timespec="seconds")
    sys.stdout.write(f"[{ts}Z] {msg}\n")
    sys.stdout.flush()

def warn(msg: str) -> None:
    ts = datetime.utcnow().isoformat(timespec="seconds")
    sys.stderr.write(f"[{ts}Z] WARN: {msg}\n")
    sys.stderr.flush()
