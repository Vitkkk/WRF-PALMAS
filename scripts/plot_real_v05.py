#!/usr/bin/env python3
"""WRF PALMAS V0.5 — quick-look from actual regional GFS-forced WRF outputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def plot_run(directory: Path, target: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from netCDF4 import Dataset, chartostring

    target.mkdir(parents=True, exist_ok=True)
    paths = sorted(directory.glob("wrfout_d01_*"))
    if not paths:
        raise FileNotFoundError("No WRF real-data output wrfout_d01_*")
    records = []
    for path in paths:
        with Dataset(path) as ds:
            for v in ("T2", "XLAT", "XLONG", "U10", "V10", "Times"):
                if v not in ds.variables:
                    raise ValueError(f"Required field {v} not present in {path.name}")
            stamps = chartostring(ds.variables["Times"][:])
            for i, stamp in enumerate(stamps):
                lat = np.asarray(ds.variables["XLAT"][i], dtype=float)
                lon = np.asarray(ds.variables["XLONG"][i], dtype=float)
                tc = np.asarray(ds.variables["T2"][i], dtype=float) - 273.15
                u = np.asarray(ds.variables["U10"][i], dtype=float)
                v = np.asarray(ds.variables["V10"][i], dtype=float)
                if not np.isfinite(tc).all():
                    raise ValueError(f"Nonfinite temperature in {path}")
                fig, ax = plt.subplots(figsize=(9, 7))
                image = ax.pcolormesh(lon, lat, tc, shading="auto", cmap="coolwarm")
                fig.colorbar(image, ax=ax, label="Temperatura a 2 m (°C)")
                step = max(1, min(tc.shape) // 13)
                ax.quiver(lon[::step, ::step], lat[::step, ::step],
                          u[::step, ::step], v[::step, ::step],
                          scale=260, width=0.0025)
                ax.set(xlabel="Longitude (°)", ylabel="Latitude (°)",
                       title=f"WRF PALMAS V0.5 | GFS real | {str(stamp)} UTC\n"
                             "Temperatura 2 m e vento 10 m (teste de processamento)")
                fig.tight_layout()
                name = f"t2_{len(records):03d}.png"
                fig.savefig(target / name, dpi=120)
                plt.close(fig)
                records.append({
                    "time_utc": str(stamp),
                    "min_t2_c": round(float(tc.min()), 2),
                    "max_t2_c": round(float(tc.max()), 2),
                    "max_wind10_ms": round(float(np.hypot(u, v).max()), 2),
                    "image": name,
                })

    summary = {"project": "WRF PALMAS V0.5",
               "description": "Real GFS-forced test; low-resolution WPS geographical data",
               "not_operational": True, "num_times": len(records),
               "frames": records}
    (target / "summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    a = p.parse_args()
    plot_run(a.run_dir, a.out_dir)
