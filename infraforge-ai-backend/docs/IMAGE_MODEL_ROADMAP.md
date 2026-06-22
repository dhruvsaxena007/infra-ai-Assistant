# Image Model Roadmap — InfraForge AI Backend

## Current (NOW)

- **Model:** TensorFlow Keras `MobileNetV2` with ImageNet weights (top-5 labels)
- **Intent layer:** `app/ai/image_intent_service.py` — weighted category scoring + **OpenCV hints** (aspect ratio, yellow paint, roller circles)
- **Usage:** `POST /image-search`
- **Loading:** **Lazy** — TensorFlow loads on first image request
- **Confidence:** Uses **category intent score** (not raw ImageNet top-1 alone); avoids road roller → excavator mis-map
- **Mapping:** Longest-keyword-first rules; excavator blocked when label contains roller/drill/crane/etc.

### Why lazy-load?

- TensorFlow + MobileNet adds **seconds** to cold start and **hundreds of MB** RAM
- Most requests (`/health`, `/chat`, `/machines`) do not need image ML
- Lazy load keeps the API responsive for text/voice/RAG workloads

## Limitations of MobileNet (ImageNet)

- Trained on general objects, not construction equipment
- "Loader" / "truck" labels are ambiguous (JCB vs wheel loader vs dump truck)
- Low confidence on site photos, dust, partial frames

## Future options (NOT implemented — requires approval)

| Option | Pros | Cons |
|--------|------|------|
| **YOLOv8n** | Fast, good local inference, bounding boxes | Needs labelled InfraForge dataset |
| **YOLOv11n** | Newer, slightly better accuracy | Same dataset/training cost |
| **ONNX Runtime** | Lighter deploy, no full TF | Export + ops pipeline |
| **CLIP zero-shot** | Flexible text↔image categories | Heavier; needs prompt tuning |

## When to move to YOLO

Move when:

1. You have **500+ labelled images** per major category (excavator, JCB, crane, crawler drill, etc.)
2. MobileNet misclassification rate is unacceptable in production analytics
3. You can maintain a **versioned model artifact** (not hardcoded in repo)

## Dataset & training requirements

- Images from real InfraForge listings (`machines.images`, `image_url`)
- Labels = canonical category (+ optional brand)
- Train/val split by listing ID (avoid leakage)
- Metrics: per-category precision/recall, confusion matrix (JCB vs excavator critical)

## Migration path

1. Train YOLOv8n on exported dataset → export ONNX
2. Add `app/ai/yolo_classification_service.py` behind same interface as MobileNet
3. Feature flag: `IMAGE_CLASSIFIER=mobilenet|yolo` in `.env`
4. A/B test confidence + search click-through
5. Deprecate MobileNet only after approval

## Not planned without approval

- OpenAI Vision, Google Vision, AWS Rekognition, Azure Vision (paid APIs)
