# -*- coding: utf-8 -*-
"""
یک ریسه‌ی (Thread) مستقل به ازای هر دوربینِ «در حال پایش»، که خط پردازش کامل
(دریافت فریم -> تشخیص حرکت خودرو -> تشخیص ناحیه‌ی پلاک -> OCR -> ثبت، و
به‌صورت مستقل: تشخیص اشیاء -> ردیابی -> تشخیص عبور از خط/محدوده -> ثبت) را
بدون قفل کردن رابط گرافیکی اجرا می‌کند. نتایج (فریم پیش‌نمایش و رکوردهای
ثبت‌شده) از طریق callback به رشته‌ی اصلی GUI فرستاده می‌شود.
"""

import os
import threading
import time

import cv2

import config
import zone_manager
from camera_manager import normalize_source
from centroid_tracker import CentroidTracker, crossed_polyline, entered_polygon
from detector import PlateDetector
from motion_trigger import VehicleMotionTrigger
from object_detector import ObjectDetector
from ocr_reader import PlateOCR
from storage import PlateLogger
from utils import preprocess_plate_crop, draw_label


class CameraWorker(threading.Thread):
    def __init__(self, camera_id, camera_name, source,
                 shared_detector: PlateDetector, shared_ocr: PlateOCR, shared_logger: PlateLogger,
                 shared_object_detector: ObjectDetector = None,
                 on_preview=None, on_log=None, on_status=None, on_crossing=None):
        super().__init__(daemon=True)
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.source = source

        # مدل‌های تشخیص/OCR سنگین هستند و بین تمام دوربین‌ها به اشتراک گذاشته
        # می‌شوند تا حافظه و زمان بارگذاری تکرار نشود.
        self.detector = shared_detector
        self.ocr = shared_ocr
        self.logger = shared_logger
        self.object_detector = shared_object_detector

        self.motion_trigger = VehicleMotionTrigger() if config.ENABLE_MOTION_TRIGGER else None

        # نواحی/خطوط هشدار تعریف‌شده برای این دوربین + ردیاب اشیاء مخصوص خودش
        # (هر دوربین باید ردیاب جدا داشته باشد چون track_id ها بین دوربین‌ها ربطی ندارند)
        self.zones = zone_manager.get_zones_for_camera(camera_id)
        self.tracker = CentroidTracker() if self.zones else None

        self.on_preview = on_preview    # callback(camera_id, frame_bgr)
        self.on_log = on_log            # callback(camera_id, record_dict) - رویداد پلاک
        self.on_status = on_status      # callback(camera_id, status_text)
        self.on_crossing = on_crossing  # callback(camera_id, record_dict) - رویداد عبور

        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        src = normalize_source(self.source)
        cap = cv2.VideoCapture(src)

        if not cap.isOpened():
            self._notify_status("خطا در اتصال")
            return

        self._notify_status("در حال پایش")
        last_preview_time = 0
        last_process_time = 0
        last_zone_time = 0

        while not self._stop_event.is_set():
            ok, frame = cap.read()
            if not ok:
                self._notify_status("قطع شد - تلاش مجدد...")
                cap.release()
                time.sleep(2)
                if self._stop_event.is_set():
                    break
                cap = cv2.VideoCapture(src)
                continue

            should_process = True
            if self.motion_trigger is not None:
                should_process = self.motion_trigger.update(frame)
            else:
                now = time.time()
                should_process = (now - last_process_time) >= config.FRAME_PROCESS_INTERVAL
                if should_process:
                    last_process_time = now

            if should_process:
                frame = self._process_frame(frame)

            # تشخیص عبور از خط/محدوده، مستقل از تشخیص پلاک اجرا می‌شود چون
            # باید با فاصله‌ی زمانی کوتاه و ثابت (نه فقط هنگام حرکت بزرگ)
            # دنبال شود تا عبور فرد/حیوان هم از قلم نیفتد.
            if self.zones and self.object_detector is not None:
                now = time.time()
                if (now - last_zone_time) >= config.ZONE_PROCESS_INTERVAL:
                    last_zone_time = now
                    frame = self._process_zone_frame(frame)
                else:
                    frame = self._draw_zone_overlays(frame)

            now = time.time()
            if self.on_preview and (now - last_preview_time) >= config.GUI_PREVIEW_INTERVAL:
                last_preview_time = now
                self.on_preview(self.camera_id, frame)

        cap.release()
        self._notify_status("متوقف شد")

    def _process_frame(self, frame):
        boxes = self.detector.detect_plate_regions(frame)
        full_frame_saved_path = None

        for (x, y, w, h) in boxes:
            crop = frame[y:y + h, x:x + w]
            processed = preprocess_plate_crop(crop)
            plate_text, confidence = self.ocr.read_plate(processed)

            if plate_text and self.logger.should_log(plate_text, camera_name=self.camera_name):
                plate_image_path = self._save_plate_image(crop, plate_text)
                if full_frame_saved_path is None:
                    full_frame_saved_path = self._save_vehicle_image(frame, plate_text)

                self.logger.log_plate(
                    plate_text, confidence, plate_image_path, full_frame_saved_path,
                    camera_name=self.camera_name,
                )

                if self.on_log:
                    self.on_log(self.camera_id, {
                        "camera_name": self.camera_name,
                        "plate_text": plate_text,
                        "confidence": confidence,
                        "plate_image_path": plate_image_path,
                        "vehicle_image_path": full_frame_saved_path,
                    })

            frame = draw_label(frame, (x, y, w, h), plate_text)

        return frame

    def _save_plate_image(self, crop, plate_text):
        import os
        safe_name = plate_text.replace("/", "_")
        safe_cam = "".join(ch for ch in self.camera_name if ch.isalnum()) or "cam"
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_cam}_{safe_name}_{timestamp}.jpg"
        path = os.path.join(config.PLATES_IMAGE_DIR, filename)
        cv2.imwrite(path, crop)
        return path

    def _save_vehicle_image(self, full_frame, plate_text):
        import os
        safe_name = plate_text.replace("/", "_")
        safe_cam = "".join(ch for ch in self.camera_name if ch.isalnum()) or "cam"
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_cam}_{safe_name}_{timestamp}_full.jpg"
        path = os.path.join(config.VEHICLE_IMAGE_DIR, filename)
        cv2.imwrite(path, full_frame)
        return path

    # ------------------------------------------------------------------
    # تشخیص عبور از خط/محدوده (فرد، حیوان، خودرو، موتورسیکلت و ...)
    # ------------------------------------------------------------------
    def _process_zone_frame(self, frame):
        h, w = frame.shape[:2]
        detections = self.object_detector.detect(frame)
        tracked = self.tracker.update(detections)

        for track_id, prev_c, curr_c, category, confidence, box in tracked:
            # جعبه‌ی دور هر شیء تشخیص‌داده‌شده، همیشه رسم می‌شود (حتی اگر عبور نکرده باشد)
            x, y, bw, bh = box
            cv2.rectangle(frame, (x, y), (x + bw, y + bh), (255, 140, 0), 2)
            cv2.putText(frame, category, (x, max(0, y - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 140, 0), 2, cv2.LINE_AA)

            if prev_c is None:
                continue  # این شیء تازه ظاهر شده، هنوز مسیر حرکتی برای مقایسه نداریم

            for zone in self.zones:
                if category not in zone["classes"]:
                    continue

                zone_points = zone_manager.zone_points_absolute(zone, w, h)
                if len(zone_points) < 2:
                    continue

                crossed = False
                if zone["mode"] == "polygon" and len(zone_points) >= 3:
                    crossed = entered_polygon(prev_c, curr_c, zone_points)
                else:
                    crossed = crossed_polyline(prev_c, curr_c, zone_points)

                if crossed and self.logger.should_log_crossing(self.camera_name, zone["name"], category):
                    image_path = self._save_crossing_image(frame, category)
                    self.logger.log_crossing_event(
                        self.camera_name, zone["name"], category, confidence, image_path
                    )
                    if self.on_crossing:
                        self.on_crossing(self.camera_id, {
                            "camera_name": self.camera_name,
                            "zone_name": zone["name"],
                            "category": category,
                            "confidence": confidence,
                            "image_path": image_path,
                        })

        return self._draw_zone_overlays(frame)

    def _draw_zone_overlays(self, frame):
        """خطوط/محدوده‌های تعریف‌شده را همیشه روی تصویر زنده رسم می‌کند تا
        کاربر مطمئن شود کجا را دارد پایش می‌کند."""
        h, w = frame.shape[:2]
        for zone in self.zones:
            pts = zone_manager.zone_points_absolute(zone, w, h)
            pts_int = [(int(px), int(py)) for px, py in pts]
            is_closed = zone["mode"] == "polygon" and len(pts_int) >= 3
            for i in range(len(pts_int) - 1):
                cv2.line(frame, pts_int[i], pts_int[i + 1], (0, 165, 255), 2)
            if is_closed and len(pts_int) >= 2:
                cv2.line(frame, pts_int[-1], pts_int[0], (0, 165, 255), 2)
            if pts_int:
                cv2.putText(frame, zone["name"], pts_int[0],
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2, cv2.LINE_AA)
        return frame

    def _save_crossing_image(self, frame, category):
        safe_cam = "".join(ch for ch in self.camera_name if ch.isalnum()) or "cam"
        safe_cat = "".join(ch for ch in category if ch.isalnum()) or "shi"
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_cam}_{safe_cat}_{timestamp}.jpg"
        path = os.path.join(config.CROSSING_IMAGE_DIR, filename)
        cv2.imwrite(path, frame)
        return path

    def _notify_status(self, text):
        if self.on_status:
            self.on_status(self.camera_id, text)
