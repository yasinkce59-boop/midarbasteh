# -*- coding: utf-8 -*-
"""
اسکریپت کمکی برای مشاهده‌ی گزارش تردد ثبت‌شده در دیتابیس، بدون نیاز به
باز کردن فایل SQLite با ابزار جداگانه.

نمونه‌ی استفاده:
    python report.py                      # ۵۰ رکورد آخر
    python report.py --date 2026-09-25    # ترددهای یک روز خاص
    python report.py --plate 12ب345-67    # جست‌وجوی یک پلاک خاص
"""

import argparse
import sqlite3

import config


def main():
    parser = argparse.ArgumentParser(description="گزارش تردد خودروهای ثبت‌شده")
    parser.add_argument("--date", help="فیلتر بر اساس تاریخ، مثل 2026-09-25")
    parser.add_argument("--plate", help="جست‌وجوی یک پلاک خاص (تطبیق جزئی هم قبول است)")
    parser.add_argument("--limit", type=int, default=50, help="حداکثر تعداد رکورد نمایش داده‌شده")
    args = parser.parse_args()

    conn = sqlite3.connect(config.DB_PATH)
    cur = conn.cursor()

    query = "SELECT plate_text, confidence, timestamp, plate_image_path, vehicle_image_path FROM plates WHERE 1=1"
    params = []

    if args.date:
        query += " AND timestamp LIKE ?"
        params.append(f"{args.date}%")

    if args.plate:
        query += " AND plate_text LIKE ?"
        params.append(f"%{args.plate}%")

    query += " ORDER BY id DESC LIMIT ?"
    params.append(args.limit)

    cur.execute(query, params)
    rows = cur.fetchall()

    if not rows:
        print("رکوردی یافت نشد.")
        return

    print(f"{'پلاک':<15} {'اطمینان':<10} {'زمان':<20} {'عکس پلاک'}")
    print("-" * 90)
    for plate_text, confidence, timestamp, plate_img, vehicle_img in rows:
        print(f"{plate_text:<15} {confidence:<10.2f} {timestamp:<20} {plate_img}")

    print(f"\nتعداد رکورد نمایش داده‌شده: {len(rows)}")
    conn.close()


if __name__ == "__main__":
    main()
