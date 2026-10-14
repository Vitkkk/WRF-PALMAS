#!/usr/bin/env python3
"""Create a GIF directly from archived WRF PALMAS PNGs; WRF is NOT required."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def animate(png_dir: Path, gif_path: Path, duration_ms: int = 1250) -> int:
    from PIL import Image

    if duration_ms < 80:
        raise ValueError("Frames would change too quickly")
    source = sorted(png_dir.glob("t2_*.png"))
    if not source:
        raise FileNotFoundError(f"No t2_*.png in {png_dir}")
    manifest = png_dir / "summary.json"
    if manifest.exists():
        expected = json.loads(manifest.read_text(encoding="utf-8")).get("num_times")
        if expected is not None and len(source) != expected:
            raise ValueError(f"Missing frames: expected {expected}, got {len(source)}")
    frames = []
    try:
        for path in source:
            with Image.open(path) as img:
                frames.append(img.convert("RGB"))
        if len({im.size for im in frames}) != 1:
            raise ValueError("Frame sizes do not match")
        gif_path.parent.mkdir(parents=True, exist_ok=True)
        frames[0].save(gif_path, format="GIF", save_all=True,
                       append_images=frames[1:], duration=duration_ms,
                       loop=0, optimize=True)
        with Image.open(gif_path) as check:
            if check.n_frames != len(frames):
                raise ValueError("GIF frame count inconsistent")
        print(f"Animated {len(frames)} old PNGs => {gif_path}")
        return len(frames)
    finally:
        for frame in frames:
            frame.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--png-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--duration-ms", type=int, default=1250)
    args = parser.parse_args()
    animate(args.png_dir, args.out, args.duration_ms)
