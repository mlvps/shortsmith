"""Flask web dashboard for shortsmith.

Single-page UI with status panel, action buttons, recent uploads, and live log.
Connect YouTube via OAuth-launching button. Trigger any pipeline step from
the browser. Designed to run locally on 127.0.0.1.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

try:
    from flask import Flask, jsonify, render_template, request, send_from_directory
except ImportError as e:
    raise SystemExit(
        "flask not installed. run: pip install -r requirements.txt"
    ) from e

from . import config

app = Flask(__name__, template_folder="templates", static_folder="static")
_cfg: config.Config | None = None
_jobs: dict[str, dict] = {}  # in-memory job tracker


def cfg() -> config.Config:
    assert _cfg is not None
    return _cfg


def _read_json(path: Path) -> dict | list:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _tail(path: Path, n: int = 50) -> str:
    if not path.exists():
        return ""
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-n:])
    except Exception:
        return ""


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    c = cfg()
    uploaded = _read_json(c.uploaded_path) or {"uploaded_indices": [], "log": []}
    final_count = len(list(c.final_dir.glob("final_*.mp4"))) if c.final_dir.exists() else 0
    source_count = len(list(c.source_dir.glob("*.mp4"))) if c.source_dir.exists() else 0
    clip_count = len(list(c.out_dir.glob("clip_*.mp4"))) if c.out_dir.exists() else 0
    hooks_count = 0
    if c.hooks_path.exists():
        try:
            hooks_count = len(json.loads(c.hooks_path.read_text()))
        except Exception:
            pass

    yt_connected = c.upload_token_path.exists()
    has_secret = c.client_secret_path.exists()

    recent = []
    for entry in (uploaded.get("log", []) or [])[-10:][::-1]:
        recent.append({
            "video_id": entry.get("video_id"),
            "hook": entry.get("hook"),
            "uploaded_at": entry.get("uploaded_at"),
            "url": f"https://youtube.com/shorts/{entry.get('video_id')}",
        })

    return jsonify({
        "yt_connected": yt_connected,
        "has_client_secret": has_secret,
        "ntfy_topic": c.ntfy_topic,
        "channel_url": c.get("source", "channel_url", default=""),
        "template_exists": c.template_path.exists(),
        "template_path": str(c.template_path),
        "counts": {
            "hooks": hooks_count,
            "sources": source_count,
            "clips": clip_count,
            "final": final_count,
            "uploaded": len(uploaded.get("uploaded_indices", [])),
        },
        "recent_uploads": recent,
        "running_jobs": [j for j in _jobs.values() if j["status"] == "running"],
    })


@app.route("/api/logs")
def api_logs():
    c = cfg()
    return jsonify({
        "upload": _tail(c.project_root / "upload.log", 30),
        "upload_err": _tail(c.project_root / "upload.err", 30),
        "analyze": _tail(c.project_root / "analyze.log", 30),
        "health": _tail(c.project_root / "health.log", 30),
    })


def _run_job(job_id: str, argv: list[str]) -> None:
    _jobs[job_id]["status"] = "running"
    proc = subprocess.Popen(
        argv, cwd=str(cfg().project_root),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    _jobs[job_id]["pid"] = proc.pid
    output_lines: list[str] = []
    for line in iter(proc.stdout.readline, ""):
        output_lines.append(line.rstrip())
        _jobs[job_id]["output"] = "\n".join(output_lines[-200:])
    proc.wait()
    _jobs[job_id]["status"] = "done" if proc.returncode == 0 else "failed"
    _jobs[job_id]["returncode"] = proc.returncode


def _start_job(name: str, argv: list[str]) -> str:
    job_id = f"{name}-{datetime.now().strftime('%H%M%S')}"
    _jobs[job_id] = {
        "id": job_id, "name": name, "status": "queued",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "output": "", "argv": argv,
    }
    threading.Thread(target=_run_job, args=(job_id, argv), daemon=True).start()
    return job_id


@app.route("/api/run/<action>", methods=["POST"])
def api_run(action: str):
    c = cfg()
    py = sys.executable
    actions = {
        "download": [py, "-m", "shortsmith.cli", "-c", str(c.project_root / "config.yaml"),
                     "download"],
        "generate": [py, "-m", "shortsmith.cli", "-c", str(c.project_root / "config.yaml"),
                     "generate"],
        "stitch":   [py, "-m", "shortsmith.cli", "-c", str(c.project_root / "config.yaml"),
                     "stitch"],
        "upload":   [py, "-m", "shortsmith.cli", "-c", str(c.project_root / "config.yaml"),
                     "upload", "--count", str(int(request.json.get("count", 1)) if request.is_json else 1)],
        "analyze":  [py, "-m", "shortsmith.cli", "-c", str(c.project_root / "config.yaml"),
                     "analyze"],
        "healthcheck": [py, "-m", "shortsmith.cli", "-c", str(c.project_root / "config.yaml"),
                        "healthcheck"],
    }
    if action not in actions:
        return jsonify({"error": "unknown action"}), 400
    job_id = _start_job(action, actions[action])
    return jsonify({"job_id": job_id})


@app.route("/api/job/<job_id>")
def api_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    return jsonify(job)


@app.route("/api/connect-youtube", methods=["POST"])
def api_connect_youtube():
    """Run upload --count 0 won't work; trigger auth via a dummy small flow.
    Simplest: spawn the CLI 'upload --count 1' as a background job with
    privacy=private, and let the user's browser do OAuth."""
    c = cfg()
    if not c.client_secret_path.exists():
        return jsonify({"error": "client_secret.json missing — see SETUP.md"}), 400
    py = sys.executable
    argv = [
        py, "-m", "shortsmith.cli", "-c", str(c.project_root / "config.yaml"),
        "upload", "--count", "1", "--privacy", "private",
    ]
    job_id = _start_job("connect", argv)
    return jsonify({"job_id": job_id, "note": "browser will open — sign in"})


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    c = cfg()
    cfg_path = c.project_root / "config.yaml"
    if request.method == "GET":
        return jsonify({"yaml": cfg_path.read_text() if cfg_path.exists() else ""})
    new_yaml = request.json.get("yaml", "")
    cfg_path.write_text(new_yaml)
    return jsonify({"ok": True, "note": "saved. some changes need a restart."})


def run(c: config.Config, host: str = "127.0.0.1", port: int = 8765) -> None:
    global _cfg
    _cfg = c
    print(f"shortsmith dashboard → http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
