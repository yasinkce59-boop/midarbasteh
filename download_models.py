# -*- coding: utf-8 -*-
"""
دانلود یک‌باره‌ی مدل‌های OCR به پوشه‌ی محلی کنار برنامه (config.OCR_MODELS_DIR).

این اسکریپت را روی یک سیستمِ متصل به اینترنت اجرا کنید. پس از اجرا، پوشه‌ی
easyocr_models/ (کنار همین فایل‌ها) پر می‌شود. اگر همین پوشه را همراه با
بقیه‌ی فایل‌های برنامه (یا کنار فایل exe نهایی) با فلش به یک سیستم دیگر
منتقل کنید، آن سیستم در اولین اجرا هم دیگر نیازی به اینترنت نخواهد داشت.

اجرا:
    python download_models.py
"""

import easyocr
import config


def main():
    print(f"در حال دانلود مدل‌های OCR به مسیر: {config.OCR_MODELS_DIR}")
    print("بسته به سرعت اینترنت ممکن است چند دقیقه طول بکشد...")

    easyocr.Reader(
        config.OCR_LANGUAGES,
        gpu=False,
        verbose=True,
        model_storage_directory=config.OCR_MODELS_DIR,
        download_enabled=True,
    )

    print("\nدانلود مدل‌ها با موفقیت تمام شد.")
    print(f"از این پس پوشه‌ی «easyocr_models» را همراه با برنامه نگه دارید یا با فلش منتقل کنید.")


if __name__ == "__main__":
    main()
