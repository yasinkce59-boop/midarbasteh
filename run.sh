#!/usr/bin/env bash
# اجرای سامانه‌ی ثبت خودکار پلاک روی لینوکس/مک
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "محیط مجازی یافت نشد؛ در حال ساخت (فقط بار اول)..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

python3 gui_app.py
