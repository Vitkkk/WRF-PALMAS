#!/usr/bin/env python3
"""V0.3 idealized dynamics: vertical vorticity and rain-only dBZ proxy.

The dBZ approximation assumes Marshall-Palmer rain drop size distribution
(N0=8e6 m^-4), excludes hail/ice/snow, and is NOT radar observed reflectivity.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

N0 = 8.0e6
RHOW = 1000.0
RD = 287.05
CP = 1004.0


def destagger_uv(u, v):
    """Return mass-centered horizontal winds (z,y,x)."""
    uc = 0.5 * (u[..., :-1] + u[..., 1:])
    vc = 0.5 * (v[..., :-1, :] + v[..., 1:, :])
    if uc.shape != vc.shape:
        raise ValueError("U and V staggered fields do not align")
    return uc, vc


def vertical_vorticity(u, v, dx, dy):
    """Relative zeta = dv/dx - du/dy [s^-1]."""
    import numpy as np
    if dx <= 0 or dy <= 0:
        raise ValueError("Grid spacings must be positive")
    uc, vc = destagger_uv(u, v)
    return (np.gradient(vc, dx, axis=-1, edge_order=2)
            - np.gradient(uc, dy, axis=-2, edge_order=2))


def height_agl_mass(ph, phb):
    """Convert W-staggered geopotential to mass-layer height AGL [m]."""
    z = (ph + phb) / 9.81
    return (z[:-1] + z[1:]) * 0.5 - z[0]


def near_height(field, height, target=1000.0):
    """Select the nearest model mass level at each column."""
    import numpy as np
    if field.shape != height.shape:
        raise ValueError("height and field shapes differ")
    idx = np.abs(height - target).argmin(axis=0)
    return np.take_along_axis(field, idx[None, ...], axis=0)[0]


def rain_dbz_proxy(qr, pressure, theta_pert, qv):
    """Approximate reflectivity of Kessler liquid rain only [dBZ].

    rho_air * qr = pi*rho_water*N0/lambda**4;
    Z [mm^6/m^3] = N0*720/lambda**7 * 1e18.
    """
    import numpy as np
    qr, pressure, theta_pert, qv = (
        np.asarray(a, dtype=float) for a in (qr, pressure, theta_pert, qv)
    )
    temp = (theta_pert + 300.0) * (pressure / 100000.0) ** (RD / CP)
    rho = pressure / (RD * temp * (1.0 + 0.61 * np.maximum(qv, 0.0)))
    mask = (qr > 1e-10) & (pressure > 0) & np.isfinite(rho)
    result = np.full(qr.shape, np.nan)
    if np.any(mask):
        rain_density = rho[mask] * qr[mask]
        lam = (np.pi * RHOW * N0 / rain_density) ** 0.25
        z_linear = N0 * 720.0 / lam**7 * 1e18
        result[mask] = 10.0 * np.log10(z_linear)
    return result


def model_frames(directory):
    """Read all timestamps from the WRF NetCDF, not filenames."""
    import numpy as np
    from netCDF4 import Dataset
    from plot_ideal import read_model_times

    paths = sorted(directory.glob("wrfout_d01_*"))
    if not paths:
        raise FileNotFoundError("WRF wrfout_d01_* files not found")
    records = {}
    required = ("U", "V", "PH", "PHB", "QRAIN", "P", "PB", "T", "QVAPOR", "W")
    for path in paths:
        with Dataset(path) as ds:
            missing = [v for v in required if v not in ds.variables]
            if missing:
                raise ValueError(f"Missing variables in {path.name}: {missing}")
            dx, dy = float(ds.DX), float(ds.DY)
            for i, time in enumerate(read_model_times(ds)):
                def get(variable):
                    return np.asarray(
                        np.ma.filled(ds.variables[variable][i], np.nan),
                        dtype=float,
                    )
                zeta = vertical_vorticity(get("U"), get("V"), dx, dy)
                height = height_agl_mass(get("PH"), get("PHB"))
                zeta1 = near_height(zeta, height, 1000.0)
                dbz = rain_dbz_proxy(
                    get("QRAIN"), get("P") + get("PB"),
                    get("T"), get("QVAPOR"),
                )
                rain_max = np.max(np.where(np.isfinite(dbz), dbz, -99.0), axis=0)
                rain_max = np.where(rain_max == -99.0, np.nan, rain_max)
                updraft = np.nanmax(get("W"), axis=0)
                records[time] = zeta1, rain_max, updraft, dx, dy
    origin = min(records)
    for time in sorted(records):
        minute = int(round((time - origin).total_seconds() / 60))
        yield minute, records[time]


def produce(run_dir, output_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from PIL import Image

    frames = list(model_frames(run_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    vortex_scale = max(
        1.0, max(float(np.nanmax(np.abs(values[0]))) * 1000
                 for _, values in frames)
    )
    series = []
    pictures = []
    for minute, (vort, dbz, updraft, dx, dy) in frames:
        ny, nx = vort.shape
        extent = (0, nx*dx/1000, 0, ny*dy/1000)
        fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), constrained_layout=True)
        im1 = axes[0].imshow(vort*1000, origin="lower", extent=extent,
                             vmin=-vortex_scale, vmax=vortex_scale, cmap="RdBu_r")
        fig.colorbar(im1, ax=axes[0], label="Vorticidade vertical (10⁻³ s⁻¹)")
        axes[0].set_title("Vorticidade vertical perto de 1 km AGL")
        im2 = axes[1].imshow(np.ma.masked_invalid(dbz), origin="lower",
                             extent=extent, vmin=0, vmax=60, cmap="turbo")
        fig.colorbar(im2, ax=axes[1], label="dBZ proxy: somente chuva")
        axes[1].set_title("Refletividade aproximada (não é radar real)")
        for ax in axes:
            ax.set(xlabel="Distância L-O (km)", ylabel="Distância S-N (km)")
        fig.suptitle(f"WRF PALMAS V0.3 | Idealizada | T+{minute:03d} min"
                     f" | W máx {np.nanmax(updraft):.1f} m/s")
        name = f"diagnosticos_t{minute:04d}.png"
        fig.savefig(output_dir / name, dpi=120)
        plt.close(fig)
        with Image.open(output_dir / name) as im:
            pictures.append(im.convert("RGB"))
        finite = dbz[np.isfinite(dbz)]
        series.append({
            "minute": minute,
            "max_w_ms": round(float(np.nanmax(updraft)), 3),
            "max_abs_vorticity_s1": round(float(np.nanmax(np.abs(vort))), 6),
            "max_rain_proxy_dbz": round(float(finite.max()), 2) if finite.size else None,
            "png": name,
        })
    pictures[0].save(output_dir / "v03_vorticidade_e_chuva.gif", save_all=True,
                     append_images=pictures[1:], duration=750, loop=0)
    for pic in pictures:
        pic.close()
    result = {
        "description": "WRF idealized case em_quarter_ss (not observed weather)",
        "vorticity": "relative zeta=dv/dx-du/dy at nearest 1km AGL",
        "reflectivity": "approximate warm-rain Marshall-Palmer proxy, NOT WRF full radar",
        "frame_count": len(series),
        "simulated_minutes": series[-1]["minute"],
        "frames": series,
    }
    (output_dir / "diagnostics_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("V0.3 diagnostics:", len(series), "frames;", series[-1]["minute"], "min")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    produce(args.run_dir, args.out_dir)
