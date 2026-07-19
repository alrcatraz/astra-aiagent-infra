#!/usr/bin/env python3
"""harness-gate-audit.py — Read gate-audit.log + archives, produce structured summary.

Used by the harness-daily-audit cron as a data-collection script (no_agent).
Outputs a JSON summary suitable for the agent to format into a report.

Usage:
  python3 ~/.hermes/scripts/harness-gate-audit.py                   # last 24h, live log only
  python3 ~/.hermes/scripts/harness-gate-audit.py --hours=72        # last 3 days, live log only
  python3 ~/.hermes/scripts/harness-gate-audit.py --months=1        # last 24h + this month's archive
  python3 ~/.hermes/scripts/harness-gate-audit.py --all-time        # everything (live + all archives)
"""

import gzip
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

GATE_LOG = Path.home() / ".hermes" / "persistent" / "gate-audit.log"
ARCHIVE_PATTERN = re.compile(r"gate-audit-(\d{6})\.log\.gz")


def load_events(all_time: bool = False, months_back: int = 0) -> list[dict]:
    """Load JSON lines from the current log and optionally archives."""
    events = []

    # Live log
    if GATE_LOG.exists():
        _read_file_lines(GATE_LOG, events)

    # Archives
    if all_time or months_back > 0:
        archive_dir = GATE_LOG.parent
        if archive_dir.exists():
            now = datetime.now()
            # Determine which archives to include
            keep_months = set()
            if all_time:
                pass  # include everything
            else:
                for i in range(months_back):
                    ym = now.strftime("%Y%m")
                    if i > 0:
                        ym = (now.replace(day=1) - timedelta(days=1) * 30 * i).strftime("%Y%m")
                    keep_months.add(ym)

            for f in sorted(archive_dir.iterdir()):
                m = ARCHIVE_PATTERN.match(f.name)
                if m:
                    ym = m.group(1)
                    if all_time or ym in keep_months:
                        _read_gzip_lines(f, events)

    return events


def _read_file_lines(path: Path, events: list[dict]) -> None:
    """Read JSON lines from a plain text file."""
    try:
        text = path.read_text()
    except (FileNotFoundError, PermissionError):
        return
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass


def _read_gzip_lines(path: Path, events: list[dict]) -> None:
    """Read JSON lines from a gzip-compressed file."""
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except (FileNotFoundError, PermissionError, gzip.BadGzipFile):
        pass


def summarize(events: list[dict], hours: int = 24) -> dict:
    """Produce a summary of gate events."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    recent = [e for e in events if parse_ts(e.get("t", "")) > cutoff]
    all_time = events

    def _by_gate(evts):
        counts: dict[str, int] = {}
        for e in evts:
            g = e.get("gate", "unknown")
            counts[g] = counts.get(g, 0) + 1
        return counts

    def _by_phase(evts):
        counts: dict[str, int] = {}
        for e in evts:
            p = e.get("phase", "unknown")
            counts[p] = counts.get(p, 0) + 1
        return counts

    def _by_tool(evts):
        counts: dict[str, int] = {}
        for e in evts:
            t = e.get("tool", "unknown")
            counts[t] = counts.get(t, 0) + 1
        return counts

    total_all_time = len(all_time)
    recent_blocks = _by_gate(recent)
    recent_detail = []
    for e in recent:
        recent_detail.append({
            "t": e.get("t", ""),
            "gate": e.get("gate", ""),
            "tool": e.get("tool", ""),
            "phase": e.get("phase", ""),
            "cmd": e.get("cmd", ""),
            "reason": e.get("reason", ""),
        })

    return {
        "period_hours": hours,
        "period_t": {
            "start": cutoff.isoformat(),
            "end": datetime.now(timezone.utc).isoformat(),
        },
        "summary": {
            "total_all_time": total_all_time,
            "total_recent": len(recent),
            "by_gate": recent_blocks,
            "by_phase": _by_phase(recent),
            "by_tool": _by_tool(recent),
        },
        "recent_events": recent_detail[-20:],
        "gates_empty": {
            k: v
            for k, v in {"research": 0, "modify": 0, "ssh": 0, "closure": 0}.items()
            if recent_blocks.get(k, 0) == 0
        },
    }


def parse_ts(ts_str: str) -> datetime:
    """Parse ISO timestamp with fallback."""
    try:
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


if __name__ == "__main__":
    hours = 24
    months = 0
    all_time = False

    for arg in sys.argv[1:]:
        if arg.startswith("--hours="):
            hours = int(arg.split("=")[1])
        elif arg.startswith("--months="):
            months = int(arg.split("=")[1])
        elif arg == "--all-time":
            all_time = True

    evts = load_events(all_time=all_time, months_back=months)
    summary = summarize(evts, hours=hours)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
