#!/usr/bin/env python3
"""Build the QGIS plugin zip and/or deploy the plugin by copying.

Two jobs `install.py` doesn't cover:

1. **Zip** (default): package `qgis_mcp_plugin/` into
   `dist/qgis_mcp_plugin-<version>.zip` with the plugin folder at the zip
   root — the exact layout QGIS's "Install from ZIP" and the QGIS plugin
   repository expect. Version is read from `qgis_mcp_plugin/metadata.txt`.

2. **Copy-deploy** (`--install`): copy the plugin into a QGIS profile's
   plugins folder, replacing what's there. Use this instead of install.py's
   symlink when the repo and QGIS live on different filesystems — e.g. the
   repo in WSL and QGIS on Windows, where a junction into the WSL ext4 tree
   is not resolvable by QGIS — or whenever you want a frozen copy rather
   than a live link.

Usage:
    python scripts/deploy.py                       # build dist zip only
    python scripts/deploy.py --install             # zip + copy into QGIS profile
    python scripts/deploy.py --install --plugins-dir "/mnt/c/Users/me/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins"
    python scripts/deploy.py --install --profile someprofile --qgis-version 3

After a copy-deploy, restart QGIS (or reload the plugin) to load the new
code — the running plugin keeps executing the old code from memory.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
PLUGIN_SRC = REPO_DIR / "qgis_mcp_plugin"
DIST_DIR = REPO_DIR / "dist"
EXCLUDE_DIRS = {"__pycache__"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}

sys.path.insert(0, str(REPO_DIR))
from install import qgis_plugins_dir  # noqa: E402  (path helpers, resolved at call time)


def plugin_version() -> str:
    meta = (PLUGIN_SRC / "metadata.txt").read_text(encoding="utf-8")
    m = re.search(r"^version=(.+)$", meta, re.MULTILINE)
    if not m:
        sys.exit("Could not read version from qgis_mcp_plugin/metadata.txt")
    return m.group(1).strip()


def _plugin_files():
    for p in sorted(PLUGIN_SRC.rglob("*")):
        rel = p.relative_to(PLUGIN_SRC)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if p.suffix in EXCLUDE_SUFFIXES:
            continue
        if p.is_file():
            yield p, rel


def build_zip() -> Path:
    version = plugin_version()
    DIST_DIR.mkdir(exist_ok=True)
    out = DIST_DIR / f"qgis_mcp_plugin-{version}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p, rel in _plugin_files():
            zf.write(p, Path("qgis_mcp_plugin") / rel)
    n = len(zf.namelist())
    print(f"  [ok] {out}  ({n} files, v{version})")
    return out


def copy_deploy(plugins_dir: Path) -> Path:
    target = plugins_dir / "qgis_mcp_plugin"
    if target.is_symlink():
        sys.exit(
            f"{target} is a symlink (install.py-managed). Remove it first or "
            "keep using the symlink workflow."
        )
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    count = 0
    for p, rel in _plugin_files():
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)
        count += 1
    print(f"  [ok] copied {count} files -> {target}")
    return target


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--install", action="store_true", help="also copy-deploy into a QGIS profile")
    ap.add_argument("--plugins-dir", help="explicit QGIS plugins folder (overrides profile detection)")
    ap.add_argument("--profile", default="default", help="QGIS profile name (default: default)")
    ap.add_argument(
        "--qgis-version", default="auto", choices=["auto", "3", "4"],
        help="QGIS major version for profile detection (default: auto)",
    )
    args = ap.parse_args()

    print(f"QGIS MCP deploy (plugin v{plugin_version()})")
    print("\n[1/2] Building plugin zip...")
    build_zip()

    if args.install:
        print("\n[2/2] Copy-deploying plugin...")
        if args.plugins_dir:
            plugins_dir = Path(args.plugins_dir)
        else:
            plugins_dir = qgis_plugins_dir(args.profile, args.qgis_version)
        copy_deploy(plugins_dir)
        print("\nRestart QGIS (or reload the plugin) to load the new code.")
    else:
        print("\n[2/2] Skipping deploy (pass --install to copy into a QGIS profile).")


if __name__ == "__main__":
    main()
