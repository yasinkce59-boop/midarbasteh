# -*- coding: utf-8 -*-
"""
تشخیص ناحیه‌ی احتمالی پلاک در یک فریم تصویری.

این ماژول از دو روش استفاده می‌کند:
  1) طبقه‌بند Haar Cascade آماده‌ی OpenCV برای پلاک (تشخیص سریع اولیه)
  2) روش کلاسیک مبتنی بر لبه‌یابی و کانتور به عنوان روش پشتیبان،
     برای زمانی که کسکید چیزی پیدا نکند یا دوربین/زاویه با آن سازگار نباشد.

نکته مهم: این روش‌های کلاسیک برای یک نمونه‌ی اولیه (MVP) کاربردی و سبک
هستند، اما دقت آن‌ها به پای یک مدل یادگیری عمیق آموزش‌دیده (مثلاً YOLOv8
fine-tune شده روی دیتاست پلاک ایران) نمی‌رسد. در بخش README توضیح داده‌ام
چطور می‌توان بعداً detect_plate_regions را با چنین مدلی جایگزین کرد بدون
آنکه بقیه‌ی برنامه تغییر کند.
"""

import cv2
import numpy as np
import config


class PlateDetector:
    def __init__(self):
        cascade_path = cv2.data.haarcascades + "haarcascade_russian_plate_number.xml"
        self.cascade = cv2.CascadeClassifier(cascade_path)
        if self.cascade.empty():
            self.cascade = None  # اگر فایل کسکید در دسترس نبود، فقط از روش پشتیبان استفاده می‌شود

    # ------------------------------------------------------------------
    def detect_plate_regions(self, frame: np.ndarray):
        """
        لیستی از مستطیل‌های (x, y, w, h) که به احتمال زیاد پلاک هستند را برمی‌گرداند.
        """
        boxes = []

        if self.cascade is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            detections = self.cascade.detectMultiScale(
                gray, scaleFactor=1.05, minNeighbors=4, minSize=(60, 20)
            )
            boxes.extend([tuple(map(int, d)) for d in detections])

        # روش پشتیبان مبتنی بر لبه/کانتور؛ همیشه اجرا می‌شود تا موارد از قلم‌افتاده
        # توسط کسکید را هم پوشش دهد (سپس تکراری‌ها فیلتر می‌شوند)
        boxes.extend(self._contour_based_candidates(frame))

        return self._filter_and_deduplicate(boxes, frame.shape)

    # ------------------------------------------------------------------
    def _contour_based_candidates(self, frame: np.ndarray):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 11, 17, 17)
        edged = cv2.Canny(gray, 30, 200)
        edged = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, np.ones((3, 9), np.uint8))

        contours, _ = cv2.findContours(edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        candidates = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if h == 0:
                continue
            aspect_ratio = w / float(h)
            area = w * h
            if (
                config.PLATE_ASPECT_RATIO_MIN <= aspect_ratio <= config.PLATE_ASPECT_RATIO_MAX
                and area >= config.MIN_PLATE_AREA
            ):
                candidates.append((x, y, w, h))
        return candidates

    # ------------------------------------------------------------------
    def _filter_and_deduplicate(self, boxes, frame_shape):
        h_frame, w_frame = frame_shape[:2]
        max_area = config.MAX_PLATE_AREA_RATIO * h_frame * w_frame

        filtered = []
        for (x, y, w, h) in boxes:
            if w * h > max_area:
                continue
            filtered.append((x, y, w, h))

        # حذف جعبه‌های همپوشان با استفاده از non-max-suppression ساده
        if not filtered:
            return []

        rects = np.array([[x, y, x + w, y + h] for (x, y, w, h) in filtered])
        keep_idx = self._simple_nms(rects, overlap_thresh=0.3)
        return [filtered[i] for i in keep_idx]

    @staticmethod
    def _simple_nms(rects, overlap_thresh=0.3):
        if len(rects) == 0:
            return []
        x1, y1, x2, y2 = rects[:, 0], rects[:, 1], rects[:, 2], rects[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        order = areas.argsort()[::-1]

        keep = []
        while len(order) > 0:
            i = order[0]
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            w = np.maximum(0, xx2 - xx1)
            h = np.maximum(0, yy2 - yy1)
            inter = w * h
            iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
            order = order[1:][iou <= overlap_thresh]

        return keep
