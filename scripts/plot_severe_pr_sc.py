#!/usr/bin/env python3
"""Experimental PR/SC severe-weather diagnostics from real WRF history files.

Plots WRF-native 10-cm simulated reflectivity, 0–1/0–6 km shear,
and coarse-sampled *surface-based* CAPE/CIN from MetPy parcel calculations.
CAPE here is SBCAPE on a sparse subset, not MLCAPE/MUCAPE; no calibrated
tornado probabilities or warning categories are implied.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def earth_relative(u, v, cosalpha, sinalpha):
    return u * cosalpha - v * sinalpha, v * cosalpha + u * sinalpha


def interpolate_agl(z, field, meters):
    import numpy as np
    # z and field: (vertical, y, x), z from the ground in metres.
    # Using first available level at heights below model mass grid bottom.
    nlevels = z.shape[0]
    above = np.sum(z < meters, axis=0)
    upper = np.clip(above, 1, nlevels - 1)
    lower = upper - 1
    z0 = np.take_along_axis(z, lower[None, ...], axis=0)[0]
    z1 = np.take_along_axis(z, upper[None, ...], axis=0)[0]
    f0 = np.take_along_axis(field, lower[None, ...], axis=0)[0]
    f1 = np.take_along_axis(field, upper[None, ...], axis=0)[0]
    weight = np.clip((meters - z0) / np.maximum(z1 - z0, 1.), 0, 1)
    values = f0 + (f1 - f0) * weight
    return np.where(z[-1] >= meters, values, np.nan)


def shear_fields(variables, index):
    import numpy as np
    g = 9.80665
    height_stag = (
        np.asarray(variables["PH"][index], dtype=float)
        + np.asarray(variables["PHB"][index], dtype=float)
    ) / g
    z = 0.5 * (height_stag[:-1] + height_stag[1:]) - height_stag[0]
    staggered_u = np.asarray(variables["U"][index], dtype=float)
    staggered_v = np.asarray(variables["V"][index], dtype=float)
    u = 0.5 * (staggered_u[:, :, :-1] + staggered_u[:, :, 1:])
    v = 0.5 * (staggered_v[:, :-1, :] + staggered_v[:, 1:, :])
    c = (np.asarray(variables["COSALPHA"][index], dtype=float)
         if "COSALPHA" in variables else np.ones_like(u[0]))
    s = (np.asarray(variables["SINALPHA"][index], dtype=float)
         if "SINALPHA" in variables else np.zeros_like(u[0]))
    u, v = earth_relative(u, v, c, s)
    result = {}
    for altitude in (1000., 6000.):
        ut = interpolate_agl(z, u, altitude)
        vt = interpolate_agl(z, v, altitude)
        # First mass grid ≈ near-surface; not exactly a measured zero-metre wind.
        result[f"shear{int(altitude/1000)}"] = np.hypot(ut - u[0], vt - v[0])
    return result


def surface_parcel_cape(variables, index, stride=12):
    """Calculate legitimate SBCAPE/CIN at sampled columns; do not interpolate it as full resolution."""
    import numpy as np
    import metpy.calc as mpcalc
    from metpy.units import units

    pressure = (
        np.asarray(variables["P"][index], dtype=float)
        + np.asarray(variables["PB"][index], dtype=float))
    theta = np.asarray(variables["T"][index], dtype=float) + 300.
    temp_k = theta * (pressure / 100000.) ** 0.2854
    mixing = np.clip(np.asarray(variables["QVAPOR"][index], dtype=float), 0, 0.1)
    vapor_pressure = np.clip(pressure * mixing / (0.622 + mixing), 1., None)
    ln = np.log(vapor_pressure / 611.2)
    dew_k = 243.5 * ln / (17.67 - ln) + 273.15

    ny, nx = pressure.shape[1:]
    iy = np.arange(0, ny, stride)
    ix = np.arange(0, nx, stride)
    cape = np.full((len(iy), len(ix)), np.nan)
    cin = np.full_like(cape, np.nan)
    failed = 0
    for j, y in enumerate(iy):
        for k, x in enumerate(ix):
            p = pressure[:, y, x]
            t = temp_k[:, y, x]
            d = np.minimum(dew_k[:, y, x], t)
            valid = np.isfinite(p) & np.isfinite(t) & np.isfinite(d)
            if valid.sum() < 12:
                failed += 1
                continue
            # Pressure descending for a model profile (surface to top).
            p, t, d = p[valid], t[valid], d[valid]
            order = np.argsort(-p)
            p, t, d = p[order], t[order], d[order]
            unique = np.r_[True, np.diff(p) < -1.]
            p, t, d = p[unique], t[unique], d[unique]
            if len(p) < 12:
                failed += 1
                continue
            try:
                c, n = mpcalc.surface_based_cape_cin(
                    p * units.pascal, t * units.kelvin, d * units.kelvin
                )
                cape[j, k] = max(0., float(c.to("J/kg").magnitude))
                cin[j, k] = float(n.to("J/kg").magnitude)
            except (ValueError, IndexError, ZeroDivisionError, OverflowError):
                failed += 1
    return cape, cin, iy, ix, failed


def run(run_dir: Path, out_dir: Path, cape_stride=12):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from netCDF4 import Dataset, chartostring
    import cartopy.crs as ccrs
    import cartopy.feature as cf
    from plot_real_v06 import draw_geography, save_gif, reflectivity, RADAR_LEVELS, RADAR_COLORS

    files = sorted(run_dir.glob("wrfout_d01_*"))
    if not files:
        raise FileNotFoundError(f"No wrfout_d01_* in {run_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    features = (
        cf.NaturalEarthFeature("physical", "coastline", "50m", facecolor="none"),
        cf.NaturalEarthFeature("cultural", "admin_0_boundary_lines_land", "50m", facecolor="none"),
        cf.NaturalEarthFeature("cultural", "admin_1_states_provinces_lines", "50m", facecolor="none"),
    )
    projection = ccrs.PlateCarree()
    series = {x: [] for x in ("refl", "shear1", "shear6", "sbcape", "sbcin")}
    records = []
    for file in files:
        with Dataset(file) as ds:
            v = ds.variables
            for required in ("Times", "XLAT", "XLONG", "P", "PB", "T",
                             "QVAPOR", "U", "V", "PH", "PHB"):
                if required not in v:
                    raise ValueError(f"Missing {required} in {file}")
            for i, stamp in enumerate(chartostring(v["Times"][:])):
                lat = np.asarray(v["XLAT"][i], dtype=float)
                lon = np.asarray(v["XLONG"][i], dtype=float)
                shears = shear_fields(v, i)
                cape, cin, iy, ix, failed = surface_parcel_cape(v, i, cape_stride)
                refl, refl_desc = reflectivity(v, i)
                fields = [
                    ("shear1", shears["shear1"], lon, lat,
                     "Cisalhamento bulk ~0–1 km AGL", "m/s", "plasma", None),
                    ("shear6", shears["shear6"], lon, lat,
                     "Cisalhamento bulk ~0–6 km AGL", "m/s", "plasma", None),
                    ("sbcape", cape, lon[np.ix_(iy, ix)], lat[np.ix_(iy, ix)],
                     f"SBCAPE (amostra cada {cape_stride} células, sem interpolação)",
                     "J/kg", "turbo", None),
                    ("sbcin", cin, lon[np.ix_(iy, ix)], lat[np.ix_(iy, ix)],
                     f"SBCIN (amostra cada {cape_stride} células)",
                     "J/kg", "coolwarm", None),
                ]
                if refl is not None:
                    palette = ListedColormap(RADAR_COLORS)
                    fields.append(("refl", refl, lon, lat, refl_desc, "dBZ",
                                   palette, BoundaryNorm(RADAR_LEVELS, palette.N)))
                record = {
                    "utc": str(stamp),
                    "sbcape_sample_stride": cape_stride,
                    "sbcape_failed_columns": failed,
                    "sbcape_max_sample_jkg": (
                        round(float(np.nanmax(cape)), 1) if np.isfinite(cape).any() else None
                    ),
                    "products": {}, "reflectivity": refl_desc,
                }
                n = len(records)
                for name, values, x, y, label, unit, cmap, norm in fields:
                    fig = plt.figure(figsize=(10, 7))
                    ax = fig.add_subplot(111, projection=projection)
                    kwargs = dict(shading="auto", cmap=cmap, transform=projection)
                    if norm is not None:
                        kwargs["norm"] = norm
                    im = ax.pcolormesh(x, y, values, **kwargs)
                    draw_geography(ax, lon, lat, *features, transform=projection)
                    fig.colorbar(im, ax=ax, fraction=0.045, shrink=.83, label=unit)
                    ax.set_title(f"WRF PALMAS | PR + SC | {label}\n"
                                 f"{stamp} UTC | 6 km | EXPERIMENTAL", fontsize=10)
                    fileout = out_dir / name / f"{name}_{n:03d}.png"
                    fileout.parent.mkdir(parents=True, exist_ok=True)
                    fig.savefig(fileout, dpi=115, bbox_inches="tight")
                    plt.close(fig)
                    series[name].append(fileout)
                    record["products"][name] = str(fileout.relative_to(out_dir))
                records.append(record)

    for name, frames in series.items():
        save_gif(frames, out_dir / "gifs" / (name + ".gif"), duration_ms=650)
    summary = {
        "project": "WRF PALMAS inaugural PR/SC 2026-11-07",
        "model": "WRF real GFS-driven 6km",
        "not_operational": True,
        "sbcape_method": "MetPy surface_based_cape_cin on sparse mass-grid columns",
        "shear_method": "Earth-relative unstaggered model U/V, first mass level to interpolated AGL 1/6km",
        "num_times": len(records),
        "available_gifs": [f"gifs/{k}.gif" for k, v in series.items() if v],
        "unavailable": [k for k, v in series.items() if not v],
        "frames": records,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf8"
    )
    print(json.dumps({"num_times": len(records), "available": summary["available_gifs"],
                      "unavailable": summary["unavailable"]}))


if __name__ == "__main__":
    arg = argparse.ArgumentParser()
    arg.add_argument("--run-dir", type=Path, required=True)
    arg.add_argument("--out-dir", type=Path, required=True)
    arg.add_argument("--cape-stride", type=int, default=12)
    opts = arg.parse_args()
    run(opts.run_dir, opts.out_dir, opts.cape_stride)
