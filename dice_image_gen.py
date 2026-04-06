"""
Dice Image Generator
────────────────────
Generates 64x64 PNG images of dice faces using Pillow.

Standard dice (d2-d20): Colored polygon/shape with number overlay.
FFG dice: Colored background with FFG symbol glyphs drawn on the face.
"""

from __future__ import annotations

import math
from io import BytesIO
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont

from ffg_dice import (
    FFGResult,
    FFG_COLORS,
    SYMBOL_DISPLAY,
    SU,
    AD,
    TR,
    FA,
    TH,
    DE,
    LS,
    DS,
)

SIZE = 64
HALF = SIZE // 2

# ── Color palette for standard dice by sides ─────────────────────────────────
STANDARD_COLORS: dict[int, Tuple[str, str]] = {
    2: ("#555555", "#FFFFFF"),
    4: ("#E74C3C", "#FFFFFF"),  # red
    6: ("#F5F5F5", "#222222"),  # white-ish
    8: ("#3498DB", "#FFFFFF"),  # blue
    10: ("#2ECC71", "#FFFFFF"),  # green
    12: ("#E67E22", "#FFFFFF"),  # orange
    20: ("#9B59B6", "#FFFFFF"),  # purple
}


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load a TrueType font, fall back to default."""
    try:
        return ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size
        )
    except (OSError, IOError):
        try:
            return ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf", size)
        except (OSError, IOError):
            return ImageFont.load_default()


def _color_for_sides(sides: int) -> Tuple[str, str]:
    """Pick background and foreground colors for a given die type."""
    if sides in STANDARD_COLORS:
        return STANDARD_COLORS[sides]
    # Fallback: hash-based hue
    hue = (sides * 37) % 360
    bg = f"hsl({hue}, 60%, 45%)"
    return bg, "#FFFFFF"


# ── Standard die shapes ──────────────────────────────────────────────────────


def _draw_square(draw: ImageDraw.ImageDraw, bg: str):
    """d6 style square with rounded feel."""
    draw.rounded_rectangle([4, 4, SIZE - 5, SIZE - 5], radius=8, fill=bg)


def _draw_diamond(draw: ImageDraw.ImageDraw, bg: str):
    """d4-ish / d8-ish diamond shape."""
    points = [(HALF, 4), (SIZE - 5, HALF), (HALF, SIZE - 5), (4, HALF)]
    draw.polygon(points, fill=bg)


def _draw_pentagon(draw: ImageDraw.ImageDraw, bg: str):
    """d10/d12 pentagon."""
    cx, cy, r = HALF, HALF, HALF - 4
    pts = []
    for i in range(5):
        angle = math.radians(-90 + 72 * i)
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    draw.polygon(pts, fill=bg)


def _draw_circle(draw: ImageDraw.ImageDraw, bg: str):
    """d20 / coin / generic."""
    draw.ellipse([4, 4, SIZE - 5, SIZE - 5], fill=bg)


def _draw_triangle(draw: ImageDraw.ImageDraw, bg: str):
    """d4 triangle."""
    pts = [(HALF, 6), (SIZE - 6, SIZE - 8), (6, SIZE - 8)]
    draw.polygon(pts, fill=bg)


def _shape_for_sides(sides: int):
    """Select shape drawing function based on die type."""
    if sides == 2:
        return _draw_circle
    if sides == 4:
        return _draw_triangle
    if sides == 6:
        return _draw_square
    if sides in (8,):
        return _draw_diamond
    if sides in (10, 12):
        return _draw_pentagon
    if sides == 20:
        return _draw_circle
    # generic fallback
    if sides <= 6:
        return _draw_square
    if sides <= 12:
        return _draw_pentagon
    return _draw_circle


# ── Render standard die ─────────────────────────────────────────────────────


def render_standard_die(sides: int, value: int) -> bytes:
    """Render a standard die face and return PNG bytes."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    bg, fg = _color_for_sides(sides)
    shape_fn = _shape_for_sides(sides)
    shape_fn(draw, bg)

    # Label: "d{sides}" small at top, value large in center
    label = f"d{sides}"
    value_str = str(value)

    font_sm = _get_font(10)
    font_lg = _get_font(22 if len(value_str) <= 2 else 16)

    # Draw die type label at top
    lbox = draw.textbbox((0, 0), label, font=font_sm)
    lw = lbox[2] - lbox[0]
    draw.text(((SIZE - lw) / 2, 4), label, fill=fg, font=font_sm)

    # Draw value centered
    vbox = draw.textbbox((0, 0), value_str, font=font_lg)
    vw = vbox[2] - vbox[0]
    vh = vbox[3] - vbox[1]
    draw.text(((SIZE - vw) / 2, (SIZE - vh) / 2 + 2), value_str, fill=fg, font=font_lg)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── FFG symbol glyphs (text-based, compact) ──────────────────────────────────

# Map each symbol to a small text glyph and a color
FFG_SYMBOL_GLYPHS = {
    SU: ("★", "#FFD700"),  # gold star
    AD: ("▲", "#00CC00"),  # green triangle
    TR: ("✦", "#FFFF00"),  # bright yellow
    FA: ("✖", "#FF4444"),  # red X
    TH: ("◆", "#333333"),  # dark diamond
    DE: ("☠", "#FF0000"),  # red skull
    LS: ("○", "#929292"),  # grey circle
    DS: ("●", "#000000"),  # black circle
}


def render_ffg_die(die_name: str, result: FFGResult) -> bytes:
    """Render an FFG die face and return PNG bytes."""
    bg_color, fg_color = FFG_COLORS.get(die_name, ("#888888", "#FFFFFF"))

    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw rounded rectangle background
    draw.rounded_rectangle([2, 2, SIZE - 3, SIZE - 3], radius=8, fill=bg_color)

    font_sm = _get_font(9)
    font_sym = _get_font(16)

    # Die type label at top
    label = die_name[:3].upper()
    lbox = draw.textbbox((0, 0), label, font=font_sm)
    lw = lbox[2] - lbox[0]
    draw.text(((SIZE - lw) / 2, 3), label, fill=fg_color, font=font_sm)

    symbols = result.symbols
    if not symbols:
        # Blank face
        blank_font = _get_font(20)
        draw.text((HALF - 6, HALF - 10), "—", fill=fg_color, font=blank_font)
    elif len(symbols) == 1:
        # Single symbol, centered
        glyph, glyph_color = FFG_SYMBOL_GLYPHS.get(symbols[0], ("?", fg_color))
        gbox = draw.textbbox((0, 0), glyph, font=font_sym)
        gw = gbox[2] - gbox[0]
        gh = gbox[3] - gbox[1]
        draw.text(
            ((SIZE - gw) / 2, (SIZE - gh) / 2 + 4),
            glyph,
            fill=glyph_color,
            font=font_sym,
        )
    else:
        # Multiple symbols side by side
        total_w = 0
        glyph_info = []
        for sym in symbols:
            g, gc = FFG_SYMBOL_GLYPHS.get(sym, ("?", fg_color))
            box = draw.textbbox((0, 0), g, font=font_sym)
            w = box[2] - box[0]
            glyph_info.append((g, gc, w))
            total_w += w

        spacing = 2
        total_w += spacing * (len(glyph_info) - 1)
        x = (SIZE - total_w) / 2
        y = HALF - 2
        for g, gc, w in glyph_info:
            draw.text((x, y), g, fill=gc, font=font_sym)
            x += w + spacing

    # Thin border
    draw.rounded_rectangle(
        [2, 2, SIZE - 3, SIZE - 3], radius=8, outline="#00000066", width=1
    )

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
