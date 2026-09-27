# -*- coding: utf-8 -*-
"""
تشخیص اشیاء (فرد، خودرو، موتورسیکلت، اتوبوس، کامیون، دوچرخه، حیوان) با
استفاده از شبکه‌ی سبک YOLOv4-tiny از طریق ماژول DNN خودِ OpenCV — بدون
نیاز به کتابخانه‌ی سنگینی مثل PyTorch (که حجم و پیچیدگی بسته‌بندی exe را
چند برابر می‌کند).

مدل باید از قبل با download_yolo_model.py دانلود شده باشد.
"""

import os

import cv2
import numpy as np

import config


class ObjectDetector:
    def __init__(self):
        if not (os.path.exists(config.YOLO_CFG_PATH) and
                os.path.exists(config.YOLO_WEIGHTS_PATH) and
                os.path.exists(config.YOLO_NAMES_PATH)):
            raise FileNotFoundError(
                "فایل‌های مدل تشخیص اشیاء پیدا نشد. ابتدا download_yolo_model.py را اجرا کنید."
            )

        self.net = cv2.dnn.readNetFromDarknet(config.YOLO_CFG_PATH, config.YOLO_WEIGHTS_PATH)
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

        with open(config.YOLO_NAMES_PATH, "r", encoding="utf-8") as f:
            self.class_names = [line.strip() for line in f if line.strip()]

        layer_names = self.net.getLayerNames()
        out_indices = self.net.getUnconnectedOutLayers()
        # سازگاری با نسخه‌های مختلف OpenCV (خروجی گاهی دوبعدی است)
        if hasattr(out_indices, "flatten"):
            out_indices = out_indices.flatten()
        self.output_layers = [layer_names[i - 1] for i in out_indices]

    def detect(self, frame):
        """
        تشخیص اشیاء در یک فریم. خروجی: لیستی از دیکشنری‌ها با کلیدهای
        category (دسته‌ی فارسی، مثل «فرد»)، confidence، و box=(x, y, w, h).
        اشیائی که در OBJECT_CATEGORY_MAP تعریف نشده باشند (مثلاً صندلی،
        لپ‌تاپ و ...) نادیده گرفته می‌شوند چون برای این قابلیت مرتبط نیستند.
        """
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(
            frame, 1 / 255.0, (config.YOLO_INPUT_SIZE, config.YOLO_INPUT_SIZE),
            swapRB=True, crop=False,
        )
        self.net.setInput(blob)
        outputs = self.net.forward(self.output_layers)

        boxes, confidences, categories = [], [], []

        for output in outputs:
            for detection in output:
                scores = detection[5:]
                class_id = int(np.argmax(scores))
                confidence = float(scores[class_id])
                if confidence < config.OBJECT_MIN_CONFIDENCE:
                    continue

                class_name = self.class_names[class_id] if class_id < len(self.class_names) else None
                category = config.OBJECT_CATEGORY_MAP.get(class_name)
                if category is None:
                    continue  # شیء نامرتبط (مثلاً مبلمان)، رد می‌شود

                cx, cy, bw, bh = detection[0:4] * np.array([w, h, w, h])
                x = int(cx - bw / 2)
                y = int(cy - bh / 2)

                boxes.append([x, y, int(bw), int(bh)])
                confidences.append(confidence)
                categories.append(category)

        # حذف جعبه‌های تکراری/هم‌پوشان روی یک شیء با Non-Max-Suppression
        results = []
        if boxes:
            indices = cv2.dnn.NMSBoxes(
                boxes, confidences, config.OBJECT_MIN_CONFIDENCE, config.OBJECT_NMS_THRESHOLD
            )
            if hasattr(indices, "flatten"):
                indices = indices.flatten()
            for i in indices:
                results.append({
                    "category": categories[i],
                    "confidence": confidences[i],
                    "box": tuple(boxes[i]),
                })

        return results
