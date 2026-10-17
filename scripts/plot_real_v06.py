#!/usr/bin/env python3
"""WRF PALMAS V0.6: geographically referenced PNGs/GIFs from saved wrfout.

No WRF integration is done here. Maps are experimental, not operational.
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

# Reference markers: WGS84, shown only if inside the actual WRF domain.
CITIES = {
    "Curitiba": (-25.43, -49.27),
    "Cascavel": (-24.96, -53.46),
    "Foz do Iguaçu": (-25.55, -54.59),
    "Chapecó": (-27.10, -52.62),
    "Florianópolis": (-27.59, -48.55),
    "Porto Alegre": (-30.03, -51.23),
    "Passo Fundo": (-28.26, -52.41),
    "Pato Branco": (-26.23, -52.67),
    "Erechim": (-27.64, -52.27),
    "Palmas (PR)": (-26.49, -51.99),
}
REGIONS = {
    "PR": (-25.8, -51.6), "SC": (-27.35, -50.8),
    "RS": (-29.4, -52.8),
    "ARGENTINA": (-27.8, -55.9), "PARAGUAI": (-24.2, -55.9),
}
RADAR_LEVELS = [-10, 0, 10, 20, 30, 40, 50, 60, 70, 80, 90]
RADAR_COLORS = [
    "#9da6c8", "#71c5ff", "#19e73d", "#02882b", "#d1ea16",
    "#ffe216", "#ff8c12", "#e10d22", "#ffb8e8", "#9f22d4",
]


def rain_total(variables, index):
    import numpy as np
    parts = [np.asarray(variables[name][index], dtype=float)
             for name in ("RAINC", "RAINNC") if name in variables]
    if not parts:
        return None
    return np.sum(parts, axis=0)


def reflectivity(variables, index):
    """Prefer WRF REFL_10CM; never invent 'radar' from rain accumulation."""
    import numpy as np
    if "REFL_10CM" not in variables:
        return None, "REFL_10CM ausente (sem diagnóstico de refletividade)"
    arr = np.asarray(variables["REFL_10CM"][index], dtype=float)
    if arr.ndim == 3:
        arr = np.nanmax(arr, axis=0)
        label = "Máximo vertical REFL_10CM (dBZ modelado)"
    elif arr.ndim == 2:
        label = "REFL_10CM (dBZ modelado)"
    else:
        raise ValueError("Unexpected REFL_10CM rank")
    return np.ma.masked_where(~np.isfinite(arr) | (arr < 0), arr), label


def draw_geography(ax, lon, lat, coast, borders, admin, transform):
    import numpy as np
    from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER

    x0, x1 = float(np.nanmin(lon)), float(np.nanmax(lon))
    y0, y1 = float(np.nanmin(lat)), float(np.nanmax(lat))
    margin_x, margin_y = (x1-x0)*0.025, (y1-y0)*0.025
    ax.set_extent([x0-margin_x, x1+margin_x, y0-margin_y, y1+margin_y],
                  crs=transform)
    ax.add_feature(coast, linewidth=0.8, edgecolor="#202020", zorder=5)
    ax.add_feature(borders, linewidth=1.25, edgecolor="black", zorder=6)
    ax.add_feature(admin, linewidth=0.7, edgecolor="#303030", zorder=5)
    gl = ax.gridlines(draw_labels={"bottom": "x", "left": "y"},
                      linewidth=0.38, color="#333333",
                      alpha=0.45, linestyle=":")
    gl.xformatter, gl.yformatter = LONGITUDE_FORMATTER, LATITUDE_FORMATTER
    gl.xlabel_style = {"size": 8}
    gl.ylabel_style = {"size": 8}
    # Only label cities which really fall within the plotted domain.
    for name, (yy, xx) in CITIES.items():
        if x0 < xx < x1 and y0 < yy < y1:
            ax.plot(xx, yy, "o", markersize=3.2, color="black",
                    markeredgecolor="white", markeredgewidth=0.5,
                    transform=transform, zorder=10)
            ax.annotate(name, (xx, yy), xytext=(4, 3),
                        textcoords="offset points", fontsize=7.0,
                        color="black", weight="bold", transform=transform,
                        path_effects=__outline(), zorder=11)
    for name, (yy, xx) in REGIONS.items():
        if x0 + 0.2 < xx < x1 - 0.2 and y0 + 0.2 < yy < y1 - 0.2:
            ax.text(xx, yy, name, transform=transform,
                    fontsize=9, alpha=0.7, weight="bold",
                    horizontalalignment="center", zorder=8,
                    path_effects=__outline())


def __outline():
    import matplotlib.patheffects as pe
    return [pe.withStroke(linewidth=2.3, foreground="white", alpha=0.88)]


def save_gif(frames, dest, duration_ms=900):
    from PIL import Image
    if not frames:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    pictures = []
    try:
        for source in frames:
            with Image.open(source) as img:
                pictures.append(img.convert("RGB"))
        pictures[0].save(dest, format="GIF", save_all=True,
                         append_images=pictures[1:], duration=duration_ms,
                         loop=0, optimize=True)
    finally:
        for picture in pictures:
            picture.close()


def plot_run(run_dir: Path, out_dir: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    import numpy as np
    from netCDF4 import Dataset, chartostring
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature

    paths = sorted(run_dir.glob("wrfout_d01_*"))
    if not paths:
        raise FileNotFoundError(f"WRF output missing: {run_dir}/wrfout_d01_*")
    out_dir.mkdir(parents=True, exist_ok=True)

    projection = ccrs.PlateCarree()
    # Natural Earth 50m vector boundaries, cached by Cartopy.
    features = (
        cfeature.NaturalEarthFeature("physical", "coastline", "50m",
                                    facecolor="none"),
        cfeature.NaturalEarthFeature("cultural", "admin_0_boundary_lines_land",
                                    "50m", facecolor="none"),
        cfeature.NaturalEarthFeature("cultural", "admin_1_states_provinces_lines",
                                    "50m", facecolor="none"),
    )
    products = {"t2": [], "rain": [], "refl": []}
    records = []
    current = 0
    for path in paths:
        with Dataset(path) as ds:
            v = ds.variables
            missing = set(("Times", "XLAT", "XLONG", "T2", "U10", "V10")) - set(v)
            if missing:
                raise ValueError(f"Missing WRF variables {sorted(missing)}")
            for i, timestamp in enumerate(chartostring(v["Times"][:])):
                lon = np.asarray(v["XLONG"][i], dtype=float)
                lat = np.asarray(v["XLAT"][i], dtype=float)
                temp = np.asarray(v["T2"][i], dtype=float) - 273.15
                u = np.asarray(v["U10"][i], dtype=float)
                w = np.asarray(v["V10"][i], dtype=float)
                rain = rain_total(v, i)
                refl, refl_info = reflectivity(v, i)
                panels = [
                    ("t2", temp, "Temperatura a 2 m + vento a 10 m",
                     "°C", "coolwarm", None),
                ]
                if rain is not None:
                    panels.append(("rain", rain,
                                   "Precipitação acumulada desde o início",
                                   "mm", "YlGnBu", None))
                if refl is not None:
                    palette = ListedColormap(RADAR_COLORS)
                    palette.set_bad("#ffffff")
                    panels.append(("refl", refl,
                                   refl_info, "dBZ", palette,
                                   BoundaryNorm(RADAR_LEVELS, palette.N)))
                record = {"utc": str(timestamp),
                          "max_wind10_ms": round(float(np.nanmax(np.hypot(u, w))), 2),
                          "refl_status": refl_info,
                          "products": {}}
                for label, field, heading, unit, cmap, norm in panels:
                    fig = plt.figure(figsize=(10.2, 8.0))
                    ax = fig.add_subplot(111, projection=projection)
                    options = {"cmap": cmap, "shading": "auto",
                               "transform": projection}
                    if norm is not None:
                        options["norm"] = norm
                    im = ax.pcolormesh(lon, lat, field, **options)
                    draw_geography(ax, lon, lat, *features, transform=projection)
                    fig.colorbar(im, ax=ax, fraction=0.042, pad=0.035,
                                 label=unit, shrink=0.83)
                    if label == "t2":
                        stride = max(1, min(temp.shape)//14)
                        ax.quiver(lon[::stride, ::stride], lat[::stride, ::stride],
                                  u[::stride, ::stride], w[::stride, ::stride],
                                  transform=projection, scale=270,
                                  width=0.0025, zorder=7)
                    ax.set_title(f"WRF PALMAS V0.6 — {heading}\n"
                                 f"{timestamp} UTC | GFS → WRF 9 km | EXPERIMENTAL",
                                 fontsize=12)
                    dest = out_dir / label / f"{label}_{current:03}.png"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    fig.savefig(dest, dpi=120, bbox_inches="tight")
                    plt.close(fig)
                    products[label].append(dest)
                    record["products"][label] = str(dest.relative_to(out_dir))
                records.append(record)
                current += 1
    for label, filenames in products.items():
        save_gif(filenames, out_dir / "gifs" / f"{label}_anim.gif")
    result = {
        "project": "WRF PALMAS V0.6",
        "data": "Real GFS-driven WRF regional pilot, geography lowres",
        "not_operational": True,
        "geographic_layers": "Natural Earth 50m borders, states/provinces and coasts",
        "frames": records,
        "num_times": len(records),
        "gif_products": [str(Path("gifs") / f"{k}_anim.gif")
                         for k, v in products.items() if v],
        "unavailable": [k for k, v in products.items() if not v],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"frames": len(records), "gifs": result["gif_products"],
                      "unavailable": result["unavailable"]}, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", required=True, type=Path)
    p.add_argument("--out-dir", required=True, type=Path)
    a = p.parse_args()
    plot_run(a.run_dir, a.out_dir)
