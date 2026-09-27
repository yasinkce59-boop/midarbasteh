# -*- coding: utf-8 -*-
"""
توابع کمکی: پیش‌پردازش تصویر و اعتبارسنجی/قالب‌بندی متن پلاک ایران.

قالب رایج پلاک شخصی ایران به صورت زیر است:
    NN L NNN IR PP
مثال:  12  ب   345  ایران  67
که در تصویر پلاک به صورت چپ‌به‌راست دیده می‌شود:
    [دو رقم] [یک حرف فارسی] [سه رقم]   [دو رقم کد شهر]

چون خروجی OCR همیشه تمیز نیست، اینجا چند تابع برای پاک‌سازی و
تطبیق آن با الگوی بالا با استفاده از عبارت باقاعده (regex) آمده است.
"""

import re
import cv2
import numpy as np

# حروف رایج به کار رفته در پلاک‌های شخصی/دولتی/عمومی ایران
PERSIAN_PLATE_LETTERS = "الف ب پ ت ث ج د ز س ص ط ع ف ق ک گ ل م ن و ه ی D S".split()

# الگوی اعتبارسنجی: دو رقم + یک حرف + سه رقم + (فاصله اختیاری) + دو رقم کد شهر
PLATE_PATTERN = re.compile(
    r"(?P<part1>\d{2})\s*(?P<letter>[^\d\sA-Za-z]{1})\s*(?P<part2>\d{3})\s*(?:ایران|IR)?\s*(?P<city>\d{2})"
)


def preprocess_plate_crop(crop_bgr: np.ndarray) -> np.ndarray:
    """
    یک برش (crop) از ناحیه‌ی احتمالی پلاک را برای OCR آماده می‌کند:
    خاکستری‌سازی، بزرگ‌نمایی و افزایش کنتراست.
    """
    if crop_bgr is None or crop_bgr.size == 0:
        return crop_bgr

    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)

    # بزرگ‌نمایی برای خواناتر شدن کاراکترها (OCR روی تصاویر کوچک ضعیف عمل می‌کند)
    h, w = gray.shape[:2]
    scale = 3 if max(h, w) < 300 else 1.5
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # کاهش نویز با حفظ لبه‌ها
    gray = cv2.bilateralFilter(gray, 9, 75, 75)

    # افزایش کنتراست موضعی
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    return gray


def normalize_digits(text: str) -> str:
    """ارقام فارسی/عربی را به ارقام لاتین معادل تبدیل می‌کند."""
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    arabic_digits = "٠١٢٣٤٥٦٧٨٩"
    latin_digits = "0123456789"
    table = {}
    for p, a, l in zip(persian_digits, arabic_digits, latin_digits):
        table[p] = l
        table[a] = l
    return "".join(table.get(ch, ch) for ch in text)


def extract_plate_text(raw_text: str):
    """
    از متن خام خروجی OCR، پلاک را استخراج و قالب‌بندی می‌کند.
    در صورت موفقیت رشته‌ای به شکل "12ب345-67" برمی‌گرداند، وگرنه None.
    """
    if not raw_text:
        return None

    text = normalize_digits(raw_text)
    text = text.replace("\n", " ").strip()

    match = PLATE_PATTERN.search(text)
    if not match:
        return None

    part1 = match.group("part1")
    letter = match.group("letter")
    part2 = match.group("part2")
    city = match.group("city")

    return f"{part1}{letter}{part2}-{city}"


def draw_label(frame, box, text):
    """کادر سبز رنگ و متن پلاک را روی فریم رسم می‌کند."""
    x, y, w, h = box
    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 200, 0), 2)
    label = text if text else "..."
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    cv2.rectangle(frame, (x, y - th - 12), (x + tw + 6, y), (0, 200, 0), -1)
    cv2.putText(
        frame, label, (x + 3, y - 6),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2, cv2.LINE_AA
    )
    return frame
