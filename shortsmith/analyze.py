"""Weekly analytics + winner amplification.

Fetches stats for all uploaded videos, scores hooks, detects strikes,
identifies "winners", finds similar hooks via keyword overlap and bumps
them to the front of the upload queue. Writes a markdown report and
sends a push notification.
"""
from __future__ import annotations
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from . import config, notify

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "you", "your", "i", "im", "me", "my", "we", "us", "our",
    "to", "of", "in", "on", "at", "for", "with", "by", "from", "as",
    "and", "or", "but", "if", "so", "not", "no", "yes",
    "this", "that", "these", "those", "it", "its",
    "have", "has", "had", "do", "does", "did", "will", "would", "should",
    "can", "could", "just", "really",
}


def auth_yt(cfg: config.Config):
    creds = None
    token_p = cfg.analyze_token_path
    if token_p.exists():
        creds = Credentials.from_authorized_user_file(str(token_p), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(cfg.client_secret_path), SCOPES
            )
            creds = flow.run_local_server(port=0)
        token_p.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z']+", text.lower())
    return {w for w in words if len(w) > 2 and w not in STOP_WORDS}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def fetch_stats(yt, video_ids: list[str]) -> dict:
    out = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        resp = yt.videos().list(
            part="statistics,status,contentDetails,snippet",
            id=",".join(batch),
        ).execute()
        for item in resp.get("items", []):
            out[item["id"]] = item
    return out


def hours_since(iso: str) -> float:
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600.0


def main(cfg: config.Config, args=None) -> None:
    cfg.reports_dir.mkdir(parents=True, exist_ok=True)
    if not cfg.uploaded_path.exists():
        print("no uploads recorded yet")
        return

    hooks = json.loads(cfg.hooks_path.read_text())
    uploaded = json.loads(cfg.uploaded_path.read_text())
    log = uploaded.get("log", [])
    if not log:
        print("no uploads logged")
        return

    yt = auth_yt(cfg)
    video_ids = [e["video_id"] for e in log]
    print(f"fetching stats for {len(video_ids)} videos…")
    stats = fetch_stats(yt, video_ids)

    rows = []
    strikes = []
    for entry in log:
        vid = entry["video_id"]
        item = stats.get(vid)
        if not item:
            strikes.append({"video_id": vid, "reason": "missing, possibly removed",
                            "hook": entry["hook"]})
            continue
        s = item.get("statistics", {})
        st = item.get("status", {})
        views = int(s.get("viewCount", 0))
        likes = int(s.get("likeCount", 0))
        comments = int(s.get("commentCount", 0))
        hrs = hours_since(entry["uploaded_at"])
        score = views / max(hrs, 1.0)
        rows.append({
            "idx": entry["idx"], "video_id": vid, "hook": entry["hook"],
            "views": views, "likes": likes, "comments": comments,
            "hours_live": round(hrs, 1), "score": round(score, 2),
            "privacy": st.get("privacyStatus"),
            "upload_status": st.get("uploadStatus"),
        })
        if st.get("uploadStatus") == "rejected":
            strikes.append({"video_id": vid, "reason": st.get("rejectionReason", "rejected"),
                            "hook": entry["hook"]})
        if st.get("uploadStatus") == "failed":
            strikes.append({"video_id": vid, "reason": st.get("failureReason", "failed"),
                            "hook": entry["hook"]})
        if "regionRestriction" in item.get("contentDetails", {}):
            strikes.append({"video_id": vid, "reason": "region-blocked",
                            "hook": entry["hook"]})

    rows.sort(key=lambda r: r["score"], reverse=True)

    winner_mult = cfg.get("analyze", "winner_multiplier", default=2.5)
    winner_min_h = cfg.get("analyze", "winner_min_hours", default=18)
    amplify_n = cfg.get("analyze", "amplify_per_winner", default=3)

    eligible = [r for r in rows if r["hours_live"] >= winner_min_h]
    median_score = 0.0
    winners = []
    if eligible:
        scores = sorted([r["score"] for r in eligible])
        median_score = scores[len(scores) // 2]
        threshold = max(median_score * winner_mult, 0.5)
        winners = [r for r in eligible if r["score"] >= threshold]

    uploaded_set = set(uploaded["uploaded_indices"])
    existing_priority = []
    if cfg.priority_path.exists():
        existing_priority = json.loads(cfg.priority_path.read_text()).get("indices", [])
    new_priority = list(existing_priority)
    amplified = []
    for w in winners:
        winner_kw = keywords(w["hook"])
        sims = []
        for i, h in enumerate(hooks):
            if i in uploaded_set or i in new_priority:
                continue
            sim = jaccard(winner_kw, keywords(h["hook"]))
            if sim > 0:
                sims.append((sim, i, h["hook"]))
        sims.sort(reverse=True)
        for sim, i, hook_text in sims[:amplify_n]:
            new_priority.append(i)
            amplified.append({
                "winner_hook": w["hook"], "added_idx": i,
                "added_hook": hook_text, "similarity": round(sim, 3),
            })

    cfg.priority_path.write_text(json.dumps({"indices": new_priority}, indent=2))

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    report_path = cfg.reports_dir / f"report_{ts}.md"
    total_views = sum(r["views"] for r in rows)
    avg_views = total_views / max(len(rows), 1)

    lines = [
        f"# Report, {ts}", "",
        f"- Videos analyzed: **{len(rows)}**",
        f"- Total views: **{total_views:,}**",
        f"- Avg views per video: **{avg_views:.1f}**",
        f"- Median score (views/hour): **{median_score:.2f}**",
        f"- Strikes / issues: **{len(strikes)}**",
        f"- Winners (>= {winner_mult}x median, >= {winner_min_h}h live): **{len(winners)}**",
        f"- Amplified (added to priority queue): **{len(amplified)}**",
        f"- Priority queue size: **{len(new_priority)}**",
        "", "## Top 5 by score", "",
        "| score | views | likes | hours | hook |",
        "|------:|------:|------:|------:|------|",
    ]
    for r in rows[:5]:
        lines.append(f"| {r['score']} | {r['views']} | {r['likes']} | {r['hours_live']} | {r['hook']} |")
    if winners:
        lines += ["", "## Winners", ""]
        for w in winners:
            lines.append(f"- **{w['score']}**, {w['hook']}  → https://youtube.com/shorts/{w['video_id']}")
    if amplified:
        lines += ["", "## Amplifications added to priority queue", ""]
        for a in amplified:
            lines.append(f"- (sim {a['similarity']}) {a['added_hook']}  <- winner: {a['winner_hook']}")
    if strikes:
        lines += ["", "## Strikes / issues", ""]
        for s in strikes:
            lines.append(f"- {s['video_id']}, {s['reason']}, {s.get('hook','')}")
    report_path.write_text("\n".join(lines))
    print(f"report → {report_path}")

    topic = cfg.ntfy_topic
    if topic:
        body_parts = [
            f"{len(rows)} videos | {total_views:,} views | avg {avg_views:.0f}/vid",
            f"winners: {len(winners)} | amplified: {len(amplified)}",
        ]
        if strikes:
            body_parts.append(f"WARN {len(strikes)} issues")
        if winners:
            body_parts += ["", f"top: {winners[0]['hook'][:80]}"]
        notify.send(topic, f"shortsmith report - {ts}", "\n".join(body_parts))
        print(f"ntfy → {topic}")
