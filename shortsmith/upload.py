"""Uploads stitched videos to YouTube as Shorts.

Reads `final/final_xxxx.mp4`, uploads N per run with title/description/tags
derived from hooks.json. Tracks uploaded indices so it never double-posts.
"""
from __future__ import annotations
import argparse
import json
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from . import config

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def auth_youtube(cfg: config.Config):
    creds = None
    token_p = cfg.upload_token_path
    if token_p.exists():
        creds = Credentials.from_authorized_user_file(str(token_p), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            secret_p = cfg.client_secret_path
            if not secret_p.exists():
                raise SystemExit(
                    f"missing {secret_p}\n"
                    f"see docs/SETUP.md for how to create OAuth credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(secret_p), SCOPES)
            creds = flow.run_local_server(port=0)
        token_p.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def load_uploaded(cfg: config.Config) -> dict:
    p = cfg.uploaded_path
    if p.exists():
        return json.loads(p.read_text())
    return {"uploaded_indices": [], "log": []}


def save_uploaded(cfg: config.Config, data: dict) -> None:
    cfg.uploaded_path.write_text(json.dumps(data, indent=2))


def cta_text(segments: list[dict]) -> str:
    return "".join(s.get("text", "") for s in segments).strip()


def metadata_for(idx: int, hook: str, cta: str, cfg: config.Config) -> dict:
    title = hook.strip()
    if len(title) > 95:
        title = title[:92] + "..."
    title = title + " #shorts"
    description_template = cfg.get("upload", "description_template", default=None)
    if description_template:
        description = description_template.format(hook=hook, cta=cta)
    else:
        description = f"{hook}\n\n{cta}\n\n#shorts"
    rng = random.Random(idx)
    tags = list(cfg.get("upload", "default_tags", default=["shorts", "fyp"]))
    rng.shuffle(tags)
    return {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags[:12],
            "categoryId": cfg.get("upload", "category_id", default="22"),
        },
    }


def pick_next_indices(count: int, total: int, uploaded: list[int],
                      priority_path: Path) -> list[int]:
    uploaded_set = set(uploaded)
    priority: list[int] = []
    if priority_path.exists():
        priority = json.loads(priority_path.read_text()).get("indices", [])
        priority = [i for i in priority if i not in uploaded_set]
    fallback = [i for i in range(total) if i not in uploaded_set and i not in priority]
    queue = priority + fallback
    chosen = queue[:count]
    if priority and any(i in priority for i in chosen):
        remaining = [i for i in priority if i not in chosen]
        priority_path.write_text(json.dumps({"indices": remaining}, indent=2))
    return chosen


def upload_one(yt, idx: int, hook: str, cta: str, privacy: str,
               cfg: config.Config, publish_at: str | None = None) -> str:
    file_path = cfg.final_dir / f"final_{idx:04d}.mp4"
    if not file_path.exists():
        raise SystemExit(f"missing {file_path}")

    body = metadata_for(idx, hook, cta, cfg)
    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}
    if publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at
    body["status"] = status

    media = MediaFileUpload(str(file_path), chunksize=-1, resumable=True,
                            mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    backoff = 2
    while response is None:
        try:
            _, response = req.next_chunk()
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504):
                print(f"  retrying after {backoff}s ({e.resp.status})")
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
            else:
                raise
    return response["id"]


def main(cfg: config.Config, args: argparse.Namespace) -> None:
    hooks = json.loads(cfg.hooks_path.read_text())
    uploaded = load_uploaded(cfg)
    total_videos = len(list(cfg.final_dir.glob("final_*.mp4")))
    if total_videos == 0:
        raise SystemExit(f"no videos in {cfg.final_dir}")

    indices = pick_next_indices(
        args.count, total_videos,
        uploaded["uploaded_indices"], cfg.priority_path,
    )
    if not indices:
        print("queue empty, nothing left to upload")
        return

    yt = auth_youtube(cfg)
    privacy = args.privacy or cfg.get("upload", "default_privacy", default="public")
    print(f"uploading {len(indices)} video(s) as {privacy}"
          + (" (scheduled)" if args.schedule else ""))

    publish_times: list[str | None] = [None] * len(indices)
    if args.schedule:
        now = datetime.now(timezone.utc).astimezone()
        base = now.replace(hour=args.start_hour, minute=0, second=0, microsecond=0)
        if base <= now:
            base += timedelta(days=1)
        gap = timedelta(hours=24 / max(len(indices), 1))
        publish_times = [
            (base + i * gap).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            for i in range(len(indices))
        ]

    for n, idx in enumerate(indices):
        entry = hooks[idx]
        hook_text = entry["hook"]
        cta = cta_text(entry["cta_segments"])
        publish_at = publish_times[n]
        print(f"[{idx:04d}] {hook_text!r}")
        if publish_at:
            print(f"        scheduled for {publish_at}")
        try:
            video_id = upload_one(yt, idx, hook_text, cta, privacy, cfg, publish_at)
            print(f"        uploaded → https://youtube.com/shorts/{video_id}")
            uploaded["uploaded_indices"].append(idx)
            uploaded["log"].append({
                "idx": idx,
                "video_id": video_id,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "publish_at": publish_at,
                "hook": hook_text,
            })
            save_uploaded(cfg, uploaded)
        except HttpError as e:
            print(f"        FAILED: {e}", file=sys.stderr)
            break

    print(f"done. uploaded={len(uploaded['uploaded_indices'])}/{total_videos}")
