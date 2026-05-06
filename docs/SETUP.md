# Setup guide

End-to-end setup, ~15 minutes if you've done OAuth before, ~30 if you haven't.

## 1. Install dependencies

### macOS
```bash
brew install ffmpeg yt-dlp python@3.11
pip3 install -r requirements.txt
```

### Linux (Debian/Ubuntu)
```bash
sudo apt update
sudo apt install ffmpeg python3 python3-pip cron
pipx install yt-dlp     # or:  python3 -m pip install --user yt-dlp
pip3 install -r requirements.txt
```

### Windows
Install [Python 3.11+](https://www.python.org/downloads/), [Chocolatey](https://chocolatey.org/install) (recommended), then:
```powershell
choco install ffmpeg yt-dlp
pip install -r requirements.txt
```
Or install ffmpeg/yt-dlp manually and ensure both are on PATH.

ffmpeg must be on your PATH. Check with `which ffmpeg` (macOS/Linux) or `where ffmpeg` (Windows).

## 2. Scaffold a project

```bash
mkdir ~/my-campaign
cd ~/my-campaign
shortsmith init
```

This creates `config.yaml`, `hooks.json` example, and the directory tree.

## 3. Drop in your end-clip

Save your raw end-clip to `./template/template.mov` (or whatever you set in config). Roughly 5-8 seconds. shortsmith will pad anything narrower than 9:16 with a white caption box on top.

## 4. Generate your hooks

shortsmith uses your existing LLM CLI subscription (no API key needed). Install whichever you already pay for:

| Provider | Install | Backed by |
|---|---|---|
| Claude Code | https://claude.ai/code | Claude Pro / Max plan |
| OpenAI Codex CLI | `npm i -g @openai/codex` | ChatGPT Plus plan |
| Google Gemini CLI | `npm i -g @google/gemini-cli` | Google AI Studio key |
| Ollama | https://ollama.com/download | Fully local, offline |

Then generate:

```bash
shortsmith hooks --count 100 \
  --brand "bo" \
  --theme "summer body, abs by june" \
  --product "a peptide tracking app"
```

`--provider auto` (default) picks the first installed CLI. Override with `--provider claude|codex|gemini|ollama` if you want a specific one.

Output goes to `hooks.json`. shortsmith parses + validates the LLM output before writing. Bad entries are dropped silently.

You can also trigger this from the dashboard: **Generate hooks** button opens a form (brand, theme, count, provider).

### Manual hooks

If you'd rather write hooks by hand, edit `hooks.json` directly. Each entry:

```json
{
  "hook": "okay but you forgot you wanted to be shredded by summer",
  "cta_segments": [
    {"text": "stop coping. "},
    {"text": "track", "hl": "yellow"},
    {"text": " your peptides with "},
    {"text": "bo", "hl": "purple"}
  ]
}
```

Rules:
- All lowercase, no em-dashes, Gen-Z TikTok voice
- `hl` values come from `highlight_colors` in `config.yaml` (default: yellow/green/purple)
- The renderer auto-appends `cta_suffix` from config (e.g., `(it's on the app store)`)
- Punctuation goes in the unhighlighted "connector" segments, never inside an `hl` segment

See `examples/hooks_example.json` for ~10 templates you can adapt.

## 5. Edit `config.yaml`

Set:
- `source.channel_url`, the channel whose Shorts you'll use as hooks
- `caption.font_path`, point to a TTF on your system (default works on macOS)
- `highlight_colors`, your brand colors as `[R, G, B]`
- `cta_suffix`, your call-to-action footer
- `upload.schedule_hours`, when to post each day
- `ntfy.topic`, for push notifications (optional)

## 6. YouTube OAuth credentials

shortsmith uploads via the YouTube Data API. Free tier covers 6 uploads/day per project.

### Create the OAuth client

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → create a new project (or pick an existing one)
2. **APIs & Services → Library** → search "YouTube Data API v3" → **Enable**
3. **APIs & Services → OAuth consent screen**:
   - User type: **External**
   - App name: anything (e.g. "shortsmith")
   - User support + developer email: yours
   - Add yourself as a **Test user** (the email tied to your YouTube channel)
4. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Type: **Desktop app**
   - Name: anything
   - Click **Create** → **Download JSON**
5. Move the JSON to `./client_secret.json`:

```bash
mv ~/Downloads/client_secret_*.json ./client_secret.json
```

### First-time auth

```bash
shortsmith upload --count 1 --privacy private
```

A browser window opens. Sign in with the Google account that owns your YouTube channel, click **Allow**. A `token.json` is saved, you won't be prompted again.

The first test upload posts as private. Verify it on your channel; delete if you want.

## 7. Install the schedule

```bash
shortsmith schedule install
```

shortsmith detects your OS and installs the right scheduler:

- **macOS** → three launchd plists in `~/Library/LaunchAgents/`. Verify with `launchctl list | grep com.shortsmith`.
- **Linux** → cron entries in your user crontab inside a `# >>> shortsmith managed >>>` block. Verify with `crontab -l`.
- **Windows** → tasks in Task Scheduler prefixed `shortsmith_*`. Verify with `schtasks /Query | findstr shortsmith`.

You should see three job entries either way (1 daily upload + 1 weekly analyze + 1 weekly health check).

### macOS Full Disk Access (important, macOS only)

If your project lives in `~/Documents/`, `~/Desktop/`, or `~/Downloads/`, macOS TCC will block launchd from reading your Python scripts. You'll see "Operation not permitted" in `upload.err`.

**Fix:** System Settings → Privacy & Security → Full Disk Access → click **+** → press **⌘ Shift G** → type `/usr/bin/python3` → toggle on. Restart the jobs:

```bash
shortsmith schedule uninstall && shortsmith schedule install
```

Or move the project outside protected folders (`~/projects/my-campaign`), TCC doesn't gate non-Documents paths.

### Linux: machine must be running at trigger times

Cron only fires while the machine is on. For a 24/7 schedule, run shortsmith on a small VPS or a Raspberry Pi that's always up.

### Windows: "Run only when user is logged on"

Tasks created by `schtasks` default to running only while you're signed in. To run while logged out, edit the task in Task Scheduler GUI → check **Run whether user is logged on or not** and provide your password.

## 8. (Optional) Push notifications

1. Install the [ntfy app](https://ntfy.sh/app) on your phone
2. Pick an unguessable topic name (e.g. `shortsmith-yourname-7k9q2x`)
3. In the app: tap **+** → enter your topic → subscribe
4. Add it to `config.yaml`:
   ```yaml
   ntfy:
     topic: "shortsmith-yourname-7k9q2x"
   ```
5. Test: `shortsmith healthcheck`, you should get a push within a few seconds

## 9. Done

Open the dashboard:

```bash
shortsmith dashboard
```

Visit `http://127.0.0.1:8765`. You'll see counts, recent uploads, live logs, and a button for every action.

---

**Stuck?** See [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
