"""
Star Wars FFG (Fantasy Flight Games) Dice System
─────────────────────────────────────────────────
Dice types and their symbol faces.

Symbols:
  Success (Su), Advantage (Ad), Triumph (Tr)     ← positive
  Failure (Fa), Threat (Th), Despair (De)         ← negative
  Light Side (LS), Dark Side (DS)                 ← Force only

Triumph also counts as a Success.
Despair also counts as a Failure.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# ── Symbol constants ─────────────────────────────────────────────────────────
SU = "success"
AD = "advantage"
TR = "triumph"
FA = "failure"
TH = "threat"
DE = "despair"
LS = "light"
DS = "dark"
BLANK = "blank"

SYMBOL_DISPLAY = {
    SU: "Su",
    AD: "Ad",
    TR: "Tr",
    FA: "Fa",
    TH: "Th",
    DE: "De",
    LS: "LS",
    DS: "DS",
    BLANK: "—",
}

# ── FFG Die Definitions ─────────────────────────────────────────────────────
# Each die is a list of faces. Each face is a tuple of symbols.
# Source: Star Wars RPG core rulebooks.

FFG_DICE: Dict[str, List[Tuple[str, ...]]] = {
    # Boost die (d6) — light blue
    "boost": [
        (),  # blank
        (),  # blank
        (SU,),
        (SU, AD),
        (AD, AD),
        (AD,),
    ],
    # Setback die (d6) — black
    "setback": [
        (),  # blank
        (),  # blank
        (FA,),
        (FA,),
        (TH,),
        (TH,),
    ],
    # Ability die (d8) — green
    "ability": [
        (),  # blank
        (SU,),
        (SU,),
        (SU, SU),
        (AD,),
        (AD,),
        (SU, AD),
        (AD, AD),
    ],
    # Difficulty die (d8) — purple
    "difficulty": [
        (),  # blank
        (FA,),
        (FA, FA),
        (TH,),
        (TH,),
        (TH,),
        (TH, TH),
        (FA, TH),
    ],
    # Proficiency die (d12) — yellow
    "proficiency": [
        (),  # blank
        (SU,),
        (SU,),
        (SU, SU),
        (SU, SU),
        (AD,),
        (SU, AD),
        (SU, AD),
        (SU, AD),
        (AD, AD),
        (AD, AD),
        (TR,),  # Triumph (also counts as Success)
    ],
    # Challenge die (d12) — red
    "challenge": [
        (),  # blank
        (FA,),
        (FA,),
        (FA, FA),
        (FA, FA),
        (TH,),
        (TH,),
        (FA, TH),
        (FA, TH),
        (TH, TH),
        (TH, TH),
        (DE,),  # Despair (also counts as Failure)
    ],
    # Force die (d12) — white
    "force": [
        (DS,),
        (DS,),
        (DS,),
        (DS,),
        (DS,),
        (DS,),
        (DS, DS),
        (LS,),
        (LS,),
        (LS, LS),
        (LS, LS),
        (LS, LS),
    ],
}

# Colors for each FFG die type (background, foreground/symbol)
FFG_COLORS: Dict[str, Tuple[str, str]] = {
    "boost": ("#87CEEB", "#000000"),  # light blue / black
    "setback": ("#1A1A1A", "#FFFFFF"),  # black / white
    "ability": ("#228B22", "#FFFFFF"),  # green / white
    "difficulty": ("#6A0DAD", "#FFFFFF"),  # purple / white
    "proficiency": ("#FFD700", "#000000"),  # yellow / black
    "challenge": ("#CC0000", "#FFFFFF"),  # red / white
    "force": ("#F5F5F5", "#000000"),  # white / black
}


@dataclass
class FFGResult:
    """Result of rolling one FFG die."""

    die_name: str
    face_index: int
    symbols: Tuple[str, ...]

    def display(self) -> str:
        if not self.symbols:
            return "blank"
        return " ".join(SYMBOL_DISPLAY.get(s, s) for s in self.symbols)


def roll_ffg_die(die_name: str) -> FFGResult:
    """Roll a single FFG die and return the result."""
    die_name = die_name.lower()
    faces = FFG_DICE[die_name]
    idx = random.randint(0, len(faces) - 1)
    return FFGResult(die_name=die_name, face_index=idx, symbols=faces[idx])


def net_ffg_results(results: List[FFGResult]) -> Dict[str, int]:
    """
    Compute net FFG results across multiple dice.
    Success vs Failure cancel, Advantage vs Threat cancel.
    Triumph/Despair are counted separately but also contribute to Success/Failure.
    """
    totals: Dict[str, int] = {
        SU: 0,
        FA: 0,
        AD: 0,
        TH: 0,
        TR: 0,
        DE: 0,
        LS: 0,
        DS: 0,
    }
    for r in results:
        for sym in r.symbols:
            totals[sym] = totals.get(sym, 0) + 1

    # Triumph counts as Success too, Despair counts as Failure
    total_success = totals[SU] + totals[TR]
    total_failure = totals[FA] + totals[DE]
    total_advantage = totals[AD]
    total_threat = totals[TH]

    net: Dict[str, int] = {}

    # Net success / failure
    if total_success > total_failure:
        net["net_success"] = total_success - total_failure
    elif total_failure > total_success:
        net["net_failure"] = total_failure - total_success

    # Net advantage / threat
    if total_advantage > total_threat:
        net["net_advantage"] = total_advantage - total_threat
    elif total_threat > total_advantage:
        net["net_threat"] = total_threat - total_advantage

    # Triumph and Despair never cancel — always reported
    if totals[TR]:
        net["triumph"] = totals[TR]
    if totals[DE]:
        net["despair"] = totals[DE]

    # Force pips
    if totals[LS]:
        net["light_side"] = totals[LS]
    if totals[DS]:
        net["dark_side"] = totals[DS]

    return net


def format_ffg_results(results: List[FFGResult], net: Dict[str, int]) -> str:
    """Human-readable summary of FFG roll."""
    per_die = [f"[{r.die_name}: {r.display()}]" for r in results]
    parts = " ".join(per_die)

    net_parts = []
    label_map = {
        "net_success": "Net Success",
        "net_failure": "Net Failure",
        "net_advantage": "Net Advantage",
        "net_threat": "Net Threat",
        "triumph": "Triumph",
        "despair": "Despair",
        "light_side": "Light Side",
        "dark_side": "Dark Side",
    }
    for key in (
        "net_success",
        "net_failure",
        "net_advantage",
        "net_threat",
        "triumph",
        "despair",
        "light_side",
        "dark_side",
    ):
        val = net.get(key)
        if val:
            net_parts.append(f"{label_map[key]}: {val}")

    net_str = ", ".join(net_parts) if net_parts else "All cancelled out"
    return f"{parts}  ⇒  {net_str}"


def format_ffg_summary(results: List[FFGResult], net: Dict[str, int]) -> str:
    """
    FFG summary with raw totals and an overall verdict.

    Example output:
        ✅ SUCCESS with Advantage. 2 Success, 1 Advantage
    """

    # Net results
    net_label_map = {
        "net_success": "Success",
        "net_failure": "Failure",
        "net_advantage": "Advantage",
        "net_threat": "Threat",
        "triumph": "Triumph",
        "despair": "Despair",
        "light_side": "Light Side",
        "dark_side": "Dark Side",
    }
    net_parts = []
    for key in (
        "net_success",
        "net_failure",
        "net_advantage",
        "net_threat",
        "triumph",
        "despair",
        "light_side",
        "dark_side",
    ):
        val = net.get(key)
        if val:
            net_parts.append(f"{val} {net_label_map[key]}")

    net_result = ", ".join(net_parts) if net_parts else "all cancelled out!"

    verdict = "? Unknown"

    # Verdict
    is_force_only = all(r.die_name == "force" for r in results)
    if is_force_only:
        ls = net.get("light_side", 0)
        ds = net.get("dark_side", 0)
        if ls > ds:
            verdict = f"⚪ Light Side dominates ({ls} vs {ds})"
        elif ds > ls:
            verdict = f"⚫ Dark Side dominates ({ds} vs {ls})"
        else:
            verdict = "☯ Balanced"
    else:
        has_success = "net_success" in net
        has_failure = "net_failure" in net
        has_advantage = "net_advantage" in net
        has_threat = "net_threat" in net
        has_triumph = net.get("triumph", 0) > 0
        has_despair = net.get("despair", 0) > 0

        parts = []
        if has_success:
            parts.append("SUCCESS")
        elif has_failure:
            parts.append("FAILURE")
        else:
            parts.append("WASH (no net success or failure)")

        modifiers = []
        if has_advantage:
            modifiers.append("Advantage.")
        if has_threat:
            modifiers.append("Threat.")
        if has_triumph:
            modifiers.append("Triumph!")
        if has_despair:
            modifiers.append("Despair!")
        if modifiers:
            parts.append(f"with {', '.join(modifiers)}")

        if has_success:
            emoji = "🎆" if has_triumph else "✅"
        elif has_failure:
            emoji = "💀" if has_despair else "❌"
        else:
            emoji = "➖"

        verdict = f"{emoji} {' '.join(parts)} {net_result}"

    return verdict
