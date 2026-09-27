# -*- coding: utf-8 -*-
"""
تشخیص «رویداد عبور خودرو» با استفاده از تفریق پس‌زمینه (Background Subtraction).

هدف: به جای اجرای پیوسته‌ی تشخیص‌پلاک/OCR روی هر فریم (که هم کند است و هم
باعث ثبت تکراری یک خودروی ساکن می‌شود)، فقط وقتی یک جسم متحرک به اندازه‌ی
کافی بزرگ (خودرو) در ناحیه‌ی موردنظر ظاهر شد، به بقیه‌ی خط پردازش
(تشخیص پلاک -> OCR -> ثبت) اجازه‌ی اجرا داده می‌شود.

منطق ساده‌شده:
  - فریم پیش‌زمینه (foreground mask) با MOG2 محاسبه می‌شود.
  - اگر مساحت نواحی متحرک از یک آستانه بیشتر شود، یعنی «رویداد در حال وقوع» است.
  - وقتی حرکت به مدت VEHICLE_EVENT_COOLDOWN_SECONDS متوقف شود، رویداد
    «تمام‌شده» در نظر گرفته می‌شود و رویداد بعدی می‌تواند دوباره پردازش شود.
"""

import time

import cv2
import numpy as np

import config


class VehicleMotionTrigger:
    def __init__(self):
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=300, varThreshold=40, detectShadows=True
        )
        self.last_motion_time = 0.0
        self.event_in_progress = False

    def _roi_slice(self, frame_shape):
        h, w = frame_shape[:2]
        x1r, y1r, x2r, y2r = config.DETECTION_ROI
        return (int(y1r * h), int(y2r * h), int(x1r * w), int(x2r * w))

    def update(self, frame: np.ndarray) -> bool:
        """
        فریم را پردازش می‌کند و True برمی‌گرداند اگر این لحظه لحظه‌ی مناسبی
        برای اجرای تشخیص پلاک/OCR باشد (یعنی یک خودروی جدید در ناحیه است).
        """
        y1, y2, x1, x2 = self._roi_slice(frame.shape)
        roi = frame[y1:y2, x1:x2]

        fg_mask = self.bg_subtractor.apply(roi)
        # حذف سایه (مقدار خاکستری ۱۲۷ در MOG2) و نویز ریز
        _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        fg_mask = cv2.dilate(fg_mask, np.ones((7, 7), np.uint8), iterations=2)

        motion_area = int(np.count_nonzero(fg_mask))
        now = time.time()

        has_significant_motion = motion_area >= config.MIN_VEHICLE_MOTION_AREA

        if has_significant_motion:
            self.last_motion_time = now
            self.event_in_progress = True
            # در تمام طول عبور خودرو (نه فقط لحظه‌ی اول) اجازه‌ی پردازش می‌دهیم؛
            # چون ممکن است در فریم اول، پلاک هنوز به‌خوبی در کادر نباشد.
            # جلوگیری از ثبت تکراری بر عهده‌ی cooldown در storage.py (بر اساس
            # متن پلاک) است، نه اینجا.
            return True
        else:
            # اگر مدتی حرکتی نبود، رویداد را تمام‌شده در نظر بگیر
            if self.event_in_progress and (now - self.last_motion_time) > config.VEHICLE_EVENT_COOLDOWN_SECONDS:
                self.event_in_progress = False
            return False
