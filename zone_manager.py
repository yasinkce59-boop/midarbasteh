# -*- coding: utf-8 -*-
"""
مدیریت خط‌ها/محدوده‌های هشدارِ تعریف‌شده توسط کاربر برای هر دوربین.

نقاط هر خط/محدوده به‌صورت نسبی (بین ۰ تا ۱ نسبت به عرض و ارتفاع فریم)
ذخیره می‌شوند، نه پیکسل مطلق؛ این‌طوری اگر رزولوشن دوربین بعداً تغییر
کند یا محدوده روی یک عکس با اندازه‌ی متفاوت تعریف شده باشد، مختصات همچنان
درست باقی می‌ماند.
"""

import json
import os
import uuid

import config


def load_zones():
    if not os.path.exists(config.ZONES_JSON_PATH):
        return []
    try:
        with open(config.ZONES_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_zones(zones):
    with open(config.ZONES_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(zones, f, ensure_ascii=False, indent=2)


def get_zones_for_camera(camera_id):
    return [z for z in load_zones() if z["camera_id"] == camera_id]


def add_zone(camera_id: str, name: str, points_relative, mode: str, classes):
    """
    points_relative: لیستی از (x, y) با مقادیر بین ۰ تا ۱
    mode: "line" (خط باز) یا "polygon" (محدوده‌ی بسته)
    classes: لیستی از دسته‌های موردنظر کاربر، مثل ["فرد", "خودرو"]
    """
    zones = load_zones()
    new_zone = {
        "id": str(uuid.uuid4())[:8],
        "camera_id": camera_id,
        "name": name.strip() or "ناحیه بدون نام",
        "points": [[round(p[0], 5), round(p[1], 5)] for p in points_relative],
        "mode": mode,
        "classes": list(classes),
    }
    zones.append(new_zone)
    save_zones(zones)
    return new_zone


def remove_zone(zone_id: str):
    zones = load_zones()
    zones = [z for z in zones if z["id"] != zone_id]
    save_zones(zones)


def zone_points_absolute(zone, frame_width, frame_height):
    """تبدیل نقاط نسبی یک ناحیه به مختصات پیکسلی مطلق برای یک فریم به‌خصوص."""
    return [(p[0] * frame_width, p[1] * frame_height) for p in zone["points"]]
