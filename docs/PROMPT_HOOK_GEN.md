# Hook generation prompt

Paste this into Claude / GPT-4 / any decent LLM to generate hooks for your campaign. Adjust the bracketed sections to match your product.

```
Write 100 hook+CTA pairs for a TikTok body-transformation campaign for [YOUR PRODUCT — e.g., "a peptide tracking app called Bo"]. Each pair will be stitched onto a viral short and posted to TikTok/YouTube Shorts.

Output format: a JSON array. Each entry MUST be:

{
  "hook": "string",
  "cta_segments": [
    {"text": "string"},
    {"text": "string", "hl": "yellow|green|purple"},
    ...
  ]
}

The renderer auto-appends "[YOUR CTA SUFFIX, e.g., ' (it's on the app store)']" to every CTA. Do NOT include that in cta_segments.

# Hook rules
- All lowercase, no exceptions
- NO em-dashes (—) anywhere
- Gen-Z TikTok voice — slang OK ("bro", "lowkey", "ngl", "fr", "no shot", "you cooked")
- Body-shame angle for fitness, finance-shame for money apps, productivity-shame for habit apps — make the user feel a tiny pang
- Punchy, not whiny — under 90 chars where possible
- Variety: don't repeat phrases. Mix questions, statements, callouts.
- Tied to [YOUR THEME — e.g., "summer body, looking shredded, abs by june"]

# CTA rules
- Short and provocative — 4 to 9 words before the auto-suffix
- All lowercase, no em-dashes
- Must thematically tie to the hook
- Vary the verbs: track, log, lock in, stop coping, fix it, dial in, hit your stack
- ALWAYS reference your brand name somewhere — usually highlighted purple
- Highlight 1 or 2 important words per CTA via "hl":
  - "yellow" = power verbs / commands (track, log, lock in)
  - "green" = aspirational outcomes (get shredded, lean, ripped)
  - "purple" = always your brand name
- Each cta_segments list typically has 3-5 segments. Connecting words go in unhighlighted segments.
- DO NOT include leading or trailing punctuation/whitespace inside an "hl" segment. Highlights wrap exactly the words you want a colored box around.

# Example
[
  {
    "hook": "okay but you forgot you wanted to be shredded by summer",
    "cta_segments": [
      {"text": "stop coping. "},
      {"text": "track", "hl": "yellow"},
      {"text": " your peptides with "},
      {"text": "bo", "hl": "purple"}
    ]
  }
]

Output ONLY valid JSON. No prose. No markdown fences. Just the array.
Generate 100 entries.
```

## Tips

- Generate in batches of 100. Most LLMs degrade after that point.
- Use a model with strong JSON discipline (Claude Sonnet, GPT-4o, Gemini Pro).
- Validate before saving:
  ```bash
  python3 -c "import json; print(len(json.load(open('hooks.json'))))"
  ```
- Manually skim 10-20 entries for quality before generating the full set. If the LLM is producing weak hooks, tweak the example or add more constraints.
