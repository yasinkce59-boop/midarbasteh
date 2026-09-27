# -*- coding: utf-8 -*-
"""
مدیریت لیست دوربین‌های تعریف‌شده توسط کاربر.
دوربین‌ها در یک فایل JSON ساده (cameras.json) نگه‌داری می‌شوند تا با
بستن و باز کردن دوباره‌ی برنامه، تنظیمات کاربر از دست نرود.
"""

import json
import os
import uuid

import cv2

import config


def load_cameras():
    if not os.path.exists(config.CAMERAS_JSON_PATH):
        return []
    try:
        with open(config.CAMERAS_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_cameras(cameras):
    with open(config.CAMERAS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(cameras, f, ensure_ascii=False, indent=2)


def add_camera(name: str, source: str):
    cameras = load_cameras()
    new_cam = {"id": str(uuid.uuid4())[:8], "name": name.strip(), "source": source.strip()}
    cameras.append(new_cam)
    save_cameras(cameras)
    return new_cam


def update_camera(camera_id: str, name: str, source: str):
    cameras = load_cameras()
    for cam in cameras:
        if cam["id"] == camera_id:
            cam["name"] = name.strip()
            cam["source"] = source.strip()
            break
    save_cameras(cameras)


def remove_camera(camera_id: str):
    cameras = load_cameras()
    cameras = [c for c in cameras if c["id"] != camera_id]
    save_cameras(cameras)


def normalize_source(source: str):
    """اگر منبع فقط یک عدد باشد (اندیس وبکم)، به int تبدیل می‌شود؛ وگرنه رشته
    (مسیر فایل یا آدرس RTSP) بدون تغییر باقی می‌ماند."""
    source = source.strip()
    if source.isdigit():
        return int(source)
    return source


def test_camera_connection(source: str, timeout_frames: int = 30):
    """
    تلاش می‌کند به منبع تصویر متصل شود و یک فریم بخواند.
    خروجی: (موفق: bool, پیام: str)
    """
    src = normalize_source(source)
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        cap.release()
        return False, "اتصال برقرار نشد. آدرس/شماره دوربین یا شبکه را بررسی کنید."

    ok, frame = cap.read()
    cap.release()

    if not ok or frame is None:
        return False, "اتصال برقرار شد ولی فریمی دریافت نشد. RTSP یا کاربری/رمز را بررسی کنید."

    h, w = frame.shape[:2]
    return True, f"اتصال موفق ✓  (رزولوشن دریافتی: {w}x{h})"
