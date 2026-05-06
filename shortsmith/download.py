"""Downloads YouTube Shorts from a channel via yt-dlp.

Cross-platform: pure Python with concurrent.futures (no bash).

Note on ethics: by using this you agree to respect creators. Stitching their
content into your videos is a gray area under YouTube's reused-content policy.
shortsmith adds your own end-clip + caption to make the result transformative,
but YouTube's enforcement is opaque. Don't be surprised if your channel gets
flagged. This tool is provided as-is, for educational use.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import shutil
import subprocess
import sys

from . import config


def _download_one(vid_id, source_dir,
                  cookies_browser=None):
    """Returns (id, ok, message)."""
    out_template = str(source_dir / "%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "--quiet", "--no-warnings",
        "--sleep-interval", "2", "--max-sleep-interval", "5",
        "-f", "bv*[ext=mp4][height<=1920]+ba[ext=m4a]/b[ext=mp4]/b",
        "--merge-output-format", "mp4",
        "-o", out_template,
        "--no-overwrites", "--no-playlist",
    ]
    if cookies_browser:
        cmd += ["--cookies-from-browser", cookies_browser]
    cmd.append(f"https://www.youtube.com/shorts/{vid_id}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return (vid_id, False, "timeout")
    if r.returncode != 0:
        return (vid_id, False, (r.stderr or r.stdout)[-300:].strip())
    return (vid_id, True, "")


def main(cfg: config.Config, args: argparse.Namespace) -> None:
    if not shutil.which("yt-dlp"):
        raise SystemExit(
            "yt-dlp not found. install it: https://github.com/yt-dlp/yt-dlp\n"
            "  brew install yt-dlp        (macOS)\n"
            "  pipx install yt-dlp        (Linux/Windows)\n"
            "  choco install yt-dlp       (Windows w/ Chocolatey)"
        )

    url = args.channel or cfg.get("source", "channel_url")
    if not url:
        raise SystemExit(
            "no channel URL. pass --channel or set source.channel_url in config.yaml"
        )
    count = args.count or cfg.get("source", "count", default=500)
    parallel = cfg.get("source", "download_parallel", default=2)

    cfg.source_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/2] fetching up to {count} short IDs from {url}")
    res = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--print", "%(id)s",
         "--playlist-end", str(count), url],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        print(res.stderr[-2000:], file=sys.stderr)
        raise SystemExit("failed to enumerate channel")
    ids = [line.strip() for line in res.stdout.splitlines() if line.strip()]
    print(f"got {len(ids)} IDs")

    print(f"[2/2] downloading with {parallel} parallel workers → {cfg.source_dir}")
    succeeded = 0
    failed: list[tuple[str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as ex:
        futures = {
            ex.submit(_download_one, vid, cfg.source_dir, args.cookies_browser): vid
            for vid in ids
        }
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            vid_id, ok, msg = fut.result()
            if ok:
                succeeded += 1
            else:
                failed.append((vid_id, msg))
            if i % 10 == 0 or i == len(ids):
                print(f"  {i}/{len(ids)}  ok={succeeded}  fail={len(failed)}", flush=True)

    done = len(list(cfg.source_dir.glob("*.mp4")))
    print(f"done: {done} files in {cfg.source_dir}")
    if failed:
        print(f"\n{len(failed)} failures (showing first 5):")
        for vid, msg in failed[:5]:
            print(f"  {vid}: {msg.splitlines()[-1] if msg else 'unknown'}")
