"""
Train YOLOv8n classification model on InfraForge exported dataset.

Dataset layout (Ultralytics classify):
    datasets/infraforge_yolo/cls_dataset/
        train/<class_name>/*.jpg
        val/<class_name>/*.jpg

Usage:
    python scripts/export_yolo_dataset.py
    python scripts/train_yolo_classifier.py --epochs 50

Exports best weights to:
    models/infraforge_yolov8n_cls/best.pt
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DATASET_ROOT = os.path.join(PROJECT_ROOT, "datasets", "infraforge_yolo", "cls_dataset")
TRAIN_DIR = os.path.join(DATASET_ROOT, "train")
VAL_DIR = os.path.join(DATASET_ROOT, "val")
MODEL_OUT_DIR = os.path.join(PROJECT_ROOT, "models", "infraforge_yolov8n_cls")
DEFAULT_WEIGHTS = os.path.join(MODEL_OUT_DIR, "best.pt")

from scripts.yolo_image_validate import is_valid_image_file, purge_invalid_in_dataset


def _count_images(root: str) -> dict[str, int]:
    counts = {}
    if not os.path.isdir(root):
        return counts
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if os.path.isdir(path):
            counts[name] = len(
                [
                    f
                    for f in os.listdir(path)
                    if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
                ]
            )
    return counts


def _validate_dataset(*, purge: bool = True) -> dict:
    if not os.path.isdir(TRAIN_DIR):
        raise FileNotFoundError(
            f"Missing {TRAIN_DIR}\nRun: python scripts/export_yolo_dataset.py"
        )

    purge_report = purge_invalid_in_dataset(DATASET_ROOT) if purge else {"bad_count": 0}
    if purge_report.get("bad_count"):
        print(
            f"Removed {purge_report['bad_count']} corrupt images before training:",
            purge_report.get("bad_by_class"),
        )

    train_counts = _count_images(TRAIN_DIR)
    val_counts = _count_images(VAL_DIR)

    if not train_counts:
        raise RuntimeError("No class folders under cls_dataset/train after validation")

    # Re-verify every file Ultralytics will read
    bad_files = []
    for split_name, split_dir in (("train", TRAIN_DIR), ("val", VAL_DIR)):
        if not os.path.isdir(split_dir):
            continue
        for class_name in os.listdir(split_dir):
            class_path = os.path.join(split_dir, class_name)
            if not os.path.isdir(class_path):
                continue
            for fname in os.listdir(class_path):
                if not fname.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    continue
                fpath = os.path.join(class_path, fname)
                ok, reason = is_valid_image_file(fpath)
                if not ok:
                    bad_files.append((fpath, reason))
                    try:
                        os.remove(fpath)
                    except OSError:
                        pass

    if bad_files:
        print(f"Final sweep removed {len(bad_files)} unreadable files")
        train_counts = _count_images(TRAIN_DIR)
        val_counts = _count_images(VAL_DIR)

    print("Train images per class:", train_counts)
    print("Val images per class:", val_counts)

    too_few = [c for c, n in train_counts.items() if n < 2]
    if too_few:
        raise RuntimeError(
            f"Classes with fewer than 2 train images after cleanup: {too_few}. "
            "Re-run export_yolo_dataset.py"
        )

    missing_val = [c for c in train_counts if val_counts.get(c, 0) == 0]
    if missing_val:
        print(
            "WARNING: These classes have no val images (re-run export_yolo_dataset.py):",
            missing_val,
        )

    total_train = sum(train_counts.values())
    if total_train < 30:
        print(
            "WARNING: Very few training images. Accuracy will be low until you import "
            "the full marketplace dump:\n"
            "  python scripts/import_marketplace_dump.py"
        )

    return {
        "train_counts": train_counts,
        "val_counts": val_counts,
        "purged": purge_report.get("bad_count", 0) + len(bad_files),
        "classes": len(train_counts),
    }


def _remove_stale_splits() -> None:
    """Ultralytics may create train_split if data path was wrong — remove it."""
    stale = os.path.join(DATASET_ROOT, "train_split")
    if os.path.isdir(stale):
        shutil.rmtree(stale, ignore_errors=True)
        print(f"Removed stale folder: {stale}")


def train(*, epochs: int, model_name: str, imgsz: int, purge: bool = True) -> None:
    _remove_stale_splits()
    meta = _validate_dataset(purge=purge)
    print(
        f"Dataset OK: {meta['classes']} classes, "
        f"{sum(meta['train_counts'].values())} train images, "
        f"purged={meta['purged']}"
    )

    from ultralytics import YOLO

    model = YOLO(model_name)
    results = model.train(
        data=DATASET_ROOT,
        epochs=epochs,
        imgsz=imgsz,
        project=os.path.join(PROJECT_ROOT, "runs", "classify"),
        name="infraforge_machines",
        exist_ok=True,
        verbose=True,
    )

    best_src = None
    save_dir = getattr(results, "save_dir", None)
    if save_dir:
        candidate = os.path.join(save_dir, "weights", "best.pt")
        if os.path.isfile(candidate):
            best_src = candidate

    if not best_src:
        candidate = os.path.join(
            PROJECT_ROOT,
            "runs",
            "classify",
            "infraforge_machines",
            "weights",
            "best.pt",
        )
        if os.path.isfile(candidate):
            best_src = candidate

    if not best_src:
        raise FileNotFoundError("Training finished but best.pt not found under runs/classify/")

    os.makedirs(MODEL_OUT_DIR, exist_ok=True)
    shutil.copy2(best_src, DEFAULT_WEIGHTS)
    print(f"\nSaved model: {DEFAULT_WEIGHTS}")

    results_csv = os.path.join(
        PROJECT_ROOT, "runs", "classify", "infraforge_machines", "results.csv"
    )
    if os.path.isfile(results_csv):
        with open(results_csv, encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh if ln.strip()]
        if len(lines) > 1:
            last = lines[-1].split(",")
            print(f"Final epoch metrics (last row): top1={last[3] if len(last) > 3 else '?'} val_loss={last[5] if len(last) > 5 else '?'}")

    print("\n--- Enable YOLO in the API (.env file, NOT PowerShell commands) ---")
    print("YOLO_MODEL_PATH=models/infraforge_yolov8n_cls/best.pt")
    print("IMAGE_CLASSIFIER=auto")
    print("\nOr run: python scripts/configure_yolo_env.py")
    print("Then restart: python -m uvicorn app.main:app --reload")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--model", type=str, default="yolov8n-cls.pt")
    parser.add_argument("--imgsz", type=int, default=224)
    parser.add_argument("--skip-purge", action="store_true")
    args = parser.parse_args()
    train(
        epochs=args.epochs,
        model_name=args.model,
        imgsz=args.imgsz,
        purge=not args.skip_purge,
    )


if __name__ == "__main__":
    main()
