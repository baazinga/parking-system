from pathlib import Path
from uuid import uuid4

import cv2
from ultralytics import YOLO


BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "model" / "best.pt"
CROP_DIR = BASE_DIR / "plate_crops"

CROP_DIR.mkdir(exist_ok=True)

_model = None


def get_detector():
    global _model
    if _model is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"未找到车牌检测模型: {MODEL_PATH}")
        _model = YOLO(str(MODEL_PATH))
    return _model


def detect_and_crop_plate(image_path: str) -> str:
    model = get_detector()
    results = model.predict(source=image_path, conf=0.25, verbose=False)

    if not results:
        raise ValueError("YOLO 未返回检测结果")

    result = results[0]
    boxes = result.boxes

    if boxes is None or len(boxes) == 0:
        raise ValueError("未检测到车牌区域，请重新拍摄")

    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("原始图片读取失败")

    height, width = image.shape[:2]

    best_box = max(boxes, key=lambda box: float(box.conf[0]))
    x1, y1, x2, y2 = best_box.xyxy[0].tolist()

    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

    # 给车牌框留一点边距，避免裁得太死
    pad_x = int((x2 - x1) * 0.15)
    pad_y = int((y2 - y1) * 0.25)

    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(width, x2 + pad_x)
    y2 = min(height, y2 + pad_y)

    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        raise ValueError("车牌裁剪失败")

    crop_name = f"plate_{uuid4().hex}.jpg"
    crop_path = CROP_DIR / crop_name
    cv2.imwrite(str(crop_path), crop)

    return str(crop_path)
