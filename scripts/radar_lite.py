#!/usr/bin/env python3
"""WRF-PALMAS Radar Lite 0.1: CPU-only model-to-radar prototype.

Uses actual WRF REFL_10CM and, where available, mass-level winds/height.
Its output is a simulated model-derived product, NOT an observed radar scan.
The included analytic demo is explicitly identified as non-WRF/non-observed.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

EARTH_KM = 6371.0
G = 9.81


def _two_d(var, index: int):
    import numpy as np
    selection = var[index] if var.ndim == 3 else var[:]
    return np.asarray(np.ma.filled(selection, np.nan), dtype=np.float32)


def _layer(var, index: int, level: int):
    import numpy as np
    return np.asarray(np.ma.filled(var[index, level, :, :], np.nan), dtype=np.float32)


def _wind(var, index: int, level: int, ny: int, nx: int, direction: str):
    """Read only one WRF staggered model level at a time."""
    import numpy as np
    arr = _layer(var, index, level)
    if direction == "u" and arr.shape == (ny, nx + 1):
        arr = (arr[:, :-1] + arr[:, 1:]) * 0.5
    elif direction == "v" and arr.shape == (ny + 1, nx):
        arr = (arr[:-1, :] + arr[1:, :]) * 0.5
    if arr.shape != (ny, nx):
        raise ValueError(f"Unexpected WRF {direction} grid: {arr.shape}; expected {ny}x{nx}")
    return arr


def fold_velocity(velocity, nyquist: float):
    if nyquist <= 0:
        raise ValueError("Nyquist must be positive")
    return (velocity + nyquist) % (2 * nyquist) - nyquist


def sample_frame(ds, index: int, *, site_lat: float | None = None,
                 site_lon: float | None = None, elevation_deg: float = 0.5,
                 nyquist: float = 27.0, range_km: float = 140.0) -> dict:
    """Approximate PPI sampled at WRF mass-grid centers, not at polar radials.

    Height is calculated from PH+PHB when provided.  If absent, use the real
    vertically-maximum model reflectivity and suppress the pseudo-PPI velocity.
    """
    import numpy as np
    variables = ds.variables
    if "REFL_10CM" not in variables:
        raise ValueError("WRF REFL_10CM absent: no radar-like product can be derived")
    for name in ("XLAT", "XLONG"):
        if name not in variables:
            raise ValueError(f"WRF variable {name} absent")
    lat = _two_d(variables["XLAT"], index)
    lon = _two_d(variables["XLONG"], index)
    ny, nx = lat.shape
    if lon.shape != lat.shape:
        raise ValueError("XLAT/XLONG inconsistent dimensions")
    if site_lat is None:
        site_lat = float(lat[ny // 2, nx // 2])
    if site_lon is None:
        site_lon = float(lon[ny // 2, nx // 2])
    # WGS84 small-domain tangent-plane approximation. WRF domain <~400 km.
    x = (lon - site_lon) * (111.32 * math.cos(math.radians(site_lat)))
    y = (lat - site_lat) * 110.574
    dist = np.hypot(x, y)
    inside = (dist <= range_km) & np.isfinite(lat) & np.isfinite(lon)
    if not np.any(inside):
        raise ValueError("Radar site is outside WRF grid / range")
    earth_radial_x = x / np.maximum(dist, 0.001)
    earth_radial_y = y / np.maximum(dist, 0.001)
    elev = math.radians(elevation_deg)
    # Standard 4/3-earth beam path: height above site (m).
    beam_above_site_m = (dist * math.tan(elev) +
                         (dist ** 2) / (2 * (4 / 3) * EARTH_KM)) * 1000
    nearest = np.unravel_index(np.argmin(dist), dist.shape)
    terrain = _two_d(variables["HGT"], index) if "HGT" in variables else np.zeros_like(lat)
    target_msl = beam_above_site_m + float(terrain[nearest])

    reflect = variables["REFL_10CM"]
    if reflect.ndim == 3:
        dbz = np.asarray(np.ma.filled(reflect[index], np.nan), dtype=np.float32)
        if dbz.shape != (ny, nx):
            raise ValueError("Unexpected 2D reflectivity dimensions")
        mode, velocity = "2d_model_reflectivity", np.full_like(dbz, np.nan)
    elif reflect.ndim == 4:
        nz = reflect.shape[1]
        heights = all(name in variables for name in ("PH", "PHB"))
        if not heights:
            dbz = np.full((ny, nx), -np.inf, np.float32)
            for k in range(nz):
                dbz = np.fmax(dbz, _layer(reflect, index, k))
            dbz[~np.isfinite(dbz)] = np.nan
            velocity = np.full_like(dbz, np.nan)
            mode = "vertical_max_no_beam_heights"
        else:
            mode = "model_height_sampled_ppi"
            dbz = np.full((ny, nx), np.nan, np.float32)
            velocity = np.full((ny, nx), np.nan, np.float32)
            best = np.full((ny, nx), np.inf, np.float32)
            has_winds = "U" in variables and "V" in variables
            rotation = ("COSALPHA" in variables and "SINALPHA" in variables)
            if rotation:
                cos_a = _two_d(variables["COSALPHA"], index)
                sin_a = _two_d(variables["SINALPHA"], index)
            for k in range(nz):
                # Read one vertical slice (and two staggered geopotential slices)
                # instead of materializing a 4D field in RAM.
                height = (_layer(variables["PH"], index, k) +
                          _layer(variables["PHB"], index, k) +
                          _layer(variables["PH"], index, k + 1) +
                          _layer(variables["PHB"], index, k + 1)) / (2 * G)
                delta = np.abs(height - target_msl)
                pick = inside & (delta < best)
                if not np.any(pick):
                    continue
                best[pick] = delta[pick]
                dbz_layer = _layer(reflect, index, k)
                dbz[pick] = dbz_layer[pick]
                if has_winds:
                    u = _wind(variables["U"], index, k, ny, nx, "u")
                    v = _wind(variables["V"], index, k, ny, nx, "v")
                    if rotation:
                        u, v = u * cos_a - v * sin_a, v * cos_a + u * sin_a
                    vr = math.cos(elev) * (u * earth_radial_x + v * earth_radial_y)
                    if "W" in variables:
                        # W is vertically staggered. Two adjacent levels are averaged.
                        w = (_layer(variables["W"], index, k) +
                             _layer(variables["W"], index, k + 1)) * 0.5
                        vr += math.sin(elev) * w
                    velocity[pick] = fold_velocity(vr[pick], nyquist)
    else:
        raise ValueError("REFL_10CM must have 3 or 4 dimensions")

    dbz[~inside | (dbz < 5)] = np.nan
    velocity[~inside | ~np.isfinite(dbz)] = np.nan
    if "Times" in variables:
        from netCDF4 import chartostring
        timestamp = str(chartostring(variables["Times"][index:index+1])[0])
    else:
        timestamp = f"frame-{index:03d}"
    return {
        "dbz": dbz, "velocity": velocity, "x_km": x, "y_km": y,
        "site_lat": site_lat, "site_lon": site_lon, "timestamp": timestamp,
        "sampling_mode": mode, "has_velocity": bool(np.any(np.isfinite(velocity))),
        "elevation_deg": elevation_deg, "nyquist_mps": nyquist,
        "range_km": range_km, "max_dbz": float(np.nanmax(dbz)) if
        np.any(np.isfinite(dbz)) else None,
    }


def make_demo(path: Path, *, frames: int = 8, grid: int = 100) -> None:
    """Small ANALYTIC storm fixture to exercise the pipeline, not a WRF run."""
    import numpy as np
    from netCDF4 import Dataset
    path.parent.mkdir(parents=True, exist_ok=True)
    nz = 8
    lat0, lon0 = -27.30, -52.30
    xx, yy = np.meshgrid((np.arange(grid) - grid // 2) * 2.0,
                         (np.arange(grid) - grid // 2) * 2.0)
    lat = lat0 + yy / 110.574
    lon = lon0 + xx / (111.32 * math.cos(math.radians(lat0)))
    with Dataset(path, "w", format="NETCDF4") as ds:
        for name, n in (("Time", frames), ("DateStrLen", 19), ("bottom_top", nz),
                        ("bottom_top_stag", nz + 1), ("south_north", grid),
                        ("west_east", grid), ("west_east_stag", grid + 1),
                        ("south_north_stag", grid + 1)):
            ds.createDimension(name, n)
        def v(name, dims):
            return ds.createVariable(name, "f4", dims, zlib=True, complevel=1)
        dim2 = ("Time", "south_north", "west_east")
        dim3 = ("Time", "bottom_top", "south_north", "west_east")
        dimh = ("Time", "bottom_top_stag", "south_north", "west_east")
        latv = v("XLAT", dim2); lonv = v("XLONG", dim2)
        hgt = v("HGT", dim2)
        phi = v("PH", dimh); phb = v("PHB", dimh)
        refl = v("REFL_10CM", dim3)
        uv = v("U", ("Time", "bottom_top", "south_north", "west_east_stag"))
        vv = v("V", ("Time", "bottom_top", "south_north_stag", "west_east"))
        times = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
        geo = np.float32(G * 260)
        levels = np.array([0, 250, 600, 1150, 1850, 2800, 4000, 5500, 7250], np.float32)
        for t in range(frames):
            latv[t] = lat; lonv[t] = lon; hgt[t] = 260
            for k in range(nz + 1):
                phb[t, k] = geo + G * levels[k]
                phi[t, k] = 0
            stamp = (datetime(2027, 4, 15, 22, tzinfo=timezone.utc) +
                     timedelta(minutes=5 * t)).strftime("%Y-%m-%d_%H:%M:%S")
            times[t] = np.array(list(stamp), dtype="S1")
            cx, cy = 25 + 2.4 * t, 4 + 1.1 * t
            dx, dy = xx - cx, yy - cy
            theta = np.arctan2(dy, dx)
            radius = np.hypot(dx, dy)
            broad = np.exp(-((dx + 6) / 37)**2 - ((dy - 10) / 22)**2)
            core = np.exp(-((dx - 4) / 13)**2 - ((dy + 4) / 11)**2)
            hook = np.exp(-((radius - 18) / 5)**2) * np.exp(-((theta + 1.6) / 1.1)**2)
            # Analytic geometry is only a demonstration of file flow.
            base = 8 + 21*broad + 38*core + 20*hook
            swirl = 30 * np.exp(-(radius/16)**2) / np.maximum(radius, 2)
            wind_u = 12 - swirl * dy
            wind_v = 9 + swirl * dx
            for k in range(nz):
                refl[t, k] = np.maximum(0, base * (1 - 0.055 * k) - 2 * k)
                # Staggered WRF U/V: reconstruct edge values by a safe repeat.
                uv[t, k] = np.pad(wind_u, ((0, 0), (0, 1)), mode="edge")
                vv[t, k] = np.pad(wind_v, ((0, 1), (0, 0)), mode="edge")
        ds.title = "WRF PALMAS Radar Lite - ANALYTIC TEST FIXTURE (NOT WRF)"


def render(frame: dict, path: Path, *, provenance: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap, LinearSegmentedColormap
    from matplotlib.patches import Circle
    import numpy as np

    bounds = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80]
    colors = ["#263b7e", "#1c6fb8", "#31aecf", "#229f5b", "#02cf3d",
              "#62e428", "#c3ed18", "#ffff22", "#ffc427", "#f58220",
              "#ee3536", "#b51546", "#be59d6", "#f0a8f4"]
    cmap = ListedColormap(colors); cmap.set_bad("#08131e")
    norm = BoundaryNorm(bounds, cmap.N)
    vcmap = LinearSegmentedColormap.from_list(
        "rv", [(0,"#02e76f"), (.22,"#137f45"), (.499,"#182b27"),
               (.50,"#10161c"), (.501,"#3d1d23"), (.78,"#c83a4b"), (1,"#ffe3c3")])
    vcmap.set_bad("#08131e")
    vmax = frame["nyquist_mps"]
    extent = (float(np.nanmin(frame["x_km"])), float(np.nanmax(frame["x_km"])),
              float(np.nanmin(frame["y_km"])), float(np.nanmax(frame["y_km"])))
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 6.45), dpi=110,
                             facecolor="#08111d", constrained_layout=True)
    plots = ((frame["dbz"], cmap, norm, "REFLETIVIDADE MODELADA", "dBZ"),
             (frame["velocity"], vcmap, None, "VELOCIDADE RADIAL MODELADA", "m/s"))
    for ax, (data, palette, scale, label, unit) in zip(axes, plots):
        ax.set_facecolor("#08131e")
        image = ax.imshow(data, origin="lower", extent=extent, interpolation="nearest",
                          cmap=palette, norm=scale, **({} if scale else
                          {"vmin": -vmax, "vmax": vmax}))
        ax.scatter([0], [0], marker="+", s=50, c="#fafafa", linewidths=1.1, zorder=8)
        for radius in (30, 60, 90, 120):
            if radius > frame["range_km"]: continue
            circle = Circle((0, 0), radius, fill=False, edgecolor="#6e8aa0",
                            linewidth=.6, alpha=.5)
            ax.add_patch(circle)
        ax.set_xlabel("E / O do radar (km)", color="#b7c7dc", fontsize=9)
        ax.set_ylabel("N / S do radar (km)", color="#b7c7dc", fontsize=9)
        ax.set_title(label, color="white", fontsize=10, fontweight="bold")
        ax.tick_params(colors="#8499ae", labelsize=8)
        for spine in ax.spines.values(): spine.set_color("#42556a")
        cb = fig.colorbar(image, ax=ax, orientation="horizontal", fraction=.052, pad=.07)
        cb.ax.tick_params(colors="#bac9d8", labelsize=8)
        cb.set_label(unit, color="#bac9d8", fontsize=8)
        ax.set_aspect("equal", adjustable="box")
    fig.suptitle(f"PALMAS RADAR LITE 0.1   •   {frame['timestamp']} UTC   •   "
                 f"{frame['elevation_deg']:.1f}°   •   {provenance}",
                 color="#d8e4f5", fontsize=11, fontweight="bold")
    fig.text(.5, .015, "PRODUTO EXPERIMENTAL SIMULADO — NAO E RADAR OBSERVADO",
             ha="center", va="bottom", fontsize=9, color="#ffcf79")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Render and validate in memory first. Some remote filesystems have returned
    # truncated PNGs from direct multi-frame Matplotlib file writes.
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    png = buffer.getvalue()
    from PIL import Image
    with Image.open(io.BytesIO(png)) as im:
        im.verify()
    for attempt in range(3):
        path.write_bytes(png)
        try:
            with Image.open(path) as im:
                im.verify()
            break
        except (OSError, SyntaxError):
            if attempt == 2:
                raise


def run(paths: list[Path], output: Path, *, provenance: str,
        site_lat: float | None, site_lon: float | None, elevation_deg: float,
        nyquist: float, range_km: float, max_frames: int = 16) -> dict:
    from netCDF4 import Dataset
    from PIL import Image
    start = time.perf_counter()
    output.mkdir(parents=True, exist_ok=True)
    entries = []
    image_paths = []
    for path in paths:
        with Dataset(path, "r") as ds:
            n = len(ds.dimensions["Time"])
            for index in range(n):
                if len(entries) >= max_frames: break
                frame = sample_frame(ds, index, site_lat=site_lat, site_lon=site_lon,
                                     elevation_deg=elevation_deg, nyquist=nyquist,
                                     range_km=range_km)
                destination = output / f"radar_{len(entries):03d}.png"
                render(frame, destination, provenance=provenance)
                image_paths.append(destination)
                entries.append({key: frame[key] for key in (
                    "timestamp", "sampling_mode", "has_velocity", "max_dbz")})
            if len(entries) >= max_frames: break
    if not entries:
        raise ValueError("No frames could be read")
    gif_path = output / "radar_lite_loop.gif"
    # Loading one frame at a time is also possible but Pillow's GIF encoder
    # needs frames to encode.  Limit --max-frames to avoid excessive RAM.
    frames = []
    try:
        for path in image_paths:
            with Image.open(path) as im:
                frames.append(im.convert("RGB"))
        frames[0].save(gif_path, save_all=True, append_images=frames[1:],
                       duration=650, loop=0, optimize=False)
    finally:
        for im in frames: im.close()
    # resource is POSIX only; retain Windows compatibility on the user's PC.
    try:
        import resource
        peak_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except ImportError:
        peak_mib = None
    manifest = {
        "product": "WRF PALMAS RADAR LITE 0.1",
        "provenance": provenance,
        "observed_radar": False,
        "ARHT_engine_used": False,
        "source_files": [p.name for p in paths],
        "frames": entries,
        "frame_count": len(entries),
        "radar_site": {"lat": frame["site_lat"], "lon": frame["site_lon"]},
        "elevation_deg": elevation_deg,
        "nyquist_mps": nyquist,
        "range_km": range_km,
        "peak_process_rss_mib": round(peak_mib, 1) if peak_mib is not None else None,
        "elapsed_seconds": round(time.perf_counter() - start, 2),
        "gif": gif_path.name,
        "disclaimer": "Simulated WRF/model product; not observed radar or warning data.",
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--demo", action="store_true", help="Generate analytic demo fixture")
    src.add_argument("--run-dir", type=Path, help="Directory containing WRF wrfout_d01_*")
    parser.add_argument("--out-dir", type=Path, default=Path("results/radar-lite"))
    parser.add_argument("--site-lat", type=float)
    parser.add_argument("--site-lon", type=float)
    parser.add_argument("--elevation", type=float, default=0.5)
    parser.add_argument("--nyquist", type=float, default=27.0)
    parser.add_argument("--range-km", type=float, default=140.0)
    parser.add_argument("--max-frames", type=int, default=12)
    args = parser.parse_args()
    if args.max_frames < 1 or args.max_frames > 30:
        parser.error("--max-frames must be between 1 and 30")
    if args.demo:
        path = args.out_dir / "demo_analytic_fixture.nc"
        make_demo(path, frames=min(args.max_frames, 10))
        paths = [path]
        provenance = "DEMO ANALITICA — SEM WRF"
    else:
        paths = sorted(args.run_dir.glob("wrfout_d01_*"))
        if not paths:
            parser.error(f"No wrfout_d01_* files in {args.run_dir}")
        provenance = "WRF REFL_10CM — PRODUTO MODELADO"
    result = run(paths, args.out_dir, provenance=provenance,
                 site_lat=args.site_lat, site_lon=args.site_lon,
                 elevation_deg=args.elevation, nyquist=args.nyquist,
                 range_km=args.range_km, max_frames=args.max_frames)
    print(json.dumps({key: value for key, value in result.items()
                      if key != "frames"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
