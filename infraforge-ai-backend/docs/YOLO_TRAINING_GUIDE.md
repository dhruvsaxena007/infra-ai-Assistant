# YOLO Image Training — InfraForge (free, local)

## Why train?

MobileNet only knows ImageNet (not JCB, crawler drill, site photos).  
YOLO **classification** learns from **your** `machines.productImages` — any color, angle, background (as long as labels are correct).

## Use ALL dump data

These scripts use **`machines.find({})` with no limit** — every document in MongoDB after you import the full dump:

```powershell
python scripts/import_marketplace_dump.py
python scripts/list_all_machines.py
python scripts/export_yolo_dataset.py
python scripts/train_yolo_classifier.py --epochs 50
python scripts/configure_yolo_env.py
python -m uvicorn app.main:app --reload
```

**Train script uses** `datasets/infraforge_yolo/cls_dataset` (contains `train/` + `val/`).  
Do **not** point YOLO at `cls_dataset/train` only — that causes the `train/train` warning.

If `list_all_machines.py` shows only ~19 machines, the dump is incomplete — re-import `marketplace_mongo_dump/`.

## API — put these in `.env` (not PowerShell commands)

**Wrong (PowerShell error):**
```powershell
YOLO_MODEL_PATH=models/infraforge_yolov8n_cls/best.pt   # does NOT work
```

**Correct option A — edit `.env` file:**
```env
YOLO_MODEL_PATH=models/infraforge_yolov8n_cls/best.pt
IMAGE_CLASSIFIER=auto
```

**Correct option B — script:**
```powershell
python scripts/configure_yolo_env.py
```

**Correct option C — one session only:**
```powershell
$env:YOLO_MODEL_PATH = "models/infraforge_yolov8n_cls/best.pt"
$env:IMAGE_CLASSIFIER = "auto"
python -m uvicorn app.main:app --reload
```

- `auto` — YOLO if weights exist, else MobileNet  
- `yolo` — YOLO only  
- `mobilenet` — legacy path  

Restart backend after changing `.env`.

## List all machines

```http
GET /machines?scope=all     # full collection (default)
GET /machines?scope=active  # active + public only (search-style)
```

Or run `python scripts/list_all_machines.py` for offline JSON.

## Improve accuracy

1. More images per category (full dump + more listings)  
2. Fix wrong `equipmentCategory` in DB  
3. Increase `--epochs` (e.g. 80)  
4. Later: YOLO **detect** with bounding boxes for multi-machine photos  
