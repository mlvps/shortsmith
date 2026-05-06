"""Stitches source shorts (first N seconds) + your end-clip → final videos."""
from __future__ import annotations
import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

from . import config


def stitch_one(idx: int, source_path: Path, clip_path: Path, out_path: Path,
               cfg: config.Config) -> None:
    w = cfg.get("output", "width", default=1080)
    h = cfg.get("output", "height", default=1920)
    fps = cfg.get("output", "fps", default=30)
    source_trim = cfg.get("template", "duration_seconds", default=5.5)

    norm = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},setsar=1,fps={fps},format=yuv420p"
    )
    fc = (
        f"[0:v]trim=duration={source_trim},setpts=PTS-STARTPTS,{norm}[v0];"
        f"[0:a]atrim=duration={source_trim},asetpts=PTS-STARTPTS,"
        f"aformat=sample_rates=44100:channel_layouts=stereo[a0];"
        f"[1:v]{norm}[v1];"
        f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo[a1];"
        f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(source_path),
        "-i", str(clip_path),
        "-filter_complex", fc,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"ffmpeg failed for idx={idx}")


def main(cfg: config.Config, args: argparse.Namespace) -> None:
    cfg.final_dir.mkdir(parents=True, exist_ok=True)
    sources = sorted(cfg.source_dir.glob("*.mp4"))
    clips = sorted(cfg.out_dir.glob("clip_*.mp4"))
    if not sources or not clips:
        raise SystemExit(
            f"need both: sources in {cfg.source_dir} and clips in {cfg.out_dir}"
        )

    n = min(len(sources), len(clips))
    rng = random.Random(args.seed)
    clip_order = list(range(len(clips)))
    rng.shuffle(clip_order)

    pairings = [
        {"idx": i, "source": sources[i].name, "clip": clips[clip_order[i]].name}
        for i in range(n)
    ]
    pairings_path = cfg.project_root / "pairings.json"
    pairings_path.write_text(json.dumps(pairings, indent=2))

    end = args.end if args.end is not None else n
    if args.limit is not None:
        end = min(end, args.start + args.limit)

    for i in range(args.start, end):
        p = pairings[i]
        out = cfg.final_dir / f"final_{i:04d}.mp4"
        print(f"[{i:04d}] {p['source']} + {p['clip']} → {out.name}")
        stitch_one(i, cfg.source_dir / p["source"], cfg.out_dir / p["clip"], out, cfg)

    print(f"done: {end - args.start} videos in {cfg.final_dir}")
