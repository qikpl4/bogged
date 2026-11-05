#!/usr/bin/env python3
"""Generate packed binary mapping files (one directory per version) from Minecraft mapping sources."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from binfmt.layout import SIDE_ORDER as SIDES  # noqa: E402
from pipeline import build_binary  # noqa: E402

logger = logging.getLogger(__name__)


def parse_versions(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    versions: list[str] = []
    seen: set[str] = set()
    for value in values:
        for version in value.split(","):
            version = version.strip()
            if not version:
                continue
            if version in (".", "..") or "/" in version or "\\" in version:
                raise ValueError(f"unsafe version name: {version!r}")
            if version not in seen:
                seen.add(version)
                versions.append(version)
    return versions


def parse_sides(values: list[str] | None) -> frozenset[str]:
    if values is None:
        return frozenset(SIDES)
    sides: set[str] = set()
    for value in values:
        for side in value.split(","):
            side = side.strip()
            if not side:
                continue
            if side not in SIDES:
                raise ValueError(f"unknown side {side!r}, expected one of: {', '.join(SIDES)}")
            sides.add(side)
    if not sides:
        raise ValueError("no sides selected")
    return frozenset(sides)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Directory to write; one subdirectory per version")
    parser.add_argument(
        "--sides",
        nargs="+",
        default=None,
        help=(
            f"Mapping sides to generate, any of: {', '.join(SIDES)}. Defaults to all of them. "
            "Comma-separated values are also accepted. Yarn requires --intermediary-repo to link names."
        ),
    )
    parser.add_argument("--intermediary-repo", type=Path, default=None, help="Path to a cloned FabricMC/intermediary repository (needed for the intermediary or yarn side)")
    parser.add_argument("--yarn-repo", type=Path, default=None, help="Path to a cloned FabricMC/yarn git repository with a branch or tag per version (needed for the yarn side)")
    parser.add_argument("--mojmap-dir", type=Path, default=None, help="Directory containing <version>.txt Mojang mappings (needed for the mojmap side)")
    parser.add_argument(
        "--versions",
        nargs="+",
        default=None,
        help="Only process these versions, e.g. --versions 1.21.11 1.20.6. Comma-separated values are also accepted.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=None,
        metavar="N",
        help="Number of versions to build in parallel. Defaults to the number of CPUs; pass 1 to build sequentially.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    args = parse_args()

    try:
        sides = parse_sides(args.sides)
        requested_versions = parse_versions(args.versions)
    except ValueError as error:
        logger.error("%s", error)
        return 2

    if args.jobs is not None and args.jobs < 1:
        logger.error("--jobs must be at least 1, got %d", args.jobs)
        return 2

    # Yarn links its names through intermediary, so it needs the intermediary repo too.
    needs_intermediary = bool(sides & {"intermediary", "yarn"})
    needs_yarn = "yarn" in sides
    needs_mojmap = "mojmap" in sides

    missing = []
    if needs_intermediary and args.intermediary_repo is None:
        missing.append("--intermediary-repo")
    if needs_yarn and args.yarn_repo is None:
        missing.append("--yarn-repo")
    if needs_mojmap and args.mojmap_dir is None:
        missing.append("--mojmap-dir")
    if missing:
        logger.error("sides %s require: %s", ", ".join(sorted(sides)), ", ".join(missing))
        return 2

    if needs_intermediary and not args.intermediary_repo.is_dir():
        raise FileNotFoundError(f"intermediary repository not found: {args.intermediary_repo}")
    if needs_yarn:
        if not args.yarn_repo.is_dir():
            raise FileNotFoundError(f"yarn repository not found: {args.yarn_repo}")
        git_check = subprocess.run(
            ["git", "-C", str(args.yarn_repo), "rev-parse", "--is-inside-work-tree"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if git_check.returncode != 0:
            raise ValueError(f"yarn repository is not a git repository: {args.yarn_repo}")
    if needs_mojmap and not args.mojmap_dir.is_dir():
        raise FileNotFoundError(f"mojmap directory not found: {args.mojmap_dir}")

    if requested_versions is None:
        if needs_mojmap:
            source_dir, pattern = args.mojmap_dir, "*.txt"
        else:
            source_dir, pattern = args.intermediary_repo / "mappings", "*.tiny"
        version_files = sorted(path for path in source_dir.glob(pattern) if path.is_file())
        if not version_files:
            logger.warning("no %s files found in %s", pattern, source_dir)
            return 0
        versions = [version_file.stem for version_file in version_files]
    else:
        versions = requested_versions

    build_binary(args.output, sides, args.intermediary_repo, args.yarn_repo, args.mojmap_dir, versions, jobs=args.jobs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
