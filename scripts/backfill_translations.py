#!/usr/bin/env python3
"""Backfill Montenegrin translations for existing result JSON files.

Loads each SessionResult from output/data/, runs localize_result() to
populate all _mne fields via LLM translation, and writes back.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import anyio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from government.output.localization import has_montenegrin_content, localize_result
from government.output.site_builder import load_results_from_dir, save_result_json


async def backfill(data_dir: Path, *, force: bool = False) -> None:
    results = load_results_from_dir(data_dir)
    print(f"Loaded {len(results)} result(s) from {data_dir}")

    for result in results:
        label = result.decision.title[:60]
        if has_montenegrin_content(result) and not force:
            print(f"  SKIP (already has MNE): {label}")
            continue

        print(f"  Translating: {label} ...")
        await localize_result(result)
        save_result_json(result, data_dir)
        print(f"  DONE: {label}")

    print("Backfill complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill MNE translations")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "output" / "data",
        help="Directory containing result JSON files (default: output/data/)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-translate even if MNE content already exists",
    )
    args = parser.parse_args()
    anyio.run(lambda: backfill(args.data_dir, force=args.force))


if __name__ == "__main__":
    main()
