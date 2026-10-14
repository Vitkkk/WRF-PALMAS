#!/usr/bin/env python3
"""WRF PALMAS V0.4 - idealized three-panel storm evolution.

Inputs: physical WRF em_quarter_ss outputs. The warm-rain dBZ is a
Marshall-Palmer proxy, NOT observed radar or full WRF reflectivity.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# Radar-inspired stepped palette, deliberately authored (not an extracted
# palette from a proprietary radar system). Values below 0 dBZ are hidden.
RADAR_BOUNDS = [-30, -20, -10, 0, 10, 20, 30, 40, 50, 60, 70, 80, 90]
RADAR_COLORS = [
    "#B9AF9E",  # -30:-20
    "#CEC5B2",  # -20:-10
    "#415887",  # -10:0
    "#71BEE4",  # 0:10   light blue
    "#2BCC68",  # 10:20  green
    "#007F28",  # 20:30  dark green
    "#C6E91F",  # 30:40  yellow green
    "#FBE31B",  # 40:50  yellow
    "#FA840C",  # 50:60  orange
    "#D90C20",  # 60:70  red
    "#F5C5EB",  # 70:80  pale pink
    "#9724CB",  # 80:90  purple
]
RADAR_NO_ECHO = "#FFFFFF"


def radar_palette():
    """Return a discretized Matplotlib palette and bounds for rain-only dBZ."""
    from matplotlib.colors import BoundaryNorm, ListedColormap

    cmap = ListedColormap(RADAR_COLORS, name="palmas_radar_v04")
    cmap.set_bad(RADAR_NO_ECHO)
    cmap.set_under(RADAR_NO_ECHO)
    cmap.set_over("#063638")
    norm = BoundaryNorm(RADAR_BOUNDS, cmap.N)
    return cmap, norm


def rain_display_field(dbz):
    """Hide NaNs and <0 dBZ: those areas are not interpreted as radar echoes."""
    import numpy as np

    arr = np.asarray(dbz, dtype=float)
    return np.ma.masked_where(~np.isfinite(arr) | (arr < 0), arr)


def edge_echo(dbz, threshold=20.0, strip=3):
    """Diagnostic: strong precipitation touching any map border."""
    import numpy as np

    a = np.asarray(dbz, dtype=float)
    if a.ndim != 2:
        raise ValueError("Expected a 2D reflectivity field")
    return bool(
        np.any(a[:strip, :] >= threshold)
        or np.any(a[-strip:, :] >= threshold)
        or np.any(a[:, :strip] >= threshold)
        or np.any(a[:, -strip:] >= threshold)
    )


def render(run_dir: Path, out_dir: Path, frame_duration_ms: int = 720):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from PIL import Image
    from diagnostics_v03 import model_frames

    records = list(model_frames(run_dir))
    if len(records) < 2:
        raise ValueError("Need at least two simulation timestamps")
    if frame_duration_ms < 80:
        raise ValueError("GIF frame duration must be >=80 milliseconds")
    out_dir.mkdir(parents=True, exist_ok=True)

    radar_cmap, radar_norm = radar_palette()
    w_scale = max(1.0, max(float(np.nanmax(x[1][2])) for x in records))
    zeta_scale = max(
        1.0, max(float(np.nanmax(np.abs(x[1][0]))) * 1000.0 for x in records)
    )
    rendered = []
    summary = []

    for minute, (zeta1, dbz, wmax, dx, dy) in records:
        ny, nx = wmax.shape
        if zeta1.shape != wmax.shape or dbz.shape != wmax.shape:
            raise ValueError("Diagnostics must use identical mass-grid sizes")
        extent = [0, nx * dx / 1000, 0, ny * dy / 1000]
        x = (np.arange(nx) + 0.5) * dx / 1000
        y = (np.arange(ny) + 0.5) * dy / 1000
        vmax = float(np.nanmax(wmax))
        measured = dbz[np.isfinite(dbz)]

        fig, axes = plt.subplots(
            1, 3, figsize=(16, 5.6), constrained_layout=True
        )
        first = axes[0].imshow(
            wmax, origin="lower", extent=extent, cmap="turbo",
            vmin=0, vmax=w_scale, interpolation="nearest"
        )
        fig.colorbar(first, ax=axes[0], fraction=0.048, pad=0.03,
                     label="W máx coluna (m/s)")
        axes[0].set_title("Corrente ascendente\nmáxima da coluna")

        second = axes[1].imshow(
            1000.0 * zeta1, origin="lower", extent=extent,
            cmap="RdBu_r", vmin=-zeta_scale, vmax=zeta_scale,
            interpolation="nearest"
        )
        fig.colorbar(second, ax=axes[1], fraction=0.048, pad=0.03,
                     label="ζ relativa (10⁻³ s⁻¹)")
        axes[1].set_title("Vorticidade vertical relativa\n~1 km AGL")

        third = axes[2].imshow(
            rain_display_field(dbz), origin="lower", extent=extent,
            cmap=radar_cmap, norm=radar_norm, interpolation="nearest"
        )
        fig.colorbar(
            third, ax=axes[2], fraction=0.048, pad=0.03,
            ticks=RADAR_BOUNDS, label="dBZ aproximado (chuva líquida)",
            extend="max",
        )
        levels = [threshold for threshold in (10.0, 25.0)
                  if np.nanmin(wmax) < threshold <= vmax]
        if levels:
            contour = axes[2].contour(
                x, y, wmax, levels=levels,
                colors=["black" if level == 10 else "white" for level in levels],
                linewidths=0.9
            )
            axes[2].clabel(contour, fmt="%d m/s", fontsize=6)
        axes[2].set_title("Refletividade aprox. estilo radar\n"
                          "Contornos de W colunar 10/25 m/s")

        for ax in axes:
            ax.set_xlabel("Distância L-O (km)")
            ax.set_ylabel("Distância S-N (km)")
            ax.set_aspect("equal")

        fig.suptitle(
            f"WRF PALMAS V0.4 | Supercélula idealizada | T+{minute:03d} min"
            f" | W máximo {vmax:.1f} m/s",
            fontsize=13,
        )
        name = f"palmas_v04_t{minute:04d}.png"
        fig.savefig(out_dir / name, dpi=105)
        plt.close(fig)
        with Image.open(out_dir / name) as img:
            rendered.append(img.convert("RGB"))

        peak_y, peak_x = np.unravel_index(np.nanargmax(wmax), wmax.shape)
        summary.append({
            "minute": minute,
            "w_peak_ms": round(vmax, 3),
            "w_peak_x_km": round(float(x[peak_x]), 2),
            "w_peak_y_km": round(float(y[peak_y]), 2),
            "max_abs_vorticity_s1": round(float(np.nanmax(np.abs(zeta1))), 6),
            "max_rain_dbz_proxy": (
                round(float(measured.max()), 2) if measured.size else None
            ),
            "rain_echo_near_boundary": edge_echo(dbz),
            "image": name,
        })

    gif = "wrf_palmas_v04_triplo.gif"
    rendered[0].save(
        out_dir / gif, save_all=True, append_images=rendered[1:],
        duration=frame_duration_ms, loop=0
    )
    for img in rendered:
        img.close()

    result = {
        "experiment": "WRF em_quarter_ss, idealized atmosphere (not real weather)",
        "product": "V0.4 triple panel W / relative vorticity / rain-only radar proxy",
        "rain_proxy_note": "Marshall-Palmer warm rain only; NOT observed radar",
        "display_palette": "WRF PALMAS radar-inspired stepped  -30 to 90 dBZ",
        "no_echo_rule": "NaN and below 0 dBZ hidden as white",
        "reflectivity_contours": "maximum W in the atmospheric column at 10 and 25 m/s",
        "frame_count": len(summary),
        "simulated_minutes": summary[-1]["minute"],
        "grid_cells": list(records[0][1][2].shape),
        "grid_dx_m": records[0][1][3],
        "gif": gif,
        "frames": summary,
    }
    (out_dir / "summary_v04.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"V0.4 rendered {len(summary)} frames, T+{summary[-1]['minute']} min,"
          f" {len([s for s in summary if s['rain_echo_near_boundary']])}"
          " frames with >=20dBZ touching a border")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--frame-duration-ms", type=int, default=720)
    a = ap.parse_args()
    render(a.run_dir, a.out_dir, a.frame_duration_ms)
