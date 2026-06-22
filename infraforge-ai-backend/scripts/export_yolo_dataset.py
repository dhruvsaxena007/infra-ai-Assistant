"""
Export ALL InfraForge machine images from MongoDB for YOLO classification training.

Uses every document in `machines` (no active/public filter) so the full dump is included.
Downloads productImages / productThumbnails / image_url into class folders.

Usage:
    python scripts/export_yolo_dataset.py
    python scripts/export_yolo_dataset.py --max-per-machine 5
    python scripts/export_yolo_dataset.py --dry-run

Output:
    datasets/infraforge_yolo/
        manifest.json
        images/<machine_id>/<file>.jpg
        cls_dataset/train/<category_slug>/
        cls_dataset/val/<category_slug>/
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict

import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.ai.category_mapping import (
    detect_requested_category,
    marketplace_category_to_canonical,
)
from app.core.config import settings
from app.database.mongodb import database
from app.utils.machine_normalizer import normalize_machine
from app.utils.reference_cache import get_reference_cache, reset_reference_cache
from scripts.yolo_image_validate import is_valid_image_file, purge_invalid_in_dataset

DATASET_ROOT = os.path.join(PROJECT_ROOT, "datasets", "infraforge_yolo")
IMAGES_ROOT = os.path.join(DATASET_ROOT, "images")
CLS_ROOT = os.path.join(DATASET_ROOT, "cls_dataset")


MIN_IMAGES_PER_CLASS = 2
TARGET_IMAGES_PER_CLASS = 8
SKIP_CLASS_SLUGS = frozenset({"unknown", "other", "misc", ""})
REAL_SOURCES = frozenset({"infraforge_real_db", "seed_sample", None, ""})


def _resolve_canonical_category(normalized: dict, raw: dict) -> str:
    """Best-effort label from display name, normalized category, and listing text."""
    display = normalized.get("category_display") or ""
    category = normalized.get("category") or ""
    hint_text = " ".join(
        filter(
            None,
            [
                display,
                category,
                normalized.get("name"),
                normalized.get("brand"),
                normalized.get("model"),
                str(raw.get("slug") or ""),
            ],
        )
    )
    canonical = (
        marketplace_category_to_canonical(display)
        or marketplace_category_to_canonical(category)
        or detect_requested_category(hint_text)
        or (category or "").lower().strip()
    )
    return canonical or ""


def _slug_category(canonical: str) -> str:
    base = marketplace_category_to_canonical(canonical) or canonical
    return re.sub(r"[^a-z0-9]+", "_", base.lower()).strip("_")


def _collect_urls(raw: dict, normalized: dict) -> list[str]:
    urls = []
    for key in ("productImages", "productThumbnails"):
        val = raw.get(key)
        if isinstance(val, list):
            urls.extend(str(u).strip() for u in val if u)
    for u in normalized.get("images") or []:
        if u:
            urls.append(str(u).strip())
    if normalized.get("image_url"):
        urls.append(str(normalized["image_url"]).strip())
    seen = set()
    out = []
    for u in urls:
        if u.startswith("http") and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _download(url: str, dest: str, timeout: int = 30) -> bool:
    if os.path.isfile(dest):
        ok, reason = is_valid_image_file(dest)
        if ok:
            return True
        try:
            os.remove(dest)
        except OSError:
            pass
        print(f"  removed corrupt cached file: {dest} ({reason})")

    try:
        resp = requests.get(
            url,
            timeout=timeout,
            stream=True,
            headers={"User-Agent": "InfraForge-YOLO-Export/1.0"},
        )
        resp.raise_for_status()
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    fh.write(chunk)

        ok, reason = is_valid_image_file(dest)
        if not ok:
            try:
                os.remove(dest)
            except OSError:
                pass
            print(f"  rejected invalid download ({reason}): {url[:80]}...")
            return False
        return True
    except Exception as exc:
        print(f"  download failed: {url[:80]}... -> {exc}")
        return False


async def export(*, max_per_machine: int, dry_run: bool, val_ratio: float) -> None:
    if not settings.MONGODB_URL:
        raise RuntimeError("MONGODB_URL is not set")

    reset_reference_cache()
    cache = await get_reference_cache(database)

    total = await database.machines.count_documents({})
    print(f"Exporting from {settings.DATABASE_NAME}.machines — {total} documents (ALL, no filter)")

    manifest_entries = []
    by_class: dict[str, list[str]] = defaultdict(list)
    skipped_no_category = 0
    skipped_no_images = 0

    all_raw = [raw async for raw in database.machines.find({})]

    def _is_real(doc: dict) -> bool:
        return doc.get("source") not in ("training_seed",)

    # Real InfraForge listings first, then training_seed fills gaps per class.
    ordered = sorted(all_raw, key=lambda d: (1 if d.get("source") == "training_seed" else 0))

    async def _process_one(raw: dict, *, allow_seed: bool) -> None:
        nonlocal skipped_no_category, skipped_no_images
        if raw.get("source") == "training_seed" and not allow_seed:
            return

        normalized = normalize_machine(raw, cache)
        machine_id = str(normalized.get("id") or raw.get("_id"))
        category_display = normalized.get("category_display") or normalized.get("category")
        canonical = _resolve_canonical_category(normalized, raw)
        class_slug = _slug_category(canonical)

        urls = _collect_urls(raw, normalized)[:max_per_machine]
        if not urls:
            skipped_no_images += 1
            return
        if not canonical or class_slug in SKIP_CLASS_SLUGS:
            skipped_no_category += 1
            return

        entry = {
            "machine_id": machine_id,
            "name": normalized.get("name"),
            "category": canonical,
            "category_display": category_display,
            "class_slug": class_slug,
            "source": raw.get("source"),
            "status": raw.get("status"),
            "visibility": raw.get("visibility"),
            "image_urls": urls,
            "local_files": [],
        }

        if dry_run:
            manifest_entries.append(entry)
            return

        machine_dir = os.path.join(IMAGES_ROOT, machine_id)
        for idx, url in enumerate(urls):
            ext = ".jpg"
            if ".png" in url.lower():
                ext = ".png"
            elif ".webp" in url.lower():
                ext = ".webp"
            fname = f"{idx:02d}{ext}"
            dest = os.path.join(machine_dir, fname)
            if _download(url, dest):
                entry["local_files"].append(dest)
                by_class[class_slug].append(dest)

        if entry["local_files"]:
            manifest_entries.append(entry)

    # Pass 1 — real listing photos
    for raw in ordered:
        if _is_real(raw):
            await _process_one(raw, allow_seed=True)

    # Pass 2 — seed/stock only where class still needs images
    for raw in ordered:
        if not _is_real(raw):
            normalized = normalize_machine(raw, cache)
            canonical = _resolve_canonical_category(normalized, raw)
            slug = _slug_category(canonical)
            if slug and len(by_class.get(slug, [])) < TARGET_IMAGES_PER_CLASS:
                await _process_one(raw, allow_seed=True)

    os.makedirs(DATASET_ROOT, exist_ok=True)
    manifest_path = os.path.join(DATASET_ROOT, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "total_documents": total,
                "exported_machines": len(manifest_entries),
                "skipped_no_images": skipped_no_images,
                "skipped_no_category": skipped_no_category,
                "class_counts": {k: len(v) for k, v in sorted(by_class.items())},
                "machines": manifest_entries,
            },
            fh,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    if dry_run:
        print(f"Dry run — would export {len(manifest_entries)} machines")
        print(f"Skipped (no images): {skipped_no_images}")
        return

    import shutil

    # Fresh cls_dataset (avoid mixed old + new exports)
    if os.path.isdir(CLS_ROOT):
        shutil.rmtree(CLS_ROOT)
    os.makedirs(CLS_ROOT, exist_ok=True)

    skipped_too_few = 0
    rng = random.Random(42)
    exportable: dict[str, list[str]] = {}

    skipped_invalid = 0
    for slug, paths in by_class.items():
        if slug in SKIP_CLASS_SLUGS:
            skipped_no_category += len(paths)
            continue
        valid_paths = [p for p in paths if is_valid_image_file(p)[0]]
        skipped_invalid += len(paths) - len(valid_paths)
        if len(valid_paths) < MIN_IMAGES_PER_CLASS:
            skipped_too_few += len(valid_paths)
            print(
                f"  skip class '{slug}' — only {len(valid_paths)} valid images "
                f"(need {MIN_IMAGES_PER_CLASS})"
            )
            continue
        exportable[slug] = valid_paths

    for slug, paths in exportable.items():
        rng.shuffle(paths)
        if len(paths) == 2:
            train_paths, val_paths = [paths[0]], [paths[1]]
        else:
            cut = max(1, int(len(paths) * (1 - val_ratio)))
            train_paths = paths[:cut]
            val_paths = paths[cut:]
            if not val_paths:
                val_paths = [paths[-1]]

        for split_name, split_paths in (("train", train_paths), ("val", val_paths)):
            dest_dir = os.path.join(CLS_ROOT, split_name, slug)
            os.makedirs(dest_dir, exist_ok=True)
            for src in split_paths:
                base = os.path.basename(src)
                dest = os.path.join(
                    dest_dir,
                    f"{os.path.splitext(base)[0]}_{slug}{os.path.splitext(base)[1]}",
                )
                if is_valid_image_file(src)[0]:
                    shutil.copy2(src, dest)
                else:
                    skipped_invalid += 1

    purge_report = purge_invalid_in_dataset(CLS_ROOT)
    if purge_report["bad_count"]:
        print(f"Purged {purge_report['bad_count']} invalid files from cls_dataset")

    counts = Counter({slug: len(paths) for slug, paths in exportable.items()})
    print(f"Manifest: {manifest_path}")
    print(f"Class folders under {CLS_ROOT}")
    print("Images per class:", dict(counts.most_common()))
    print(f"Skipped no images: {skipped_no_images}")
    print(f"Skipped bad/unknown category: {skipped_no_category}")
    print(f"Skipped too few images per class: {skipped_too_few}")
    print(f"Skipped invalid/corrupt images: {skipped_invalid}")
    print(f"\nTrain with: python scripts/train_yolo_classifier.py")
    print(f"Dataset root for YOLO: {CLS_ROOT}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-per-machine", type=int, default=8)
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        export(
            max_per_machine=args.max_per_machine,
            dry_run=args.dry_run,
            val_ratio=args.val_ratio,
        )
    )


if __name__ == "__main__":
    main()
