#!/usr/bin/env python3
"""WRF PALMAS V0.2: every NetCDF time -> PNG, GIF, diagnostics.

The experiment em_quarter_ss is idealized, not a forecast for Brazil.
W is vertical air velocity (m/s), NOT horizontal wind nor tornado intensity.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def read_model_times(ds):
    """Read all valid WRF Times records, including multiple in one NetCDF."""
    import numpy as np
    from netCDF4 import chartostring

    if "Times" not in ds.variables:
        raise ValueError("WRF output does not contain Times")
    raw = np.asarray(ds.variables["Times"][:])
    if raw.ndim == 2:
        values = chartostring(raw)
    elif raw.ndim == 1:
        values = raw
    else:
        raise ValueError(f"Unexpected Times dimensions: {raw.shape}")
    stamps = []
    for value in values:
        if isinstance(value, bytes):
            value = value.decode("ascii")
        stamps.append(datetime.strptime(str(value).strip(), "%Y-%m-%d_%H:%M:%S"))
    return stamps


def extract_frames(run_dir: Path):
    """Return a list of (elapsed_minutes, time_text, 2d_wmax, dx, dy).

    Sorting and deduplicating is based on the internal WRF Times variable,
    never on the filename (one file can contain many timestamps).
    """
    import numpy as np
    from netCDF4 import Dataset

    outputs = sorted(run_dir.glob("wrfout_d01_*"))
    if not outputs:
        raise FileNotFoundError("No wrfout_d01_* was generated")
    records = []
    for filename in outputs:
        with Dataset(filename, "r") as ds:
            times = read_model_times(ds)
            if "W" not in ds.variables:
                raise ValueError(f"W not found in {filename}")
            variable = ds.variables["W"]
            if variable.shape[0] != len(times):
                raise ValueError(f"Times and W disagree in {filename}")
            dx = float(getattr(ds, "DX"))
            dy = float(getattr(ds, "DY"))
            for idx, timestamp in enumerate(times):
                # W has staggered vertical levels. Take column maximum at each time.
                w_column_max = np.nanmax(
                    np.ma.filled(variable[idx, ...], np.nan), axis=0
                )
                if not np.isfinite(w_column_max).any():
                    raise ValueError(f"Invalid W data at {timestamp}")
                records.append((timestamp, w_column_max, dx, dy))
    if not records:
        raise ValueError("No WRF records found")
    records.sort(key=lambda record: record[0])
    start = records[0][0]
    result = {}
    for timestamp, field, dx, dy in records:
        minute = int(round((timestamp - start).total_seconds() / 60))
        result[minute] = (
            minute, timestamp.strftime("%Y-%m-%d_%H:%M:%S"), field, dx, dy
        )
    return [result[key] for key in sorted(result)]


def plot_wrf_outputs(run_dir: Path, out_dir: Path, frame_duration_ms: int = 650):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from PIL import Image

    records = extract_frames(run_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    global_scale = max(
        1.0, max(float(np.nanmax(field)) for _, _, field, _, _ in records)
    )
    images = []
    summaries = []

    for minute, timestamp, field, dx, dy in records:
        ny, nx = field.shape
        width_km, height_km = nx * dx / 1000, ny * dy / 1000
        vmax = float(np.nanmax(field))
        strong_area = int(np.count_nonzero(field >= 5.0)) * dx * dy / 1e6
        name = f"updraft_t{minute:04d}.png"
        fig, ax = plt.subplots(figsize=(8, 6.5))
        im = ax.imshow(
            field, origin="lower", extent=(0, width_km, 0, height_km),
            cmap="turbo", vmin=0, vmax=global_scale, aspect="equal",
            interpolation="nearest",
        )
        fig.colorbar(im, ax=ax, label="Máximo vertical de W na coluna (m/s)")
        ax.set_xlabel("Distância leste-oeste (km)")
        ax.set_ylabel("Distância sul-norte (km)")
        ax.set_title(
            f"WRF PALMAS | Supercélula idealizada | T+{minute:03d} min\n"
            f"W vertical máximo: {vmax:.1f} m/s",
        )
        fig.tight_layout()
        fig.savefig(out_dir / name, dpi=130)
        plt.close(fig)
        with Image.open(out_dir / name) as img:
            images.append(img.convert("RGB"))
        summaries.append({
            "elapsed_minutes": minute,
            "netcdf_time": timestamp,
            "max_vertical_velocity_ms": round(vmax, 3),
            "updraft_area_above_5ms_km2": round(strong_area, 3),
            "png": name,
        })

    gif_name = "supercelula_idealizada.gif"
    images[0].save(
        out_dir / gif_name, save_all=True, append_images=images[1:],
        duration=frame_duration_ms, loop=0, optimize=False,
    )
    for image in images:
        image.close()

    fig, ax = plt.subplots(figsize=(8.4, 4.6))
    ax.plot(
        [rec["elapsed_minutes"] for rec in summaries],
        [rec["max_vertical_velocity_ms"] for rec in summaries],
        marker="o",
    )
    ax.set(
        title="WRF PALMAS | Evolução da velocidade vertical máxima",
        xlabel="Minutos de simulação idealizada",
        ylabel="W máximo (m/s)",
    )
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_dir / "evolucao_updraft.png", dpi=140)
    plt.close(fig)

    summary = {
        "experiment": "WRF em_quarter_ss, idealized supercell",
        "not_a_real_weather_forecast": True,
        "frame_count": len(summaries),
        "simulated_minutes": summaries[-1]["elapsed_minutes"],
        "maximum_w_ms": max(rec["max_vertical_velocity_ms"] for rec in summaries),
        "gif": gif_name,
        "series_png": "evolucao_updraft.png",
        "frames": summaries,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--frame-duration-ms", type=int, default=650)
    args = parser.parse_args()
    plot_wrf_outputs(args.run_dir, args.out_dir, args.frame_duration_ms)
