"""Hook generator that uses your existing LLM CLI.

No API key required. shortsmith spawns whichever LLM CLI you already have
installed and pipes a hook-generation prompt into it. Supported:

  - Claude Code         claude -p "<prompt>"
  - OpenAI Codex CLI    codex exec "<prompt>"
  - Google Gemini CLI   gemini "<prompt>"
  - Ollama (local)      ollama run <model> "<prompt>"

If multiple are installed, you can pick with --provider. Default is auto:
prefer Claude > Codex > Gemini > Ollama.

The output JSON is appended to or replaces hooks.json. Validation runs before
writing so you don't overwrite a good file with garbage.
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import config

PROMPT_TEMPLATE = """You write hook + CTA pairs for an automated TikTok / YouTube Shorts campaign.

# Output

Return ONLY a JSON array. No prose, no markdown fences, no explanation. Just JSON.

Each entry MUST be:

{{
  "hook": "string",
  "cta_segments": [
    {{"text": "string"}},
    {{"text": "string", "hl": "yellow|green|purple"}}
  ]
}}

# Hook rules

- All lowercase, no exceptions.
- NO em-dashes anywhere.
- Gen-Z TikTok voice. Slang OK ("bro", "lowkey", "ngl", "fr", "no shot", "you cooked").
- {shame_angle}
- Punchy, not whiny. Under 90 chars where possible.
- Variety: don't repeat phrases. Mix questions, statements, callouts.
- Tied to: {theme}

# CTA rules

- Short and provocative, 4 to 9 words.
- All lowercase, no em-dashes.
- Must thematically tie to the hook.
- Vary the verbs (track, log, lock in, stop coping, fix it, dial in, hit your stack).
- ALWAYS reference the brand name "{brand}" somewhere, usually highlighted purple.
- Highlight 1 or 2 important words per CTA via "hl":
  - "yellow" = power verbs / commands (track, log, lock in)
  - "green" = aspirational outcomes (get shredded, lean, ripped)
  - "purple" = always the brand name
- Do NOT include leading or trailing punctuation/whitespace inside an "hl" segment.
- shortsmith auto-appends "{cta_suffix}" after every CTA. Do NOT include it in cta_segments.

# Examples

[
  {{
    "hook": "okay but you forgot you wanted to be shredded by summer",
    "cta_segments": [
      {{"text": "stop coping. "}},
      {{"text": "track", "hl": "yellow"}},
      {{"text": " your peptides with "}},
      {{"text": "{brand}", "hl": "purple"}}
    ]
  }}
]

# Task

Generate exactly {count} entries. Output ONLY the JSON array. Begin with `[` and end with `]`.
"""

PROVIDERS = ["claude", "codex", "gemini", "ollama"]


def detect_provider() -> str | None:
    """Return the first available provider, or None if none installed."""
    for p in PROVIDERS:
        if shutil.which(p):
            return p
    return None


def installed_providers() -> list[str]:
    return [p for p in PROVIDERS if shutil.which(p)]


def build_prompt(count: int, product: str, theme: str, brand: str,
                 cta_suffix: str) -> str:
    shame_angle_map = {
        "fitness": "Body-shame angle. Make the user feel a tiny pang. Punchy not whiny.",
        "finance": "Finance-shame angle. Wasted money, missed compound interest, broke energy.",
        "productivity": "Productivity-shame angle. Wasted time, no progress, scrolling instead of doing.",
        "habit": "Habit-shame angle. Discipline they keep promising. Streaks they keep breaking.",
    }
    # Default: try to infer from theme keywords
    s = theme.lower()
    if any(w in s for w in ["body", "abs", "shred", "lean", "summer", "fitness", "peptide"]):
        shame = shame_angle_map["fitness"]
    elif any(w in s for w in ["money", "finance", "broke", "rich", "save", "invest"]):
        shame = shame_angle_map["finance"]
    elif any(w in s for w in ["focus", "deep work", "productive", "time"]):
        shame = shame_angle_map["productivity"]
    elif any(w in s for w in ["habit", "streak", "discipline", "morning"]):
        shame = shame_angle_map["habit"]
    else:
        shame = "Make the user feel a tiny pang of regret about their current state."
    return PROMPT_TEMPLATE.format(
        count=count, theme=theme, brand=brand,
        cta_suffix=cta_suffix, shame_angle=shame,
    )


def run_provider(provider: str, prompt: str, model: str | None = None,
                 timeout: int = 600) -> str:
    if provider == "claude":
        cmd = ["claude", "-p", prompt]
    elif provider == "codex":
        cmd = ["codex", "exec", prompt]
    elif provider == "gemini":
        cmd = ["gemini", prompt]
    elif provider == "ollama":
        m = model or "llama3.1"
        cmd = ["ollama", "run", m, prompt]
    else:
        raise SystemExit(f"unknown provider: {provider}")

    print(f"running: {provider} (this can take 1-3 minutes for 100 hooks)", flush=True)
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if res.returncode != 0:
        print(res.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"{provider} failed (exit {res.returncode})")
    return res.stdout


def extract_json_array(raw: str) -> list:
    """Pull a JSON array out of LLM output. Handles markdown fences, prose,
    leading/trailing text. Raises ValueError if no array found."""
    # Try the easy case first.
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass
    # Strip markdown fences.
    fence_match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", raw)
    if fence_match:
        return json.loads(fence_match.group(1))
    # Find the first '[' and last ']' and try that span.
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        return json.loads(raw[start:end + 1])
    raise ValueError("no JSON array found in output")


def validate(entries: list) -> list:
    """Discard malformed entries, return clean list."""
    valid_hl = {"yellow", "green", "purple"}
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        hook = e.get("hook")
        segs = e.get("cta_segments")
        if not isinstance(hook, str) or not isinstance(segs, list) or not segs:
            continue
        clean_segs = []
        ok = True
        for s in segs:
            if not isinstance(s, dict) or "text" not in s:
                ok = False
                break
            seg = {"text": str(s["text"])}
            hl = s.get("hl")
            if hl is not None:
                if hl not in valid_hl:
                    continue
                seg["hl"] = hl
            clean_segs.append(seg)
        if not ok or not clean_segs:
            continue
        # Strip em-dashes and force lowercase on hook
        hook_clean = hook.lower().replace("—", ",").replace("–", ",").strip()
        out.append({"hook": hook_clean, "cta_segments": clean_segs})
    return out


def main(cfg: config.Config, args: argparse.Namespace) -> None:
    available = installed_providers()
    if not available:
        raise SystemExit(
            "No LLM CLI found. Install one (free with your existing subscription):\n"
            "  Claude Code:  https://claude.ai/code        # uses your Claude Pro/Max plan\n"
            "  Codex CLI:    npm i -g @openai/codex        # uses your ChatGPT Plus plan\n"
            "  Gemini CLI:   npm i -g @google/gemini-cli   # uses your Google AI Studio key\n"
            "  Ollama:       https://ollama.com/download   # runs local, fully offline\n"
        )

    provider = args.provider
    if provider == "auto":
        provider = available[0]
    elif provider not in available:
        raise SystemExit(
            f"--provider {provider} not installed. Available: {', '.join(available) or '(none)'}"
        )

    cta_suffix = (cfg.get("cta_suffix", default="") or "").strip()
    prompt = build_prompt(
        count=args.count,
        product=args.product or "your app",
        theme=args.theme or "your campaign theme",
        brand=args.brand or "your brand",
        cta_suffix=cta_suffix,
    )

    raw = run_provider(provider, prompt, model=args.model)
    print(f"received {len(raw)} chars", flush=True)

    try:
        parsed = extract_json_array(raw)
    except (ValueError, json.JSONDecodeError) as e:
        debug_path = cfg.project_root / "llm_raw_output.txt"
        debug_path.write_text(raw)
        raise SystemExit(
            f"could not parse JSON from {provider} output: {e}\n"
            f"raw output saved to {debug_path} for inspection."
        )

    cleaned = validate(parsed)
    if not cleaned:
        debug_path = cfg.project_root / "llm_raw_output.txt"
        debug_path.write_text(raw)
        raise SystemExit(
            f"all {len(parsed)} entries failed validation. raw saved to {debug_path}"
        )

    if args.append and cfg.hooks_path.exists():
        existing = json.loads(cfg.hooks_path.read_text())
        merged = existing + cleaned
        cfg.hooks_path.write_text(json.dumps(merged, indent=2))
        print(f"appended {len(cleaned)} entries (kept {len(parsed) - len(cleaned)} dropped). "
              f"total: {len(merged)} in {cfg.hooks_path}")
    else:
        cfg.hooks_path.write_text(json.dumps(cleaned, indent=2))
        print(f"wrote {len(cleaned)} entries (kept {len(parsed) - len(cleaned)} dropped) "
              f"to {cfg.hooks_path}")
