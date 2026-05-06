"""Renders the end-clip variations from a template + hooks.json.

For each entry in hooks.json:
  1. Render hook PNG (transparent, black text).
  2. Render CTA PNG (transparent, with optional highlight backgrounds).
  3. ffmpeg pads template to width × height (white caption box on top),
     overlays hook → fades out, overlays CTA → fades in, trims, fades audio.
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import config


def wrap_plain(text: str, font, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for w in words:
        candidate = (current + " " + w).strip()
        if font.getlength(candidate) <= max_w:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def render_hook_png(text: str, out_path: Path, cfg: config.Config) -> None:
    box_w = cfg.get("caption", "box_width_px", default=1080)
    box_h = cfg.get("caption", "box_height_px", default=480)
    pad_x = cfg.get("caption", "padding_x_px", default=60)
    font_path = cfg.get("caption", "font_path")
    font_size = cfg.get("caption", "font_size", default=58)
    line_spacing = cfg.get("caption", "line_spacing_px", default=14)
    max_text_w = box_w - 2 * pad_x

    img = Image.new("RGBA", (box_w, box_h), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, font_size)
    lines = wrap_plain(text, font, max_text_w)

    bboxes = [font.getbbox(line) for line in lines]
    line_heights = [b[3] - b[1] for b in bboxes]
    total_h = sum(line_heights) + line_spacing * (len(lines) - 1)
    y = (box_h - total_h) // 2

    for line, b, lh in zip(lines, bboxes, line_heights):
        line_w = b[2] - b[0]
        x = (box_w - line_w) // 2 - b[0]
        draw.text((x, y - b[1]), line, fill=(0, 0, 0, 255), font=font)
        y += lh + line_spacing

    img.save(out_path)


def render_cta_png(segments: list[dict], out_path: Path, cfg: config.Config) -> None:
    """Segment-atomic layout: each segment renders verbatim. Highlight rect
    wraps the segment's stripped (whitespace-trimmed) text."""
    cta_suffix = cfg.get("cta_suffix", default="")
    if cta_suffix:
        segments = list(segments) + [{"text": cta_suffix}]

    box_w = cfg.get("caption", "box_width_px", default=1080)
    box_h = cfg.get("caption", "box_height_px", default=480)
    pad_x = cfg.get("caption", "padding_x_px", default=60)
    font_path = cfg.get("caption", "font_path")
    font_size = cfg.get("caption", "font_size", default=58)
    line_spacing = cfg.get("caption", "line_spacing_px", default=14)
    max_text_w = box_w - 2 * pad_x

    hl_pad_x = 12
    hl_pad_y = 6
    hl_radius = 14
    hl_colors_raw = cfg.get("highlight_colors", default={})
    hl_colors = {k: tuple(v) for k, v in hl_colors_raw.items()}

    img = Image.new("RGBA", (box_w, box_h), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, font_size)

    if not segments:
        img.save(out_path)
        return

    tokens = []
    for seg in segments:
        text = seg.get("text", "")
        hl = seg.get("hl")
        full_w = font.getlength(text)
        stripped = text.strip()
        leading = len(text) - len(text.lstrip())
        leading_w = font.getlength(text[:leading])
        stripped_w = font.getlength(stripped)
        tokens.append({
            "text": text, "hl": hl,
            "full_w": full_w, "stripped_w": stripped_w, "leading_w": leading_w,
        })

    lines: list[list[dict]] = [[]]
    line_widths: list[float] = [0.0]
    for t in tokens:
        cur_w = line_widths[-1]
        if cur_w + t["full_w"] <= max_text_w or cur_w == 0:
            lines[-1].append(t)
            line_widths[-1] = cur_w + t["full_w"]
        else:
            new_text = t["text"].lstrip()
            new_full_w = font.getlength(new_text)
            lines.append([{**t, "text": new_text, "full_w": new_full_w, "leading_w": 0.0}])
            line_widths.append(new_full_w)

    for line in lines:
        if line:
            last = line[-1]
            stripped_text = last["text"].rstrip()
            last["text"] = stripped_text
            last["full_w"] = font.getlength(stripped_text)
    line_widths = [sum(t["full_w"] for t in line) for line in lines]

    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    block_h = len(lines) * line_h + line_spacing * (len(lines) - 1)
    y = (box_h - block_h) // 2

    for line, lw in zip(lines, line_widths):
        x = (box_w - lw) // 2
        cursor = x
        for t in line:
            if t["hl"] in hl_colors:
                rect_x0 = cursor + t["leading_w"] - hl_pad_x
                rect_x1 = cursor + t["leading_w"] + t["stripped_w"] + hl_pad_x
                color = hl_colors[t["hl"]]
                draw.rounded_rectangle(
                    [rect_x0, y - hl_pad_y, rect_x1, y + line_h + hl_pad_y],
                    radius=hl_radius, fill=color + (255,),
                )
            cursor += t["full_w"]
        cursor = x
        for t in line:
            draw.text((cursor, y), t["text"], fill=(0, 0, 0, 255), font=font)
            cursor += t["full_w"]
        y += line_h + line_spacing

    img.save(out_path)


def render(idx: int, hook: str, cta_segments: list[dict], cfg: config.Config) -> Path:
    out_w = cfg.get("output", "width", default=1080)
    out_h = cfg.get("output", "height", default=1920)
    fps = cfg.get("output", "fps", default=30)
    box_h = cfg.get("caption", "box_height_px", default=480)
    box_w = cfg.get("caption", "box_width_px", default=1080)
    hook_fade_start = cfg.get("output", "hook_fade_start", default=2.3)
    hook_fade_dur = cfg.get("output", "hook_fade_duration", default=0.2)
    cta_fade_start = cfg.get("output", "cta_fade_start", default=2.3)
    cta_fade_dur = cfg.get("output", "cta_fade_duration", default=0.2)
    clip_dur = cfg.get("template", "duration_seconds", default=5.5)
    audio_fade_start = cfg.get("output", "audio_fade_out_start", default=5.0)
    audio_fade_dur = cfg.get("output", "audio_fade_out_duration", default=0.5)

    out_path = cfg.out_dir / f"clip_{idx:04d}.mp4"
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    cta_preview = "".join(s.get("text", "") for s in cta_segments)

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        hook_png = tdp / "hook.png"
        cta_png = tdp / "cta.png"
        render_hook_png(hook, hook_png, cfg)
        render_cta_png(cta_segments, cta_png, cfg)

        filter_complex = (
            f"[0:v]pad={out_w}:{out_h}:0:{box_h}:white[bg];"
            f"[1:v]format=rgba,fade=t=out:st={hook_fade_start}:d={hook_fade_dur}:alpha=1[hook];"
            f"[2:v]format=rgba,fade=t=in:st={cta_fade_start}:d={cta_fade_dur}:alpha=1[cta];"
            f"[bg][hook]overlay=0:0[a];"
            f"[a][cta]overlay=0:0,trim=duration={clip_dur},setpts=PTS-STARTPTS[v];"
            f"[0:a]atrim=duration={clip_dur},asetpts=PTS-STARTPTS,"
            f"afade=t=out:st={audio_fade_start}:d={audio_fade_dur}[a]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", str(cfg.template_path),
            "-loop", "1", "-framerate", str(fps), "-i", str(hook_png),
            "-loop", "1", "-framerate", str(fps), "-i", str(cta_png),
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            "-t", str(clip_dur),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            str(out_path),
        ]
        print(f"[{idx:04d}] hook={hook!r}")
        print(f"[{idx:04d}] cta={cta_preview!r}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(res.stderr[-2000:], file=sys.stderr)
            raise SystemExit(f"ffmpeg failed for idx={idx}")
    return out_path


def main(cfg: config.Config, args: argparse.Namespace) -> None:
    if not cfg.template_path.exists():
        raise SystemExit(f"template missing: {cfg.template_path}")
    if not cfg.hooks_path.exists():
        raise SystemExit(f"hooks file missing: {cfg.hooks_path}")

    data = json.loads(cfg.hooks_path.read_text())
    end = args.end if args.end is not None else len(data)
    if args.limit is not None:
        end = min(end, args.start + args.limit)

    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    for i in range(args.start, end):
        entry = data[i]
        render(i, entry["hook"], entry["cta_segments"], cfg)

    print(f"done: {end - args.start} clips in {cfg.out_dir}")
