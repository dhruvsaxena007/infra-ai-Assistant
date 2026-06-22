"""
Restore the InfraForge marketplace MongoDB dump into the configured database.

Expected dump layout (actual project structure):
    marketplace_mongo_dump/
        infraforge-dev/
            machines.bson.gz
            equipmentcategories.bson.gz
            cities.bson.gz
            ... (gzip mongodump collections)

Usage (from infraforge-ai-backend):
    python scripts/import_marketplace_dump.py
    python scripts/import_marketplace_dump.py --dump-dir "../marketplace_mongo_dump/infraforge-dev"
    python scripts/import_marketplace_dump.py --dry-run

Requires `mongorestore` on PATH and MONGODB_URL / DATABASE_NAME in .env.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_ROOT = os.path.dirname(PROJECT_ROOT)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.config import settings


DEFAULT_DUMP_DIR = os.path.join(WORKSPACE_ROOT, "marketplace_mongo_dump")


def _has_collection_files(directory: str) -> bool:
    for name in os.listdir(directory):
        if name.endswith(".bson") or name.endswith(".bson.gz"):
            return True
    return False


def resolve_dump_dir(path: str) -> str:
    """
    Resolve the directory that actually contains collection BSON files.

    Supports:
      - marketplace_mongo_dump/infraforge-dev/*.bson.gz  (this project)
      - marketplace_mongo_dump/*.bson                   (flat dump)
    """
    resolved = os.path.abspath(path)
    if not os.path.isdir(resolved):
        raise FileNotFoundError(
            f"Dump directory not found: {resolved}\n"
            "Expected marketplace_mongo_dump/ at the workspace root."
        )

    if _has_collection_files(resolved):
        return resolved

    # Nested mongodump folder (e.g. infraforge-dev/)
    candidates = []
    for entry in sorted(os.listdir(resolved)):
        sub = os.path.join(resolved, entry)
        if os.path.isdir(sub) and _has_collection_files(sub):
            candidates.append(sub)

    if len(candidates) == 1:
        return candidates[0]

    if len(candidates) > 1:
        names = ", ".join(os.path.basename(c) for c in candidates)
        raise FileNotFoundError(
            f"Multiple dump subfolders found under {resolved}: {names}. "
            "Pass --dump-dir explicitly."
        )

    raise FileNotFoundError(
        f"No .bson / .bson.gz collection files found under {resolved}."
    )


def list_bson_files(dump_dir: str) -> list[str]:
    files = []
    for name in os.listdir(dump_dir):
        if name.endswith(".bson") or name.endswith(".bson.gz"):
            files.append(name)
    return sorted(files)


def collection_names(bson_files: list[str]) -> list[str]:
    names = []
    for fname in bson_files:
        base = fname.replace(".bson.gz", "").replace(".bson", "")
        if base not in names:
            names.append(base)
    return names


def run_mongorestore(dump_dir: str, *, dry_run: bool) -> None:
    if not settings.MONGODB_URL:
        raise RuntimeError("MONGODB_URL is not set in .env")

    if not settings.DATABASE_NAME:
        raise RuntimeError("DATABASE_NAME is not set in .env")

    mongorestore = shutil.which("mongorestore")
    if not mongorestore:
        raise RuntimeError(
            "mongorestore not found on PATH. Install MongoDB Database Tools."
        )

    bson_files = list_bson_files(dump_dir)
    if not bson_files:
        raise FileNotFoundError(
            f"No collection files found in {dump_dir}. Is this a valid mongodump folder?"
        )

    uses_gzip = any(name.endswith(".bson.gz") for name in bson_files)

    print(f"Dump directory : {dump_dir}")
    print(f"Target database: {settings.DATABASE_NAME}")
    print(f"Collections    : {', '.join(collection_names(bson_files))}")
    print(f"Gzip           : {uses_gzip}")

    cmd = [
        mongorestore,
        f"--uri={settings.MONGODB_URL}",
        f"--db={settings.DATABASE_NAME}",
        "--drop",
    ]
    if uses_gzip:
        cmd.append("--gzip")
    cmd.append(dump_dir)

    print("\nCommand:", " ".join(cmd))

    if dry_run:
        print("\n[DRY RUN] Skipping mongorestore.")
        return

    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"mongorestore failed with exit code {result.returncode}")

    print("\nImport completed successfully.")
    print("Next step: python scripts/generate_marketplace_embeddings.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import marketplace MongoDB dump")
    parser.add_argument(
        "--dump-dir",
        default=DEFAULT_DUMP_DIR,
        help=f"Path to mongodump folder (default: {DEFAULT_DUMP_DIR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print mongorestore command without executing",
    )
    args = parser.parse_args()

    dump_dir = resolve_dump_dir(args.dump_dir)
    run_mongorestore(dump_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
