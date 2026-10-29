#!/usr/bin/env python3
"""Read-only readiness check for the user-supplied third-party ARHT archive.

This tool never extracts, imports or executes the untrusted program.  The
original ARHT archive must not be republished without permission.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import zipfile
from pathlib import Path


CRITICAL = (
    "arhtmodelviewer/cpu/runtime/cuda_cpu.h",
    "arhtmodelviewer/cpu/runtime/cudacpu_rt.cpp",
    "arhtmodelviewer/cpu/kernels.py",
    "arhtmodelviewer/cpu/selftest.py",
    "arhtmodelviewer/engine.py",
)


def inspect(archive: Path, *, ram_gb: float = 8.0, grid: int = 100,
            levels: int = 30, max_ram_fraction: float = 0.65) -> dict:
    if not archive.is_file():
        raise FileNotFoundError(archive)
    if ram_gb <= 0 or grid <= 0 or levels <= 0 or not 0 < max_ram_fraction <= 1:
        raise ValueError("RAM, grade e niveis devem ser positivos")
    with zipfile.ZipFile(archive) as zf:
        names = [n.replace("\\", "/") for n in zf.namelist()]
        root = next((n.split("arhtmodelviewer/")[0] for n in names
                     if "arhtmodelviewer/cpu/kernels.py" in n), "")
        found = {name: root + name in names for name in CRITICAL}
        license_files = [n for n in names if Path(n).name.lower() in
                         {"license", "license.txt", "license.md", "copying"}]
        try:
            cpu_reqs = zf.read(root + "requirements-cpu.txt").decode("utf-8-sig")
        except KeyError:
            cpu_reqs = ""
    # ARHT engine rough estimate: 600 bytes/3D cell, NOT benchmarked.
    # Account for interpreter/compiled code and temporary arrays.
    cells = grid * grid * levels
    raw_gib = cells * 600 / (1024 ** 3)
    estimated_gib = raw_gib * 2.5 + 1.0
    missing = [p for p, ok in found.items() if not ok]
    status = "BLOCKED_MISSING_RUNTIME" if missing else (
        "BUDGET_RISK" if estimated_gib > ram_gb * max_ram_fraction else
        "PREFLIGHT_PASS_NOT_EXECUTED")
    return {
        "status": status,
        "archive": archive.name,
        "executed_original_program": False,
        "required_members": found,
        "missing_critical_members": missing,
        "license_detected": bool(license_files),
        "cpu_requirements": [line.strip() for line in cpu_reqs.splitlines()
                             if line.strip() and not line.lstrip().startswith("#")],
        "platform": platform.system(),
        "machine": platform.machine(),
        "cpu_threads_available": os.cpu_count(),
        "ram_budget_gib": round(ram_gb * max_ram_fraction, 2),
        "grid": [grid, grid, levels],
        "raw_engine_estimate_gib": round(raw_gib, 3),
        "conservative_total_estimate_gib": round(estimated_gib, 3),
        "estimate_is_not_measured": True,
        "notes": [
            "ARHT original nao foi executado nem alterado.",
            "A estimativa de memoria usa 600 bytes/celula vezes um fator de seguranca; nao e uma medicao.",
            "O motor CPU do ARHT original exige artefatos de compilacao e dependencias proprias.",
            "Nao publicar o ZIP original num repositorio publico sem permissao do autor.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="ARHT-MODEL Viewer 1.6.zip")
    parser.add_argument("--ram-gb", type=float, default=8.0)
    parser.add_argument("--grid", type=int, default=100)
    parser.add_argument("--levels", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = inspect(args.archive, ram_gb=args.ram_gb,
                     grid=args.grid, levels=args.levels)
    result = json.dumps(report, ensure_ascii=False, indent=2)
    print(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
