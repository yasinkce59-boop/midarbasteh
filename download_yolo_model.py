# -*- coding: utf-8 -*-
"""
دانلود یک‌باره‌ی مدل تشخیص اشیاء (YOLOv4-tiny) برای قابلیت «خط/محدوده هشدار».

این مدل سبک، اشیاء رایج مثل فرد، خودرو، موتورسیکلت، اتوبوس، کامیون،
دوچرخه و چند نوع حیوان را می‌تواند تشخیص دهد (بر پایه‌ی دیتاست COCO).

این اسکریپت را روی یک سیستمِ متصل به اینترنت اجرا کنید. پس از اجرا، پوشه‌ی
yolo_model/ (کنار همین فایل‌ها) با سه فایل مدل پر می‌شود. دقیقاً مثل
download_models.py، اگر این پوشه را همراه با بقیه‌ی فایل‌های برنامه (یا
کنار فایل exe نهایی) با فلش منتقل کنید، آن سیستم هم دیگر نیازی به اینترنت
نخواهد داشت.

اجرا:
    python download_yolo_model.py
"""

import os
import urllib.request

import config

# فایل‌های رسمی YOLOv4-tiny از مخزن AlexeyAB/darknet روی گیت‌هاب
FILES = {
    config.YOLO_CFG_PATH:
        "https://raw.githubusercontent.com/AlexeyAB/darknet/master/cfg/yolov4-tiny.cfg",
    config.YOLO_WEIGHTS_PATH:
        "https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v4_pre/yolov4-tiny.weights",
    config.YOLO_NAMES_PATH:
        "https://raw.githubusercontent.com/AlexeyAB/darknet/master/data/coco.names",
}


def _download(url: str, dest_path: str):
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        print(f"از قبل موجود است، رد شد: {os.path.basename(dest_path)}")
        return

    print(f"در حال دانلود {os.path.basename(dest_path)} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as response, open(dest_path, "wb") as out_file:
        total = response.length or 0
        downloaded = 0
        chunk_size = 1024 * 256
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            out_file.write(chunk)
            downloaded += len(chunk)
            if total:
                percent = downloaded * 100 // total
                print(f"\r  {percent}%", end="", flush=True)
        print()


def main():
    print(f"مقصد دانلود: {config.YOLO_MODEL_DIR}")
    for dest_path, url in FILES.items():
        _download(url, dest_path)

    print("\nدانلود مدل تشخیص اشیاء با موفقیت تمام شد.")
    print("از این پس پوشه‌ی «yolo_model» را همراه با برنامه نگه دارید یا با فلش منتقل کنید.")


if __name__ == "__main__":
    main()
