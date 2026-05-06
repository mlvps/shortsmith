# Troubleshooting

## "Operation not permitted" in upload.err

macOS TCC blocking launchd from reading your project. Two fixes:

**Option A — grant Full Disk Access to python3** (recommended):
1. System Settings → Privacy & Security → Full Disk Access
2. Click **+** → press **⌘ Shift G** → type `/usr/bin/python3` → click Open
3. Toggle on
4. Restart the jobs: `shortsmith schedule uninstall && shortsmith schedule install`

**Option B — move the project**:
```bash
mv ~/Documents/my-campaign ~/projects/my-campaign
cd ~/projects/my-campaign
shortsmith schedule uninstall
shortsmith schedule install
```
TCC only protects `~/Documents`, `~/Desktop`, `~/Downloads`, iCloud Drive, Pictures, Movies, Music. Anywhere else is fine.

## yt-dlp: "Sign in to confirm you're not a bot"

YouTube's bot detection got triggered. Three fixes, in order of preference:

1. **Wait 30 minutes** — most rate-limits clear quickly
2. **Lower parallelism** — set `source.download_parallel: 1` in config and add `--sleep-interval 5 --max-sleep-interval 10`
3. **Pass cookies** — sign in to YouTube on Safari (or a supported browser), then:
   ```bash
   shortsmith download --cookies-browser safari
   ```

⚠ Sometimes cookies *trigger* a different rate limit on the account itself. If cookies make it worse, drop them.

## OAuth: "this app isn't verified"

You're in test mode. Click **Advanced** → **Go to {app name} (unsafe)** → Allow. This is fine — the OAuth scope is just YouTube upload, and you're the only test user.

To remove the warning permanently, you'd have to submit your app for Google verification (~weeks). Not worth it for personal use.

## "Quota exceeded" on upload

YouTube Data API free tier is 10,000 units/day. Each upload costs ~1,600 units, so you get ~6 uploads/day per Google Cloud project. At the default 3-uploads/day schedule, you're well under.

If you're hitting it: you've left old test uploads enabled or you've been retrying failed uploads. Check `uploaded.json` and clean up.

## Dashboard "Connect YouTube" button does nothing

The button calls `shortsmith upload --count 1 --privacy private` to trigger OAuth. If `client_secret.json` is missing, you'll see an error in the toast. Check `docs/SETUP.md` step 6.

## Videos render but audio is silent

`ffprobe ./final/final_0000.mp4` — if you see `codec_type=audio` listed but it's silent, your `template.mov` has no audio. ffmpeg will pad with silence; that's expected. If you want music, drop a track in your template before pulling it through generate.

## Stitched video has black bars

Your source short isn't 9:16. shortsmith's stitch step does `crop=cover` which will zoom-and-crop. If you want pad-with-blur instead, change `force_original_aspect_ratio=increase` to `decrease` in `shortsmith/stitch.py` and add a blurred-background overlay.

## launchd job not firing at scheduled time

```bash
launchctl list | grep com.shortsmith
```

If a job's PID column shows `-` and the exit-code column is non-zero, the job ran and crashed. Check `upload.err`.

If the job isn't listed: rerun `shortsmith schedule install`.

If the job is listed but fires at the wrong time: macOS waits for system wake before firing missed schedules. The Mac was asleep at the trigger time.

## Push notifications not arriving

1. Make sure the topic in `config.yaml` matches the topic you subscribed to in the app (case-sensitive).
2. Test directly: `curl -d "test" ntfy.sh/your-topic-name`
3. Some carriers throttle ntfy notifications when your phone is on cellular only — try Wi-Fi first.

## Hooks render with weird character spacing

Your font doesn't have certain glyphs. Try a different font path in `config.yaml`. `Arial Bold.ttf` is safe on macOS. On Linux, try `/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf`.

## More questions

Open an issue: https://github.com/<you>/shortsmith/issues
