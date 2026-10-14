#!/usr/bin/env python3
"""Quick-look of WRF PALMAS's idealized supercell experiment.

This plots a model's calculated vertical velocity, not radar reflectivity,
not observational data, and not a South American weather forecast.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def plot_wrf_outputs(run_dir: Path, out_dir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from netCDF4 import Dataset

    outputs = sorted(run_dir.glob("wrfout_d01_*"))
    if not outputs:
        raise FileNotFoundError("No wrfout_d01 files were generated")
    out_dir.mkdir(parents=True, exist_ok=True)

    frame_summary = []
    for path in outputs:
        with Dataset(path) as ds:
            w = np.asarray(ds.variables["W"][-1, ...], dtype=float)
            # W is on vertically staggered model levels. This quick-look uses
            # each column's maximum across those model levels.
            wmax = np.nanmax(w, axis=0)
            dx_m = float(getattr(ds, "DX"))
            dy_m = float(getattr(ds, "DY"))
            ny, nx = wmax.shape
            timestep = path.name.split("wrfout_d01_", 1)[-1]
            max_w = float(np.nanmax(wmax))
            mean_w = float(np.nanmean(wmax))
            frame_summary.append({
                "filename": path.name, "forecast_valid_idealized": timestep,
                "max_updraft_ms": round(max_w, 3),
                "mean_column_max_w_ms": round(mean_w, 3),
            })
            fig, ax = plt.subplots(figsize=(8.6, 7.2))
            xmax = nx * dx_m / 1000
            ymax = ny * dy_m / 1000
            im = ax.imshow(wmax, origin="lower", extent=(0, xmax, 0, ymax),
                           vmin=0, cmap="turbo", aspect="equal")
            fig.colorbar(im, ax=ax, label="Máximo vertical W (m/s)")
            ax.set_xlabel("Distância leste-oeste (km)")
            ax.set_ylabel("Distância sul-norte (km)")
            ax.set_title("WRF PALMAS | supercélula idealizada\n"
                         f"{timestep} | W máximo: {max_w:.1f} m/s")
            fig.tight_layout()
            fig.savefig(out_dir / f"updraft_{timestep.replace(':', '-')}.png",
                        dpi=130)
            plt.close(fig)

    summary = {
        "experiment": "em_quarter_ss / supercell idealized",
        "not_a_real_weather_forecast": True,
        "frame_count": len(frame_summary),
        "frames": frame_summary,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()
    plot_wrf_outputs(args.run_dir, args.out_dir)
