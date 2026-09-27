# -*- coding: utf-8 -*-
"""
ردیابی ساده‌ی چند-شیء بر اساس نزدیک‌ترین مرکز جسم بین فریم‌های پیاپی
(Centroid Tracking)، به‌علاوه‌ی توابع تشخیص «عبور از خط» و «ورود به محدوده».

چرا ردیابی لازم است؟ برای تشخیص «عبور»، صرفاً دیدن یک شیء در یک فریم کافی
نیست؛ باید بدانیم آن شیء از کدام سمت خط به کدام سمت دیگر حرکت کرده. برای
این کار موقعیت هر شیء را بین فریم متوالی مقایسه می‌کنیم.
"""

import math

import cv2
import numpy as np

import config


def _box_center(box):
    x, y, w, h = box
    return (x + w / 2.0, y + h / 2.0)


class CentroidTracker:
    def __init__(self):
        self.next_id = 0
        # track_id -> {"centroid": (x,y), "category": str, "confidence": float,
        #              "box": (x,y,w,h), "disappeared": int}
        self.tracks = {}

    def update(self, detections):
        """
        detections: خروجی ObjectDetector.detect() برای فریم فعلی.
        خروجی: لیستی از (track_id, prev_centroid_or_None, curr_centroid, category, confidence, box)
        برای هر شیءِ ردیابی‌شده در این فریم؛ prev_centroid فقط وقتی مقدار
        دارد که این شیء در فریم قبلی هم دیده شده باشد (لازم برای تشخیص عبور).
        """
        input_centroids = [_box_center(d["box"]) for d in detections]

        # هیچ تشخیصی در این فریم نبود: همه‌ی ردیابی‌های موجود را «گم‌شده» علامت بزن
        if not input_centroids:
            for tid in list(self.tracks.keys()):
                self.tracks[tid]["disappeared"] += 1
                if self.tracks[tid]["disappeared"] > config.TRACKER_MAX_DISAPPEARED:
                    del self.tracks[tid]
            return []

        # هیچ ردیابی فعالی وجود ندارد: همه را به‌عنوان ردیابی جدید ثبت کن
        if not self.tracks:
            results = []
            for det, centroid in zip(detections, input_centroids):
                tid = self._register(det, centroid)
                results.append((tid, None, centroid, det["category"], det["confidence"], det["box"]))
            return results

        track_ids = list(self.tracks.keys())
        track_centroids = [self.tracks[tid]["centroid"] for tid in track_ids]

        # ماتریس فاصله‌ی بین هر ردیابی موجود و هر تشخیص جدید
        dist_matrix = np.zeros((len(track_centroids), len(input_centroids)))
        for i, tc in enumerate(track_centroids):
            for j, ic in enumerate(input_centroids):
                dist_matrix[i, j] = math.hypot(tc[0] - ic[0], tc[1] - ic[1])

        # جفت‌کردن حریصانه: نزدیک‌ترین جفت‌ها را اول انتخاب کن
        used_rows, used_cols = set(), set()
        results = []
        pairs = []
        for i in range(dist_matrix.shape[0]):
            for j in range(dist_matrix.shape[1]):
                pairs.append((dist_matrix[i, j], i, j))
        pairs.sort(key=lambda p: p[0])

        for dist, i, j in pairs:
            if i in used_rows or j in used_cols:
                continue
            if dist > config.TRACKER_MAX_DISTANCE:
                continue
            used_rows.add(i)
            used_cols.add(j)

            tid = track_ids[i]
            prev_centroid = self.tracks[tid]["centroid"]
            curr_centroid = input_centroids[j]
            det = detections[j]

            self.tracks[tid].update({
                "centroid": curr_centroid,
                "category": det["category"],
                "confidence": det["confidence"],
                "box": det["box"],
                "disappeared": 0,
            })
            results.append((tid, prev_centroid, curr_centroid, det["category"], det["confidence"], det["box"]))

        # تشخیص‌های جدیدی که به هیچ ردیابی قبلی جفت نشدند: ردیابی تازه بساز
        for j in range(len(input_centroids)):
            if j in used_cols:
                continue
            det = detections[j]
            centroid = input_centroids[j]
            tid = self._register(det, centroid)
            results.append((tid, None, centroid, det["category"], det["confidence"], det["box"]))

        # ردیابی‌های قدیمی که در این فریم جفت نشدند: گم‌شده علامت بزن
        for i in range(len(track_ids)):
            if i in used_rows:
                continue
            tid = track_ids[i]
            self.tracks[tid]["disappeared"] += 1
            if self.tracks[tid]["disappeared"] > config.TRACKER_MAX_DISAPPEARED:
                del self.tracks[tid]

        return results

    def _register(self, det, centroid):
        tid = self.next_id
        self.next_id += 1
        self.tracks[tid] = {
            "centroid": centroid,
            "category": det["category"],
            "confidence": det["confidence"],
            "box": det["box"],
            "disappeared": 0,
        }
        return tid


def segments_intersect(p1, p2, p3, p4):
    """آیا پاره‌خط p1-p2 با پاره‌خط p3-p4 برخورد دارد؟ (برای تشخیص عبور از خط)"""
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1 = cross(p3, p4, p1)
    d2 = cross(p3, p4, p2)
    d3 = cross(p1, p2, p3)
    d4 = cross(p1, p2, p4)

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    return False


def crossed_polyline(prev_point, curr_point, polyline_points):
    """آیا حرکت از prev_point به curr_point از یکی از پاره‌خط‌های خط
    چندنقطه‌ای (polyline) تعریف‌شده توسط کاربر عبور کرده؟"""
    for i in range(len(polyline_points) - 1):
        if segments_intersect(prev_point, curr_point, polyline_points[i], polyline_points[i + 1]):
            return True
    return False


def entered_polygon(prev_point, curr_point, polygon_points):
    """آیا شیء از بیرون محدوده به داخل آن وارد شده؟ (برای محدوده‌ی بسته)"""
    poly = np.array(polygon_points, dtype=np.float32)
    was_inside = cv2.pointPolygonTest(poly, prev_point, False) >= 0
    is_inside = cv2.pointPolygonTest(poly, curr_point, False) >= 0
    return (not was_inside) and is_inside
