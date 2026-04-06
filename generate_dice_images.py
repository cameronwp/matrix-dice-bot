#!/usr/bin/env python3
"""
generate_dice_images.py
───────────────────────
Offline script that pre-generates every possible dice face as a PNG file.

Run this ONCE (or during container build) to populate the assets/ directory.
The bot then reads from disk at startup instead of rendering on the fly.

Output structure:
    assets/
        std/
            d2_1.png  d2_2.png
            d4_1.png  d4_2.png  d4_3.png  d4_4.png
            ...
            d20_1.png ... d20_20.png
        ffg/
            boost_f0.png  boost_f1.png  ...  boost_f5.png
            setback_f0.png  ...
            ability_f0.png  ...
            difficulty_f0.png  ...
            proficiency_f0.png  ...  proficiency_f11.png
            challenge_f0.png  ...  challenge_f11.png
            force_f0.png  ...  force_f11.png

Usage:
    python generate_dice_images.py [--output-dir assets]
"""

import argparse
import os
import sys

from dice_image_gen import render_standard_die, render_ffg_die
from ffg_dice import FFG_DICE, FFGResult


def generate_all(output_dir: str) -> None:
    std_dir = os.path.join(output_dir, "std")
    ffg_dir = os.path.join(output_dir, "ffg")
    os.makedirs(std_dir, exist_ok=True)
    os.makedirs(ffg_dir, exist_ok=True)

    # ── Standard dice d2 through d20 ─────────────────────────────────────
    std_count = 0
    for sides in range(2, 21):
        for value in range(1, sides + 1):
            filename = f"d{sides}_{value}.png"
            filepath = os.path.join(std_dir, filename)
            png_bytes = render_standard_die(sides, value)
            with open(filepath, "wb") as f:
                f.write(png_bytes)
            std_count += 1
        print(f"  d{sides}: {sides} faces generated")

    # ── FFG dice ──────────────────────────────────────────────────────────
    ffg_count = 0
    for die_name, faces in FFG_DICE.items():
        for face_idx, symbols in enumerate(faces):
            result = FFGResult(die_name=die_name, face_index=face_idx, symbols=symbols)
            filename = f"{die_name}_f{face_idx}.png"
            filepath = os.path.join(ffg_dir, filename)
            png_bytes = render_ffg_die(die_name, result)
            with open(filepath, "wb") as f:
                f.write(png_bytes)
            ffg_count += 1
        print(f"  {die_name}: {len(faces)} faces generated")

    total = std_count + ffg_count
    print(f"\nDone: {std_count} standard + {ffg_count} FFG = {total} images")
    print(f"Output: {os.path.abspath(output_dir)}")


def main():
    parser = argparse.ArgumentParser(
        description="Pre-generate all dice face images to disk."
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="assets",
        help="Directory to write images into (default: assets)",
    )
    args = parser.parse_args()

    print(f"Generating dice images into {args.output_dir}/ ...")
    generate_all(args.output_dir)


if __name__ == "__main__":
    main()
