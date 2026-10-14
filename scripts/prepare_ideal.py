#!/usr/bin/env python3
"""Make a bounded, idealized WRF em_quarter_ss experiment from its stock namelist.

No moving geographic grid: this is a fixed idealized grid. Frame motion needs a
separate verified WRF-specific experiment and is not enabled here.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def _replace_once(text: str, pattern: str, replacement: str) -> str:
    text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"Expected one namelist entry for {pattern}, found {count}")
    return text


def make_namelist(source: str, duration_minutes: int, grid_points: int,
                  history_minutes: int) -> str:
    if duration_minutes not in (30, 60, 120, 180):
        raise ValueError("duration must be 30, 60, 120 or 180 min")
    if grid_points not in (42, 82, 122, 162):
        raise ValueError("grid must be 42, 82, 122 or 162 points")
    if history_minutes not in (10, 15, 30):
        raise ValueError("history must be 10, 15 or 30 min")
    if duration_minutes % history_minutes != 0:
        raise ValueError("duration must be divisible by history interval")

    hours, minutes = divmod(duration_minutes, 60)
    edits = [
        (r"^(\s*run_hours\s*=)[^\n]*$", f"\\\\g<1> {hours},"),
        (r"^(\s*run_minutes\s*=)[^\n]*$", f"\\\\g<1> {minutes},"),
        (r"^(\s*end_hour\s*=)[^\n]*$", f"\\\\g<1> {hours}, {hours}, {hours},"),
        (r"^(\s*end_minute\s*=)[^\n]*$", f"\\\\g<1> {minutes}, {minutes}, {minutes},"),
        (r"^(\s*history_interval\s*=)[^\n]*$",
         f"\\\\g<1> {history_minutes}, {history_minutes}, {history_minutes},"),
        (r"^(\s*e_we\s*=)[^\n]*$", f"\\\\g<1> {grid_points}, {grid_points}, {grid_points},"),
        (r"^(\s*e_sn\s*=)[^\n]*$", f"\\\\g<1> {grid_points}, {grid_points}, {grid_points},"),
    ]
    result = source
    for pattern, replacement in edits:
        result = _replace_once(result, pattern, replacement.replace("\\\\g", "\\g"))
    # Keep the official 41 vertical levels and 20 km model top unchanged.
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--namelist", type=Path, required=True)
    ap.add_argument("--duration", type=int, default=120)
    ap.add_argument("--grid", type=int, default=122)
    ap.add_argument("--history", type=int, default=15)
    args = ap.parse_args()
    source = args.namelist.read_text()
    modified = make_namelist(source, args.duration, args.grid, args.history)
    args.namelist.write_text(modified)
    print(f"Configured ideal WRF: {args.duration} min, grid "
          f"{args.grid}x{args.grid}, 2 km, output each {args.history} min.")
    print("No geography, GFS, or storm-following-frame modification was applied.")


if __name__ == "__main__":
    main()
