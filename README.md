# Matrix Dice Roller Bot 🎲

A Matrix/Synapse bot that rolls dice and sends back images of each die face.

## Commands

| Command | Description |
|---------|-------------|
| `!roll <expression>` | Roll dice (with images) |
| `!roll <expression> textonly` | Roll dice (text only, no images) |
| `!roll help` or `!roll ?` | Show help |
| `!dice` or `!dice help` | Show help |
| `!roll` (no args) | Roll 1d20 |

## Supported Dice

### Standard Dice (d2–d20)
```
!roll 3d20             rolls 3 twenty-sided dice
!roll 2d6 1d8          rolls 2d6 and 1d8
!roll d4               rolls 1d4
!roll 10d10            rolls 10d10
```
Any die from d2 through d100 is accepted (d2–d20 get unique colors/shapes).

### Star Wars FFG Dice

Three syntax options — all equivalent:

**By name:**
```
!roll 2boost 1ability 1difficulty
```

**Compact (d + letter):**
```
!roll 2db 1da 1dd
```

**By color (case-sensitive):**
```
!roll 2B 1g 1p
```

| Die          | Name Code | Color Code | Sides | Color  |
|-------------|-----------|------------|-------|--------|
| Boost       | b (db)    | B (Blue)   | d6    | Blue   |
| Setback     | s (ds)    | b (black)  | d6    | Black  |
| Ability     | a (da)    | g (green)  | d8    | Green  |
| Difficulty  | d (dd)    | p (purple) | d8    | Purple |
| Proficiency | p (dp)    | y (yellow) | d12   | Yellow |
| Challenge   | c (dc)    | r (red)    | d12   | Red    |
| Force       | f (df)    | w (white)  | d12   | White  |

**Note:** `B` (uppercase) = Blue/Boost, `b` (lowercase) = black/Setback.

### FFG Result Summary

FFG rolls produce a detailed summary showing:
- Each die's individual result
- Raw totals before cancellation
- Net results after Success/Failure and Advantage/Threat cancel
- An overall verdict (SUCCESS, FAILURE, or WASH) with modifiers

Example output for `!roll 2g 1p`:
```
── FFG Summary ──
Rolled: 2 Ability, 1 Difficulty
  Ability: Su
  Ability: Su Ad
  Difficulty: Th
Raw totals: 2 Success, 1 Advantage, 1 Threat
Net: 2 Success
Verdict: ✅ SUCCESS
```

### Text-Only Mode

Add `textonly` anywhere in the expression to suppress dice images:
```
!roll 3d20 textonly
!roll 2B 1g textonly
```

### Mixed Rolls
```
!roll 2d6 1B 1g
!roll 2d6 1ability 1difficulty textonly
```

### Limits
Maximum 50 dice per roll.

## Deployment

### 1. Create a bot account on your Synapse server
```bash
register_new_matrix_user -c /path/to/homeserver.yaml -u dicebot -p YOUR_PASSWORD
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env with your homeserver URL, bot user, and password
```

**No room ID needed.** The bot auto-joins rooms when invited and responds
in whichever room it receives a message from. Matrix bots discover rooms
via the sync API — no room configuration required.

### 3. Build and run with Podman
```bash
podman build -t dice-bot .

# First run (creates a named volume for cache persistence):
podman run -d --name dice-bot \
  --env-file .env \
  -v dice-bot-data:/app/data \
  --restart unless-stopped \
  dice-bot
```

**Important:** The `-v dice-bot-data:/app/data` volume mount persists the
mxc:// image cache across container restarts.  Without it, the bot re-uploads
all 273 dice images on every restart (~30-60 seconds).  With it, subsequent
restarts are near-instant.

### 4. Invite the bot to a room
In your Matrix client, invite `@dicebot:example.com` to any room.

### 5. Roll!
```
!roll 3d20
!dice help
```

## Architecture

```
bot.py                    – Event loop, parsing, Matrix I/O, cache management
ffg_dice.py               – FFG die face tables, rolling, netting, summaries
dice_image_gen.py         – Pillow-based image rendering (standard + FFG)
generate_dice_images.py   – Offline script to pre-generate all PNGs to disk
Containerfile             – Podman/Docker build (runs generation at build time)
assets/                   – Pre-generated PNGs (created at build time)
  std/                    – d2_1.png … d20_20.png  (209 files)
  ffg/                    – boost_f0.png … force_f11.png  (64 files)
```

### Image Pipeline

**Stage 1 — Build time: `generate_dice_images.py`**
The Containerfile runs `generate_dice_images.py` during `podman build`.  This
renders every possible die face (273 total: 209 standard + 64 FFG) to PNG files
in `assets/`.  The images are baked into the container image.

**Stage 2 — First startup: upload + cache**
On first boot, the bot reads every PNG from `assets/`, uploads them to the
Matrix homeserver's media repository, and stores the returned `mxc://` URIs
in `mxc_cache.json`.  This takes ~30-60 seconds.

**Stage 3 — Subsequent startups: cache load**
On restart, the bot loads `mxc_cache.json` from the volume.  If all 273
entries are present, it skips uploading entirely — startup is near-instant.
If entries are missing (e.g. new dice added), only the missing images are
uploaded.

**Stage 4 — Runtime: pure cache lookup**
Every `!roll` is a dict lookup of `mxc://` URIs, then a single Matrix message
send.  No rendering, no uploading.

### Why Not Look Up Old mxc:// URIs?

Matrix's media API does not provide a way to list or search previously
uploaded files.  When you upload, you get an `mxc://` URI back — but there's
no "list my uploads" or "find by filename" endpoint.  So the bot must either
re-upload on every restart, or persist the URI mapping to disk.  We do the
latter via `mxc_cache.json`.

### Regenerating Images

To regenerate images locally (e.g. after changing colors or shapes):
```bash
pip install Pillow
python generate_dice_images.py --output-dir assets
```

Then rebuild the container and delete the old cache volume:
```bash
podman volume rm dice-bot-data
podman build -t dice-bot .
# Re-run as in step 3 above
```

## Logs
```bash
podman logs -f dice-bot
```

First startup:
```
[INFO] dice-bot: Loading image cache …
[INFO] dice-bot: Cache has 0/273 entries — uploading missing images …
[INFO] dice-bot: Uploaded 273 new images (0 failed). Cache now has 273 entries.
[INFO] dice-bot: Cache saved to /app/data/mxc_cache.json (273 entries)
[INFO] dice-bot: Image cache ready: 273 entries
[INFO] dice-bot: Ready — listening for !roll and !dice commands …
```

Subsequent startup (with volume):
```
[INFO] dice-bot: Loading image cache …
[INFO] dice-bot: Cache loaded from disk: 273 entries — skipping uploads
[INFO] dice-bot: Image cache ready: 273 entries
[INFO] dice-bot: Ready — listening for !roll and !dice commands …
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Bot doesn't respond | Check it's invited to the room and `!roll` prefix matches |
| Login fails | Verify credentials in `.env`; check homeserver URL is reachable from container |
| Images don't render | Some clients don't inline `<img>` in m.text; use `textonly` flag, or text fallback still works |
| Slow first startup | Normal — 273 images uploading. Mount `/app/data` volume to avoid this on restarts |
| Cache stale after image changes | Delete the volume: `podman volume rm dice-bot-data` and restart |
| Font rendering ugly | Ensure `fonts-dejavu-core` installed (handled by Containerfile) |