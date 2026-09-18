"""Session logging for gesture events."""

import json
import os
import time
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

MAX_LOG_AGE_DAYS = 7


def _get_log_path():
    """Return the path to today's log file."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    return LOG_DIR / f"gestures-{date_str}.jsonl"


def _rotate_old_logs():
    """Remove log files older than MAX_LOG_AGE_DAYS."""
    cutoff = time.time() - (MAX_LOG_AGE_DAYS * 86400)
    for log_file in LOG_DIR.glob("gestures-*.jsonl"):
        if log_file.stat().st_mtime < cutoff:
            try:
                log_file.unlink()
            except OSError:
                pass


def log_gesture(action: str, details: dict = None):
    """Log a gesture event with timestamp."""
    _rotate_old_logs()

    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
    }
    if details:
        entry["details"] = details

    log_path = _get_log_path()
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def get_recent_logs(limit: int = 100):
    """Return the most recent log entries across all log files."""
    entries = []
    log_files = sorted(LOG_DIR.glob("gestures-*.jsonl"), reverse=True)

    for log_file in log_files:
        if len(entries) >= limit:
            break
        try:
            with open(log_file, "r") as f:
                lines = f.readlines()
                for line in reversed(lines):
                    if len(entries) >= limit:
                        break
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except (OSError, json.JSONDecodeError):
            continue

    return list(reversed(entries))


def get_log_dates():
    """Return a list of dates that have log files."""
    dates = []
    for log_file in sorted(LOG_DIR.glob("gestures-*.jsonl"), reverse=True):
        date_str = log_file.stem.replace("gestures-", "")
        dates.append(date_str)
    return dates
