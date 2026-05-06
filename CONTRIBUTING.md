# Contributing

Thanks for considering a contribution. This is a small project, so the rules are light.

## Quick rules

- **Open an issue before a big PR.** Drive-by 500-line refactors are likely to bounce.
- **Match the existing style.** Python: PEP8, type hints where they help, no aggressive abstractions. JS in the dashboard: vanilla, no build step.
- **Don't add dependencies casually.** Each new pip package is a maintenance burden. Justify it in the PR description.
- **Keep the surface area small.** Features that 90% of users won't touch belong in a fork or a downstream tool.

## Things I'll merge fast

- Linux cron equivalent of the launchd integration
- Better error messages (especially around OAuth and TCC)
- Bug fixes with a reproduction script
- Doc improvements
- Niche-specific example `hooks.json` files in `examples/`

## Things I'll think about

- TikTok / Instagram Reels uploaders
- Alternative caption styles
- LLM hook-generator built into the CLI
- Postgres / SQLite state instead of JSON files

## Things I'll likely reject

- Full rewrites in Rust / Go / TypeScript (you can fork, that's fine)
- "Enterprise" features (multi-user, RBAC, audit logs)
- Telemetry / analytics that phone home
- Closed-source dependencies

## Setup for development

```bash
git clone https://github.com/<you>/shortsmith.git
cd shortsmith
pip install -e .
pip install -r requirements.txt
```

Run the CLI from inside the repo:
```bash
python -m shortsmith.cli --help
```

## Testing

There are no tests yet. If you want to add some, start with `shortsmith.generate` (pure functions) and `shortsmith.upload.metadata_for` (no I/O). Use `pytest`.

## Code of conduct

Be reasonable. Be specific. Don't be a jerk in the issue tracker.
