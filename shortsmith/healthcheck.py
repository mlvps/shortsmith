"""Cross-platform pipeline health check.

Verifies scheduled jobs (launchd / cron / Windows Task Scheduler), log
freshness, error counts, queue size, and disk space. Sends a push
notification with status.
"""
from __future__ import annotations
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config, notify

EXPECTED_JOB_NAMES = ["com.shortsmith.dailyupload", "com.shortsmith.weekly",
                      "com.shortsmith.healthcheck"]
WIN_TASK_PREFIX = "shortsmith_"
CRON_MARKER_BEGIN = "# >>> shortsmith managed (do not edit) >>>"

UPLOAD_LOG_MAX_AGE_HOURS = 30
ANALYZE_LOG_MAX_AGE_HOURS = 24 * 8


def hours_since_mtime(path):
    if not path.exists():
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return (datetime.now(timezone.utc) - mtime).total_seconds() / 3600.0


def file_size(path):
    return path.stat().st_size if path.exists() else 0


def jobs_ok() -> tuple[bool, str]:
    """Returns (all_jobs_present, summary_string)."""
    s = sys.platform
    if s == "darwin":
        try:
            out = subprocess.check_output(["launchctl", "list"], text=True, timeout=10)
        except Exception as e:
            return (False, f"launchctl not callable: {e}")
        missing = [j for j in EXPECTED_JOB_NAMES if j not in out]
        if missing:
            return (False, "launchd missing: " + ", ".join(missing))
        return (True, f"launchd: {len(EXPECTED_JOB_NAMES)} jobs loaded")
    if s.startswith("linux"):
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if r.returncode != 0 or CRON_MARKER_BEGIN not in r.stdout:
            return (False, "cron: shortsmith block missing")
        return (True, "cron: shortsmith block present")
    if s == "win32":
        r = subprocess.run(
            ["schtasks", "/Query", "/FO", "CSV", "/NH"],
            capture_output=True, text=True,
        )
        present = sum(
            1 for line in r.stdout.splitlines()
            if WIN_TASK_PREFIX in line.split(",", 1)[0]
        )
        if present == 0:
            return (False, "Windows Task Scheduler: no shortsmith tasks")
        return (True, f"Windows Task Scheduler: {present} tasks present")
    return (False, f"unsupported platform: {s}")


def main(cfg: config.Config, args=None) -> int:
    upload_log = cfg.project_root / "upload.log"
    upload_err = cfg.project_root / "upload.err"
    analyze_log = cfg.project_root / "analyze.log"
    analyze_err = cfg.project_root / "analyze.err"

    issues: list[str] = []
    notes: list[str] = []

    ok, summary = jobs_ok()
    (notes if ok else issues).append(summary)

    upload_age = hours_since_mtime(upload_log)
    if upload_age is None:
        notes.append("upload.log missing — no daily run yet")
    elif upload_age > UPLOAD_LOG_MAX_AGE_HOURS:
        issues.append(f"upload.log stale: {upload_age:.1f}h old")
    else:
        notes.append(f"upload.log: {upload_age:.1f}h old")

    analyze_age = hours_since_mtime(analyze_log)
    if analyze_age is None:
        notes.append("analyze.log missing — first weekly run pending")
    elif analyze_age > ANALYZE_LOG_MAX_AGE_HOURS:
        issues.append(f"analyze.log stale: {analyze_age:.1f}h old")
    else:
        notes.append(f"analyze.log: {analyze_age:.1f}h old")

    for label, path in [("upload.err", upload_err), ("analyze.err", analyze_err)]:
        if file_size(path) == 0:
            continue
        try:
            recent = path.read_text(errors="replace").splitlines()[-50:]
            real = [l for l in recent if "ERROR" in l or "Traceback" in l or "FAILED" in l]
            if real:
                issues.append(f"{label}: {len(real)} recent errors")
                notes.append("last: " + real[-1][:120])
        except Exception:
            pass

    final_count = len(list(cfg.final_dir.glob("final_*.mp4"))) if cfg.final_dir.exists() else 0
    uploaded_count = 0
    if cfg.uploaded_path.exists():
        try:
            uploaded_count = len(json.loads(cfg.uploaded_path.read_text())
                                 .get("uploaded_indices", []))
        except Exception:
            pass
    remaining = final_count - uploaded_count
    notes.append(f"queue: {uploaded_count}/{final_count} uploaded, {remaining} remaining")
    per_day = cfg.get("upload", "videos_per_day", default=3)
    if remaining < per_day * 7:
        issues.append(f"queue low: {remaining} videos ({remaining // max(per_day,1)} days)")

    free_gb = shutil.disk_usage(str(cfg.project_root)).free / (1024**3)
    notes.append(f"disk free: {free_gb:.1f} GB")
    if free_gb < 5:
        issues.append(f"disk low: {free_gb:.1f} GB")

    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    if issues:
        title = f"shortsmith health: {len(issues)} issue(s)"
        priority = "high"
        body = f"{ts}\n\n" + "\n".join("- " + i for i in issues) + "\n\n" + "\n".join(notes)
    else:
        title = "shortsmith health: all good"
        priority = "low"
        body = f"{ts}\n\n" + "\n".join(notes)

    print(title)
    print(body)
    (cfg.project_root / "health.log").write_text(f"=== {ts} ===\n{title}\n{body}\n")
    notify.send(cfg.ntfy_topic, title, body, priority, tags="stethoscope")
    return 1 if issues else 0
