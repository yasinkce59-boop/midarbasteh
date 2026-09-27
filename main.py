# -*- coding: utf-8 -*-
"""
سامانه‌ی ساده‌ی ثبت خودکار پلاک (Automatic License Plate Recognition - ALPR/LPR)

نحوه‌ی اجرا:
    python main.py
    python main.py --source 0
    python main.py --source video_test.mp4
    python main.py --source "rtsp://user:pass@192.168.1.10:554/stream1" --no-display

فرآیند کلی:
    دریافت فریم از دوربین  -->  تشخیص ناحیه‌ی احتمالی پلاک  -->
    پیش‌پردازش برش پلاک    -->  OCR و استخراج متن پلاک      -->
    اعتبارسنجی و ثبت در دیتابیس/CSV  -->  نمایش روی تصویر زنده
"""

import argparse
import os
import time

import cv2

import config
from detector import PlateDetector
from ocr_reader import PlateOCR
from storage import PlateLogger
from motion_trigger import VehicleMotionTrigger
from utils import preprocess_plate_crop, draw_label


def parse_args():
    parser = argparse.ArgumentParser(description="سامانه‌ی ثبت خودکار پلاک")
    parser.add_argument(
        "--source", default=None,
        help="منبع ویدیو: شماره‌ی دوربین (مثلاً 0)، مسیر فایل ویدیویی یا آدرس RTSP"
    )
    parser.add_argument(
        "--no-display", action="store_true",
        help="اجرا بدون نمایش پنجره‌ی تصویر زنده (مناسب اجرا روی سرور)"
    )
    return parser.parse_args()


def open_video_source(source):
    """ورودی رشته‌ای را در صورت عددی بودن به int تبدیل می‌کند (برای اندیس دوربین)."""
    if source is None:
        source = config.VIDEO_SOURCE
    if isinstance(source, str) and source.isdigit():
        source = int(source)
    return cv2.VideoCapture(source)


def main():
    args = parse_args()
    show_display = config.SHOW_DISPLAY_WINDOW and not args.no_display

    cap = open_video_source(args.source)
    if not cap.isOpened():
        print("خطا: امکان اتصال به منبع تصویری وجود ندارد. لطفاً مقدار --source را بررسی کنید.")
        return

    print("در حال بارگذاری مدل‌ها (ممکن است چند ثانیه طول بکشد)...")
    detector = PlateDetector()
    ocr = PlateOCR()
    logger = PlateLogger()
    motion_trigger = VehicleMotionTrigger() if config.ENABLE_MOTION_TRIGGER else None
    print("آماده‌ی پردازش تصویر. برای خروج کلید q را بزنید.")

    last_process_time = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("پایان استریم یا خطا در دریافت فریم. تلاش برای اتصال مجدد...")
                # برای استریم‌های RTSP که ممکن است قطع شوند، به‌جای توقف کامل
                # برنامه، دوباره تلاش برای اتصال می‌کنیم.
                cap.release()
                time.sleep(2)
                cap = open_video_source(args.source)
                continue

            # اگر motion trigger فعال است، فقط وقتی خودرویی در ناحیه‌ی
            # تشخیص وارد شده باشد پردازش پلاک/OCR (که سنگین‌تر است) اجرا می‌شود؛
            # در غیر این صورت (دوربین معمولی بدون این قابلیت) طبق فاصله‌ی
            # زمانی ثابت پردازش انجام می‌شود.
            should_process = True
            if motion_trigger is not None:
                should_process = motion_trigger.update(frame)
            else:
                now = time.time()
                should_process = (now - last_process_time) >= config.FRAME_PROCESS_INTERVAL
                if should_process:
                    last_process_time = now

            if should_process:
                frame = process_frame(frame, detector, ocr, logger)

            if show_display:
                cv2.imshow("LPR - سامانه ثبت خودکار پلاک", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    finally:
        cap.release()
        cv2.destroyAllWindows()
        logger.close()


def process_frame(frame, detector: PlateDetector, ocr: PlateOCR, logger: PlateLogger):
    boxes = detector.detect_plate_regions(frame)
    full_frame_saved_path = None  # عکس کامل صحنه فقط یک بار در صورت ثبت موفق ذخیره می‌شود

    for (x, y, w, h) in boxes:
        crop = frame[y:y + h, x:x + w]
        processed = preprocess_plate_crop(crop)

        plate_text, confidence = ocr.read_plate(processed)

        if plate_text and logger.should_log(plate_text):
            plate_image_path = save_plate_image(crop, plate_text)
            if full_frame_saved_path is None:
                full_frame_saved_path = save_vehicle_image(frame, plate_text)
            logger.log_plate(plate_text, confidence, plate_image_path, full_frame_saved_path)

        frame = draw_label(frame, (x, y, w, h), plate_text)

    return frame


def save_plate_image(crop, plate_text):
    safe_name = plate_text.replace("/", "_")
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_name}_{timestamp}.jpg"
    path = os.path.join(config.PLATES_IMAGE_DIR, filename)
    cv2.imwrite(path, crop)
    return path


def save_vehicle_image(full_frame, plate_text):
    """عکس کامل صحنه (کل خودرو، نه فقط پلاک) را ذخیره می‌کند تا در صورت نیاز
    بازبینی انسانی (مثلاً اختلاف با نگهبانی سایت) امکان‌پذیر باشد."""
    safe_name = plate_text.replace("/", "_")
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_name}_{timestamp}_full.jpg"
    path = os.path.join(config.VEHICLE_IMAGE_DIR, filename)
    cv2.imwrite(path, full_frame)
    return path


if __name__ == "__main__":
    main()
