"""Move a data folder's stored councils from GSS codes ONS has replaced to their current codes.

For data loaded before Barnsley and Sheffield were given their current codes (E08000038, E08000039; see
SUPERSEDED in scripts/build_councils.py). For each council it renames the cached Modern.gov responses, so nothing has
to be fetched again, and removes the tables stored under the old code. Then load, parse and index the two councils
again from the cache (the commands are printed at the end):

    uv run python scripts/recode_councils.py --dry-run
    uv run python scripts/recode_councils.py
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_councils import SUPERSEDED  # noqa: E402

from councils.config import load_settings  # noqa: E402


def recode(raw_dir: Path, parquet_dir: Path, old: str, new: str, dry_run: bool) -> list[str]:
    done = []
    src, dst = raw_dir / "modgov" / old, raw_dir / "modgov" / new
    if src.exists():
        if dst.exists():
            done.append(f"left {src}: {dst} already exists")
        else:
            done.append(f"renamed {src} to {dst}")
            if not dry_run:
                shutil.move(src, dst)
    for path in sorted(parquet_dir.glob(f"*/{old}.parquet")):
        done.append(f"removed {path}")
        if not dry_run:
            path.unlink()
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="say what would change, change nothing")
    args = ap.parse_args()
    s = load_settings()
    changed = []
    for old, new in SUPERSEDED.items():
        for line in recode(s.raw_dir, s.parquet_dir, old, new, args.dry_run):
            print(("would have " if args.dry_run else "") + line)
            changed.append(new)
    if changed and not args.dry_run:
        codes = " ".join(sorted(set(changed)))
        print(f"\nNow load them again from the cache:\n  uv run councils ingest {codes}\n"
              f"  uv run councils parse {codes}\n  uv run councils index")
    elif not changed:
        print("Nothing stored under the old codes: nothing to do.")


if __name__ == "__main__":
    main()
