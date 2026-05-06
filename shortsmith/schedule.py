"""Install/uninstall/status of scheduled jobs across platforms.

  - macOS  → launchd (~/Library/LaunchAgents/*.plist)
  - Linux  → cron (user crontab via `crontab` command)
  - Windows → Task Scheduler (schtasks)

The schedule itself comes from config.yaml:
  upload.schedule_hours    (list of hours for daily upload, 1 video per slot)
  weekly_analyze_day       (0=Sunday … 6=Saturday) defaults to 0
  weekly_analyze_hour      (default 10)
  healthcheck_day          (default 1=Monday)
  healthcheck_hour         (default 8)
"""
from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from . import config

LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"

JOB_NAMES = [
    "com.shortsmith.dailyupload",
    "com.shortsmith.weekly",
    "com.shortsmith.healthcheck",
]

CRON_MARKER_BEGIN = "# >>> shortsmith managed (do not edit) >>>"
CRON_MARKER_END = "# <<< shortsmith managed <<<"
WIN_TASK_PREFIX = "shortsmith_"


def _python_bin() -> str:
    return sys.executable or shutil.which("python3") or shutil.which("python") or "python3"


def _schedule_params(cfg: config.Config) -> dict:
    return {
        "upload_hours": cfg.get("upload", "schedule_hours", default=[9, 13, 19]),
        "weekly_day": cfg.get("schedule", "weekly_analyze_day", default=0),       # 0=Sun
        "weekly_hour": cfg.get("schedule", "weekly_analyze_hour", default=10),
        "health_day": cfg.get("schedule", "healthcheck_day", default=1),          # 1=Mon
        "health_hour": cfg.get("schedule", "healthcheck_hour", default=8),
    }


# ─── macOS launchd ───────────────────────────────────────────────────────────
def _launchd_plist_template_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "plists"


def _launchd_render(template_path: Path, project_root: Path, python_bin: str,
                    p: dict) -> str:
    text = template_path.read_text()
    text = text.replace("{{PROJECT_ROOT}}", str(project_root))
    text = text.replace("{{PYTHON}}", python_bin)
    if "{{SCHEDULE_HOURS}}" in text:
        entries = []
        for h in p["upload_hours"]:
            entries.append(
                "        <dict>\n"
                f"            <key>Hour</key><integer>{h}</integer>\n"
                "            <key>Minute</key><integer>0</integer>\n"
                "        </dict>"
            )
        text = text.replace("{{SCHEDULE_HOURS}}", "\n".join(entries))
    return text


def _launchd_install(cfg: config.Config) -> None:
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    p = _schedule_params(cfg)
    py = _python_bin()
    for job in JOB_NAMES:
        tmpl = _launchd_plist_template_dir() / f"{job}.plist.template"
        if not tmpl.exists():
            print(f"missing template: {tmpl}", file=sys.stderr)
            continue
        rendered = _launchd_render(tmpl, cfg.project_root, py, p)
        target = LAUNCH_AGENTS / f"{job}.plist"
        target.write_text(rendered)
        subprocess.run(["launchctl", "unload", str(target)], capture_output=True)
        subprocess.run(["launchctl", "load", str(target)], check=True)
        print(f"loaded: {target}")
    print("\nverify:  launchctl list | grep com.shortsmith")
    print("\nIMPORTANT: macOS may block launchd from reading ~/Documents/.")
    print(f"if you see 'Operation not permitted' in upload.err, grant Full Disk")
    print(f"Access to {py} in System Settings → Privacy & Security.")


def _launchd_uninstall() -> None:
    for job in JOB_NAMES:
        target = LAUNCH_AGENTS / f"{job}.plist"
        if not target.exists():
            continue
        subprocess.run(["launchctl", "unload", str(target)], capture_output=True)
        target.unlink()
        print(f"unloaded + removed: {target}")


def _launchd_status() -> None:
    out = subprocess.check_output(["launchctl", "list"], text=True)
    for job in JOB_NAMES:
        loaded = job in out
        print(f"  {'OK' if loaded else 'MISSING'}: {job}")


# ─── Linux cron ──────────────────────────────────────────────────────────────
def _cron_lines(cfg: config.Config) -> list[str]:
    p = _schedule_params(cfg)
    py = _python_bin()
    pr = cfg.project_root
    cfg_path = pr / "config.yaml"
    base = f'cd "{pr}" && {py} -m shortsmith.cli -c "{cfg_path}"'

    lines = [CRON_MARKER_BEGIN]
    for h in p["upload_hours"]:
        lines.append(f'0 {h} * * * {base} upload --count 1 '
                     f'>> "{pr}/upload.log" 2>> "{pr}/upload.err"')
    lines.append(f'0 {p["weekly_hour"]} * * {p["weekly_day"]} {base} analyze '
                 f'>> "{pr}/analyze.log" 2>> "{pr}/analyze.err"')
    lines.append(f'0 {p["health_hour"]} * * {p["health_day"]} {base} healthcheck '
                 f'>> "{pr}/healthcheck.log" 2>> "{pr}/healthcheck.err"')
    lines.append(CRON_MARKER_END)
    return lines


def _read_crontab() -> str:
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def _write_crontab(content: str) -> None:
    p = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
    p.communicate(content)
    if p.returncode != 0:
        raise SystemExit("crontab install failed")


def _strip_managed_block(content: str) -> str:
    out: list[str] = []
    inside = False
    for line in content.splitlines():
        if line.strip() == CRON_MARKER_BEGIN:
            inside = True
            continue
        if line.strip() == CRON_MARKER_END:
            inside = False
            continue
        if not inside:
            out.append(line)
    return "\n".join(out).rstrip() + "\n"


def _cron_install(cfg: config.Config) -> None:
    if not shutil.which("crontab"):
        raise SystemExit("crontab not found. install cron and try again.")
    existing = _strip_managed_block(_read_crontab())
    new = existing + "\n" + "\n".join(_cron_lines(cfg)) + "\n"
    _write_crontab(new)
    print("cron entries installed")
    print("verify:  crontab -l | grep shortsmith")


def _cron_uninstall() -> None:
    existing = _strip_managed_block(_read_crontab())
    _write_crontab(existing)
    print("cron entries removed")


def _cron_status() -> None:
    existing = _read_crontab()
    if CRON_MARKER_BEGIN in existing:
        print("OK: cron entries installed")
        for line in existing.splitlines():
            if "shortsmith" in line and not line.startswith("#"):
                print(f"  {line}")
    else:
        print("MISSING: no shortsmith cron entries")


# ─── Windows Task Scheduler ──────────────────────────────────────────────────
def _win_create_task(name: str, py: str, project_root: Path, sub: list[str],
                     hour: int, day: str | None = None) -> None:
    """schtasks wrapper. day = 'MON'/'TUE'/etc for weekly, None for daily."""
    cfg_path = project_root / "config.yaml"
    cmd_args = [
        "-m", "shortsmith.cli", "-c", str(cfg_path), *sub,
    ]
    full_cmd = f'"{py}" ' + " ".join(f'"{a}"' for a in cmd_args)

    schedule_args = (
        ["/SC", "WEEKLY", "/D", day, "/ST", f"{hour:02d}:00"]
        if day else
        ["/SC", "DAILY", "/ST", f"{hour:02d}:00"]
    )
    cmd = [
        "schtasks", "/Create", "/F",
        "/TN", name,
        "/TR", full_cmd,
        *schedule_args,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"failed to create {name}: {r.stderr}", file=sys.stderr)
    else:
        print(f"created: {name}")


def _win_install(cfg: config.Config) -> None:
    p = _schedule_params(cfg)
    py = _python_bin()
    pr = cfg.project_root

    for h in p["upload_hours"]:
        _win_create_task(
            f"{WIN_TASK_PREFIX}upload_{h:02d}",
            py, pr, ["upload", "--count", "1"], h,
        )
    weekly_day = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"][p["weekly_day"]]
    _win_create_task(
        f"{WIN_TASK_PREFIX}weekly", py, pr, ["analyze"], p["weekly_hour"], weekly_day,
    )
    health_day = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"][p["health_day"]]
    _win_create_task(
        f"{WIN_TASK_PREFIX}healthcheck", py, pr, ["healthcheck"],
        p["health_hour"], health_day,
    )


def _win_uninstall() -> None:
    r = subprocess.run(["schtasks", "/Query", "/FO", "CSV", "/NH"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return
    for line in r.stdout.splitlines():
        # CSV: "TaskName","Next Run Time","Status"
        first = line.split(",", 1)[0].strip().strip('"')
        if WIN_TASK_PREFIX in first:
            subprocess.run(["schtasks", "/Delete", "/TN", first, "/F"],
                           capture_output=True)
            print(f"removed: {first}")


def _win_status() -> None:
    r = subprocess.run(["schtasks", "/Query", "/FO", "CSV", "/NH"],
                       capture_output=True, text=True)
    found = False
    for line in r.stdout.splitlines():
        first = line.split(",", 1)[0].strip().strip('"')
        if WIN_TASK_PREFIX in first:
            print(f"  OK: {first}")
            found = True
    if not found:
        print("MISSING: no shortsmith Windows tasks")


# ─── Dispatcher ──────────────────────────────────────────────────────────────
def install(cfg: config.Config) -> None:
    s = sys.platform
    if s == "darwin":
        _launchd_install(cfg)
    elif s.startswith("linux"):
        _cron_install(cfg)
    elif s == "win32":
        _win_install(cfg)
    else:
        raise SystemExit(f"unsupported platform: {s}")


def uninstall(cfg: config.Config) -> None:
    s = sys.platform
    if s == "darwin":
        _launchd_uninstall()
    elif s.startswith("linux"):
        _cron_uninstall()
    elif s == "win32":
        _win_uninstall()
    else:
        raise SystemExit(f"unsupported platform: {s}")


def status(cfg: config.Config) -> None:
    s = sys.platform
    print(f"platform: {s}")
    if s == "darwin":
        _launchd_status()
    elif s.startswith("linux"):
        _cron_status()
    elif s == "win32":
        _win_status()
    else:
        raise SystemExit(f"unsupported platform: {s}")


def dispatch(cfg: config.Config, args: argparse.Namespace) -> None:
    {"install": install, "uninstall": uninstall, "status": status}[args.action](cfg)
