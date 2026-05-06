"""shortsmith CLI entry point.

Usage:
  shortsmith init                      # scaffold a fresh project here
  shortsmith download                  # pull source shorts via yt-dlp
  shortsmith generate                  # render hook+CTA end-clips
  shortsmith stitch                    # combine source + clips → final/
  shortsmith upload [--count N]        # upload N to YouTube
  shortsmith analyze                   # weekly stats + amplify winners
  shortsmith healthcheck               # health check + push notification
  shortsmith dashboard [--port 8765]   # launch the web UI
  shortsmith schedule install          # write + load launchd jobs
  shortsmith schedule uninstall        # unload + remove launchd jobs
"""
from __future__ import annotations
import argparse
import shutil
import sys
from pathlib import Path

from . import config


def cmd_init(args) -> None:
    pkg_root = Path(__file__).resolve().parent.parent
    cwd = Path.cwd()
    files = {
        "config.example.yaml": pkg_root / "config.example.yaml",
        "examples/hooks_example.json": pkg_root / "examples" / "hooks_example.json",
        "plists/com.shortsmith.dailyupload.plist.template":
            pkg_root / "plists" / "com.shortsmith.dailyupload.plist.template",
        "plists/com.shortsmith.weekly.plist.template":
            pkg_root / "plists" / "com.shortsmith.weekly.plist.template",
        "plists/com.shortsmith.healthcheck.plist.template":
            pkg_root / "plists" / "com.shortsmith.healthcheck.plist.template",
    }
    for rel, src in files.items():
        if not src.exists():
            continue
        dst = cwd / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            print(f"skip (exists): {rel}")
        else:
            shutil.copy2(src, dst)
            print(f"created: {rel}")
    cfg_target = cwd / "config.yaml"
    if not cfg_target.exists():
        shutil.copy2(pkg_root / "config.example.yaml", cfg_target)
        print("created: config.yaml — edit it to customize")
    for d in ["template", "source", "out", "final", "reports"]:
        (cwd / d).mkdir(exist_ok=True)
    print("\nNext steps:")
    print("  1. drop your end-clip into ./template/template.mov")
    print("  2. edit config.yaml (channel URL, ntfy topic, brand colors)")
    print("  3. write your hooks.json (see examples/hooks_example.json)")
    print("  4. shortsmith download    # pull source content")
    print("  5. shortsmith generate    # render end-clips")
    print("  6. shortsmith stitch      # combine source + clips")
    print("  7. shortsmith dashboard   # open the web UI")


def cmd_download(args) -> None:
    from . import download
    cfg = config.load(args.config)
    download.main(cfg, args)


def cmd_generate(args) -> None:
    from . import generate
    cfg = config.load(args.config)
    generate.main(cfg, args)


def cmd_stitch(args) -> None:
    from . import stitch
    cfg = config.load(args.config)
    stitch.main(cfg, args)


def cmd_upload(args) -> None:
    from . import upload
    cfg = config.load(args.config)
    upload.main(cfg, args)


def cmd_analyze(args) -> None:
    from . import analyze
    cfg = config.load(args.config)
    analyze.main(cfg, args)


def cmd_healthcheck(args) -> None:
    from . import healthcheck
    cfg = config.load(args.config)
    raise SystemExit(healthcheck.main(cfg, args))


def cmd_dashboard(args) -> None:
    from . import dashboard
    cfg = config.load(args.config)
    dashboard.run(cfg, host=args.host, port=args.port)


def cmd_schedule(args) -> None:
    from . import schedule
    cfg = config.load(args.config)
    schedule.dispatch(cfg, args)


def main() -> None:
    ap = argparse.ArgumentParser(prog="shortsmith",
                                 description="Open-source viral-shorts pipeline")
    ap.add_argument("--config", "-c", default=None,
                    help="path to config.yaml (auto-discovered by default)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="scaffold a fresh project in CWD").set_defaults(func=cmd_init)

    p = sub.add_parser("download", help="pull source shorts via yt-dlp")
    p.add_argument("--channel", default=None)
    p.add_argument("--count", type=int, default=None)
    p.add_argument("--cookies-browser", default=None,
                   help="e.g. safari, brave, edge — only if YT bot-blocks you")
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("generate", help="render hook+CTA end-clips")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--end", type=int, default=None)
    p.add_argument("--limit", type=int, default=None)
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("stitch", help="combine source + clips → final/")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--end", type=int, default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--seed", type=int, default=42)
    p.set_defaults(func=cmd_stitch)

    p = sub.add_parser("upload", help="upload N videos to YouTube")
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--privacy", choices=["private", "unlisted", "public"], default=None)
    p.add_argument("--schedule", action="store_true",
                   help="set publishAt across next 24h instead of immediate")
    p.add_argument("--start-hour", type=int, default=10)
    p.set_defaults(func=cmd_upload)

    p = sub.add_parser("analyze", help="weekly analytics + amplify")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("healthcheck", help="health check + push notification")
    p.set_defaults(func=cmd_healthcheck)

    p = sub.add_parser("dashboard", help="launch the web UI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(func=cmd_dashboard)

    p = sub.add_parser("schedule", help="manage launchd jobs")
    p.add_argument("action", choices=["install", "uninstall", "status"])
    p.set_defaults(func=cmd_schedule)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
