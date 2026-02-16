#!/usr/bin/env python3
"""Build the static site from serialized analysis results."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from the scripts/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from government.output.site_builder import SiteBuilder, load_results_from_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Build AI Government static site")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "output" / "data",
        help="Directory containing result JSON files (default: output/data/)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "_site",
        help="Directory to write the built site (default: _site/)",
    )
    args = parser.parse_args()

    data_dir: Path = args.data_dir
    output_dir: Path = args.output_dir

    results = []
    if data_dir.exists():
        results = load_results_from_dir(data_dir)
        print(f"Loaded {len(results)} result(s) from {data_dir}")
    else:
        print(f"No data directory at {data_dir}, building empty site")

    builder = SiteBuilder(output_dir)
    builder.build(results, data_dir=data_dir if data_dir.exists() else None)
    print(f"Site built at {output_dir}")


if __name__ == "__main__":
    main()
