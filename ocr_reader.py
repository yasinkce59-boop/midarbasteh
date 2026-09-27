# -*- coding: utf-8 -*-
"""
لایه‌ی OCR: متن روی برش پلاک را با استفاده از EasyOCR می‌خواند.

EasyOCR انتخاب شده چون:
  - از فارسی/عربی پشتیبانی می‌کند (بر خلاف Tesseract که برای فارسی
    نیازمند دیتای زبان جداگانه و تنظیم دقیق است)
  - نصب و استفاده‌ی آن ساده‌تر است و روی CPU هم قابل استفاده است
    (کندتر از GPU، ولی برای این کاربرد کافی است)
"""

import easyocr
import config
from utils import extract_plate_text


class PlateOCR:
    def __init__(self):
        # gpu=False به صورت پیش‌فرض تا روی هر سیستمی بدون کارت گرافیک هم اجرا شود.
        # model_storage_directory: مدل‌ها کنار خودِ exe نگه‌داری می‌شوند (نه در
        # پوشه‌ی کاربر ویندوز)؛ اگر این پوشه از قبل با فلش پر شده باشد، هیچ
        # دانلودی لازم نیست. اگر خالی باشد و اینترنت باشد، خودکار دانلود می‌شود.
        self.reader = easyocr.Reader(
            config.OCR_LANGUAGES,
            gpu=False,
            verbose=False,
            model_storage_directory=config.OCR_MODELS_DIR,
            download_enabled=True,
        )

    def read_plate(self, plate_crop_gray):
        """
        روی تصویر خاکستری/پیش‌پردازش‌شده‌ی پلاک OCR اجرا می‌کند.
        خروجی: تاپل (متن_قالب‌بندی‌شده یا None, میزان_اطمینان)
        """
        if plate_crop_gray is None or plate_crop_gray.size == 0:
            return None, 0.0

        results = self.reader.readtext(plate_crop_gray, detail=1, paragraph=False)
        if not results:
            return None, 0.0

        # همه‌ی قطعات متن شناسایی‌شده در ناحیه را به هم می‌چسبانیم
        # (چون پلاک ممکن است به چند تکه جدا تشخیص داده شود)
        combined_text = " ".join([r[1] for r in results])
        avg_conf = sum(r[2] for r in results) / len(results)

        if avg_conf < config.OCR_MIN_CONFIDENCE:
            return None, avg_conf

        plate_text = extract_plate_text(combined_text)
        return plate_text, avg_conf
