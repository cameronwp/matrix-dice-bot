#!/usr/bin/env python3
"""
Matrix Dice Roller Bot
Supports standard dice (d2-d20) and Star Wars FFG dice.
Pre-uploads dice face PNGs at startup and persists the mxc:// cache to disk
so subsequent restarts skip uploading entirely.
"""

import asyncio
import json
import logging
import os
import re
import random
import sys
from io import BytesIO
from dataclasses import dataclass, field
from typing import Optional

from nio import (
    AsyncClient,
    LoginResponse,
    RoomMessageText,
    UploadResponse,
)

from ffg_dice import (
    FFG_DICE,
    FFGResult,
    roll_ffg_die,
    net_ffg_results,
    format_ffg_results,
    format_ffg_summary,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("dice-bot")

# ── Configuration via environment ────────────────────────────────────────────
HOMESERVER = os.environ.get("MATRIX_HOMESERVER", "http://localhost:8008")
BOT_USER = os.environ.get("MATRIX_BOT_USER", "@dicebot:localhost")
BOT_PASSWORD = os.environ.get("MATRIX_BOT_PASSWORD", "changeme")
COMMAND_PREFIX = os.environ.get("COMMAND_PREFIX", "!roll")
HELP_PREFIX = os.environ.get("HELP_PREFIX", "!dice")
DEVICE_NAME = os.environ.get("DEVICE_NAME", "DiceBot")
ASSETS_DIR = os.environ.get("ASSETS_DIR", "/app/assets")
CACHE_FILE = os.environ.get("CACHE_FILE", "/app/data/mxc_cache.json")

# ── Image cache ──────────────────────────────────────────────────────────────
# In-memory dict:  string key → mxc:// URI
# Keys are strings like "std:20:17" or "ffg:boost:3" (JSON-friendly).
# Persisted to CACHE_FILE so restarts don't require re-uploading.

_image_cache: dict[str, str] = {}

EXPECTED_CACHE_SIZE = 273  # 209 standard (d2-d20) + 64 FFG


def _std_cache_key(sides: int, value: int) -> str:
    return f"std:{sides}:{value}"


def _ffg_cache_key(die_name: str, face_index: int) -> str:
    return f"ffg:{die_name}:{face_index}"


def _load_cache_from_disk() -> int:
    """Load persisted mxc:// cache from JSON file. Returns count loaded."""
    global _image_cache
    if not os.path.isfile(CACHE_FILE):
        return 0
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return 0
        _image_cache = data
        return len(_image_cache)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Could not load cache file %s: %s", CACHE_FILE, e)
        return 0


def _save_cache_to_disk() -> None:
    """Persist the current mxc:// cache to JSON file."""
    cache_dir = os.path.dirname(CACHE_FILE)
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(_image_cache, f, indent=1)
        log.info("Cache saved to %s (%d entries)", CACHE_FILE, len(_image_cache))
    except OSError as e:
        log.error("Failed to save cache to %s: %s", CACHE_FILE, e)


# ── Help text ────────────────────────────────────────────────────────────────
HELP_TEXT_PLAIN = """\
🎲 Dice Roller Bot — Help

COMMANDS
  !roll <expression>             Roll dice (with images)
  !roll <expression> textonly    Roll dice (text only, no images)
  !roll help                     This help message
  !dice / !dice help             This help message

STANDARD DICE (d2 – d20)
  !roll d20             Roll 1d20
  !roll 3d20            Roll 3 twenty-sided dice
  !roll 2d6 1d8         Roll 2d6 and 1d8
  !roll 4d6 d20 d4      Mix and match

STAR WARS FFG DICE — by name
  !roll 2boost 1ability 1difficulty
  !roll 1proficiency 1challenge
  !roll 2force

STAR WARS FFG DICE — compact (d + letter)
  !roll 2db 1da 1dd     2 Boost, 1 Ability, 1 Difficulty
  !roll 1dp 1dc         1 Proficiency, 1 Challenge
  !roll 2df             2 Force

STAR WARS FFG DICE — by color (case-sensitive!)
  B = Blue (Boost)       b = black (Setback)
  g = green (Ability)    p = purple (Difficulty)
  y = yellow (Prof.)     r = red (Challenge)
  w = white (Force)

  !roll 1B 2g            1 Boost, 2 Ability
  !roll 3b 1r            3 Setback, 1 Challenge
  !roll 1y 1p 2w         1 Proficiency, 1 Difficulty, 2 Force

MIXED ROLLS
  !roll 2d6 1B 1g        Standard + FFG together

TEXT-ONLY MODE
  !roll 3d20 textonly    Show only text results, no dice images

LIMITS
  Maximum 50 dice per roll.  Standard dice d2–d100 accepted.\
"""

HELP_TEXT_HTML = (
    HELP_TEXT_PLAIN.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
)
HELP_TEXT_HTML = "<pre>" + HELP_TEXT_HTML + "</pre>"


# ── Dice expression parsing ──────────────────────────────────────────────────
STANDARD_RE = re.compile(r"(\d*)d(\d+)", re.IGNORECASE)

FFG_RE = re.compile(
    r"(\d*)(boost|ability|proficiency|setback|difficulty|challenge|force)",
    re.IGNORECASE,
)

FFG_COMPACT_RE = re.compile(
    r"(\d*)d([bapsdcf])",
    re.IGNORECASE,
)

FFG_COMPACT_MAP = {
    "b": "boost",
    "a": "ability",
    "p": "proficiency",
    "s": "setback",
    "d": "difficulty",
    "c": "challenge",
    "f": "force",
}

FFG_COLOR_RE = re.compile(r"(?<!\w)(\d*)([Bbgpyrw])(?!\w)")

FFG_COLOR_MAP = {
    "B": "boost",
    "b": "setback",
    "g": "ability",
    "p": "difficulty",
    "y": "proficiency",
    "r": "challenge",
    "w": "force",
}

# Flag to suppress images
TEXTONLY_RE = re.compile(r"\btextonly\b", re.IGNORECASE)


@dataclass
class RollRequest:
    """Parsed roll request."""

    standard: list[tuple[int, int]] = field(default_factory=list)
    ffg: list[tuple[int, str]] = field(default_factory=list)
    text_only: bool = False


def parse_roll(text: str) -> Optional[RollRequest]:
    """Parse a dice expression string into a RollRequest."""
    req = RollRequest()
    remaining = text.strip()

    # Check and strip textonly flag
    if TEXTONLY_RE.search(remaining):
        req.text_only = True
        remaining = TEXTONLY_RE.sub("", remaining).strip()

    # 1) Verbose FFG names
    for m in FFG_RE.finditer(remaining):
        count = int(m.group(1)) if m.group(1) else 1
        req.ffg.append((count, m.group(2).lower()))
    remaining = FFG_RE.sub("", remaining)

    # 2) Compact FFG (d + letter)
    for m in FFG_COMPACT_RE.finditer(remaining):
        count = int(m.group(1)) if m.group(1) else 1
        alias = m.group(2).lower()
        die_name = FFG_COMPACT_MAP.get(alias)
        if die_name:
            req.ffg.append((count, die_name))
    remaining = FFG_COMPACT_RE.sub("", remaining)

    # 3) Standard dice (NdN)
    for m in STANDARD_RE.finditer(remaining):
        count = int(m.group(1)) if m.group(1) else 1
        sides = int(m.group(2))
        if sides < 2 or sides > 100:
            continue
        req.standard.append((count, sides))
    remaining = STANDARD_RE.sub("", remaining)

    # 4) Color-based FFG (parsed last)
    for m in FFG_COLOR_RE.finditer(remaining):
        count = int(m.group(1)) if m.group(1) else 1
        color_char = m.group(2)
        die_name = FFG_COLOR_MAP.get(color_char)
        if die_name:
            req.ffg.append((count, die_name))

    if not req.standard and not req.ffg:
        return None

    total_dice = sum(c for c, _ in req.standard) + sum(c for c, _ in req.ffg)
    if total_dice > 50:
        return None

    return req


# ── Rolling logic ────────────────────────────────────────────────────────────
def roll_standard(count: int, sides: int) -> list[int]:
    return [random.randint(1, sides) for _ in range(count)]


# ── Upload helper ────────────────────────────────────────────────────────────
async def upload_image(
    client: AsyncClient, png_bytes: bytes, filename: str
) -> Optional[str]:
    """Upload a PNG to the Matrix content repository; return mxc:// URI."""
    resp = await client.upload(
        data_provider=BytesIO(png_bytes),
        content_type="image/png",
        filename=filename,
        filesize=len(png_bytes),
    )

    # matrix-nio returns either a bare UploadResponse or a tuple of
    # (UploadResponse, encryption_dict_or_None).  Handle both.
    if isinstance(resp, tuple):
        resp = resp[0]

    if isinstance(resp, UploadResponse) and resp.content_uri:
        return resp.content_uri

    log.error("Upload failed for %s: %s", filename, resp)
    return None


# ── Startup: load cache or bulk pre-upload ───────────────────────────────────
async def ensure_images_cached(client: AsyncClient) -> int:
    """
    Try to load mxc:// cache from disk.  If the cache is complete (273 entries),
    skip uploading entirely.  Otherwise, upload missing images and save the
    updated cache to disk.
    """
    loaded = _load_cache_from_disk()
    if loaded >= EXPECTED_CACHE_SIZE:
        log.info("Cache loaded from disk: %d entries — skipping uploads", loaded)
        return loaded

    log.info(
        "Cache has %d/%d entries — uploading missing images …",
        loaded,
        EXPECTED_CACHE_SIZE,
    )
    uploaded = 0
    failed = 0

    # ── Standard dice ────────────────────────────────────────────────────
    std_dir = os.path.join(ASSETS_DIR, "std")
    if os.path.isdir(std_dir):
        for filename in sorted(os.listdir(std_dir)):
            if not filename.endswith(".png"):
                continue
            base = filename[:-4]
            parts = base.split("_")
            if len(parts) != 2 or not parts[0].startswith("d"):
                continue
            try:
                sides = int(parts[0][1:])
                value = int(parts[1])
            except ValueError:
                continue

            key = _std_cache_key(sides, value)
            if key in _image_cache:
                continue  # Already cached

            filepath = os.path.join(std_dir, filename)
            with open(filepath, "rb") as f:
                png_bytes = f.read()

            mxc = await upload_image(client, png_bytes, filename)
            if mxc:
                _image_cache[key] = mxc
                uploaded += 1
            else:
                failed += 1
    else:
        log.warning("Standard assets dir not found: %s", std_dir)

    # ── FFG dice ─────────────────────────────────────────────────────────
    ffg_dir = os.path.join(ASSETS_DIR, "ffg")
    if os.path.isdir(ffg_dir):
        for filename in sorted(os.listdir(ffg_dir)):
            if not filename.endswith(".png"):
                continue
            base = filename[:-4]
            sep_idx = base.rfind("_f")
            if sep_idx < 0:
                continue
            die_name = base[:sep_idx]
            try:
                face_index = int(base[sep_idx + 2 :])
            except ValueError:
                continue
            if die_name not in FFG_DICE:
                continue

            key = _ffg_cache_key(die_name, face_index)
            if key in _image_cache:
                continue

            filepath = os.path.join(ffg_dir, filename)
            with open(filepath, "rb") as f:
                png_bytes = f.read()

            mxc = await upload_image(client, png_bytes, filename)
            if mxc:
                _image_cache[key] = mxc
                uploaded += 1
            else:
                failed += 1
    else:
        log.warning("FFG assets dir not found: %s", ffg_dir)

    log.info(
        "Uploaded %d new images (%d failed). Cache now has %d entries.",
        uploaded,
        failed,
        len(_image_cache),
    )

    # Persist to disk
    _save_cache_to_disk()

    return len(_image_cache)


# ── Cache-first lookups with fallback rendering ──────────────────────────────
async def get_std_die_mxc(client: AsyncClient, sides: int, value: int) -> Optional[str]:
    """Get mxc:// URI for a standard die face. Cache-first, render on miss."""
    key = _std_cache_key(sides, value)
    cached = _image_cache.get(key)
    if cached:
        return cached

    # Fallback: render on the fly (for dice outside d2-d20 or missing assets)
    log.debug("Cache MISS %s — rendering on the fly", key)
    from dice_image_gen import render_standard_die

    png = render_standard_die(sides, value)
    mxc = await upload_image(client, png, f"d{sides}_{value}.png")
    if mxc:
        _image_cache[key] = mxc
        _save_cache_to_disk()
    return mxc


async def get_ffg_die_mxc(
    client: AsyncClient, die_name: str, result: FFGResult
) -> Optional[str]:
    """Get mxc:// URI for an FFG die face. Cache-first, render on miss."""
    key = _ffg_cache_key(die_name, result.face_index)
    cached = _image_cache.get(key)
    if cached:
        return cached

    log.debug("Cache MISS %s — rendering on the fly", key)
    from dice_image_gen import render_ffg_die

    png = render_ffg_die(die_name, result)
    mxc = await upload_image(client, png, f"ffg_{die_name}_f{result.face_index}.png")
    if mxc:
        _image_cache[key] = mxc
        _save_cache_to_disk()
    return mxc


# ── Handle !dice help ────────────────────────────────────────────────────────
async def send_help(client: AsyncClient, room_id: str):
    """Send the help message to a room."""
    await client.room_send(
        room_id,
        "m.room.message",
        {
            "msgtype": "m.notice",
            "body": HELP_TEXT_PLAIN,
            "format": "org.matrix.custom.html",
            "formatted_body": HELP_TEXT_HTML,
        },
    )


# ── Handle !roll ─────────────────────────────────────────────────────────────
async def handle_roll(client: AsyncClient, room_id: str, sender: str, expression: str):
    req = parse_roll(expression)
    if req is None:
        await client.room_send(
            room_id,
            "m.room.message",
            {
                "msgtype": "m.text",
                "body": (
                    "I couldn't parse that expression. "
                    "Type  !dice help  for usage examples."
                ),
            },
        )
        return

    text_parts: list[str] = []
    image_mxcs: list[tuple[str, int, int]] = []

    # ── Standard dice ────────────────────────────────────────────────────
    for count, sides in req.standard:
        results = roll_standard(count, sides)
        label = f"{count}d{sides}"
        result_str = ", ".join(str(r) for r in results)
        total = sum(results)
        text_parts.append(f"{label} → {result_str}  (total: {total})")

        if not req.text_only:
            for value in results:
                mxc = await get_std_die_mxc(client, sides, value)
                if mxc:
                    image_mxcs.append((mxc, 64, 64))

    # ── FFG dice ─────────────────────────────────────────────────────────
    ffg_all_results: list[FFGResult] = []
    for count, die_name in req.ffg:
        for _ in range(count):
            result = roll_ffg_die(die_name)
            ffg_all_results.append(result)

            if not req.text_only:
                mxc = await get_ffg_die_mxc(client, die_name, result)
                if mxc:
                    image_mxcs.append((mxc, 64, 64))

    if ffg_all_results:
        net = net_ffg_results(ffg_all_results)
        # One-line per-die results
        text_parts.append(f"FFG → {format_ffg_results(ffg_all_results, net)}")
        # Detailed summary block
        text_parts.append(format_ffg_summary(ffg_all_results, net))

    # ── Build message ────────────────────────────────────────────────────
    plain_text = "\n".join(text_parts)

    if req.text_only or not image_mxcs:
        # Text-only: no images at all
        await client.room_send(
            room_id,
            "m.room.message",
            {
                "msgtype": "m.text",
                "body": plain_text,
            },
        )
    else:
        img_html = " ".join(
            f'<img src="{mxc}" width="{w}" height="{h}" alt="die" />'
            for mxc, w, h in image_mxcs
        )
        result_html = "<br>".join(
            line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            for line in text_parts
        )
        full_html = f"{img_html}<br>{result_html}"

        await client.room_send(
            room_id,
            "m.room.message",
            {
                "msgtype": "m.text",
                "body": plain_text,
                "format": "org.matrix.custom.html",
                "formatted_body": full_html,
            },
        )

    log.info("Rolled for %s in %s: %s", sender, room_id, plain_text.split("\n")[0])


# ── Event callback ───────────────────────────────────────────────────────────
async def message_callback(room, event):
    if event.sender == client.user_id:
        return

    body = event.body.strip() if event.body else ""

    # Help command: !dice  or  !dice help
    if body.lower() in (HELP_PREFIX, f"{HELP_PREFIX} help"):
        await send_help(client, room.room_id)
        return

    # Roll command
    if not body.lower().startswith(COMMAND_PREFIX):
        return

    expression = body[len(COMMAND_PREFIX) :].strip()

    # !roll help / !roll ?
    if expression.lower() in ("help", "?"):
        await send_help(client, room.room_id)
        return

    # bare !roll → default 1d20
    if not expression:
        expression = "1d20"

    await handle_roll(client, room.room_id, event.sender, expression)


# ── Main ─────────────────────────────────────────────────────────────────────
client: AsyncClient = None  # type: ignore


async def main():
    global client
    client = AsyncClient(HOMESERVER, BOT_USER)

    log.info("Logging in as %s on %s", BOT_USER, HOMESERVER)
    resp = await client.login(BOT_PASSWORD, device_name=DEVICE_NAME)

    if not isinstance(resp, LoginResponse):
        log.error("Login failed: %s", resp)
        sys.exit(1)

    log.info("Login successful, user_id=%s device_id=%s", resp.user_id, resp.device_id)

    # ── Load or build image cache ────────────────────────────────────────
    log.info("Loading image cache …")
    count = await ensure_images_cached(client)
    log.info("Image cache ready: %d entries", count)

    # ── Initial sync (skip old messages) ─────────────────────────────────
    log.info("Performing initial sync …")
    await client.sync(timeout=10000, full_state=True)

    # ── Listen ───────────────────────────────────────────────────────────
    client.add_event_callback(message_callback, RoomMessageText)
    log.info("Ready — listening for !roll and !dice commands …")

    try:
        await client.sync_forever(timeout=30000, full_state=False)
    except (asyncio.CancelledError, KeyboardInterrupt):
        log.info("Shutting down …")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
