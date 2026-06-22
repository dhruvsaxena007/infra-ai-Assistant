# Image Model Upgrade Guide

## Current safe image mode (production default)

`/image-search` uses a **confidence-gated** pipeline:

1. **YOLO** (if `YOLO_MODEL_PATH` exists and `IMAGE_CLASSIFIER=auto|yolo`)
2. **MobileNet + visual** (if TensorFlow installed and `IMAGE_CLASSIFIER=auto|mobilenet`)
3. **CLIP + OpenCV** (always available fallback)
4. **Clarification** when confidence &lt; 0.35, category unknown, or ambiguous — **no machine search**

Response fields:

- `data.classifier` / `data.classifier_used`: `yolo | mobilenet | clip | opencv | clarification`
- `data.confidence`
- `data.detected_machine_type`
- `data.match_type`
- `data.fallback_reason` (when clarification)

Logs: `[image_classify] classifier_used=… confidence=… detected_category=… fallback_reason=…`

## YOLO dataset requirements

- One folder per canonical marketplace category (excavator, road roller, …)
- Clear side-view machine photos; avoid people/cars/screenshots
- Minimum ~50 images per class recommended for first training pass
- Label names must map to marketplace categories (see `app/ai/category_mapping.py`)

## Folder structure

```
infraforge-ai-backend/
  datasets/yolo/
    train/
      excavator/
      road_roller/
      ...
    val/
      excavator/
      ...
  models/infraforge_yolov8n_cls/
    best.pt          # set YOLO_MODEL_PATH to this file
```

## Export dataset from machine images

```bash
cd infraforge-ai-backend
python scripts/export_yolo_dataset.py
```

Uses MongoDB machine listing images grouped by category.

## Train (when ready — not required for dev)

```bash
python scripts/train_yolo_classifier.py
```

## Configure environment

```bash
# .env
IMAGE_CLASSIFIER=auto          # auto | yolo | mobilenet
YOLO_MODEL_PATH=models/infraforge_yolov8n_cls/best.pt
```

Or run:

```bash
python scripts/configure_yolo_env.py
```

## Test

```bash
python scripts/run_phase_c_tests.py   # image safe mode
python scripts/run_phase_d_tests.py   # YOLO missing fallback
python scripts/test_image_classifier.py path/to/image.jpg
```

## Rollback to safe mode

1. Remove or rename `YOLO_MODEL_PATH` file, **or**
2. Set `IMAGE_CLASSIFIER=mobilenet` or rely on CLIP/OpenCV only
3. Restart API — pipeline falls back automatically; low confidence still returns `image_clarification`

No code changes required for rollback.
