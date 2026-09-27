# -*- coding: utf-8 -*-
"""
اپلیکیشن دسکتاپ سامانه‌ی ثبت خودکار پلاک.
با رابط گرافیکی ساده (Tkinter) که نیازی به خط فرمان ندارد:
  - تب «دوربین‌ها»: افزودن/ویرایش/حذف/تست اتصال و شروع یا توقف پایش هر دوربین
  - تب «نمایش زنده»: مشاهده‌ی تصویر زنده‌ی هر دوربینِ در حال پایش + لاگ لحظه‌ای
  - تب «گزارش‌ها»: جست‌وجو/فیلتر ترددهای ثبت‌شده و مشاهده‌ی عکس هر رکورد

اجرا:
    python gui_app.py
"""

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import cv2
from PIL import Image, ImageTk

import camera_manager
import config
import zone_manager
from detector import PlateDetector
from ocr_reader import PlateOCR
from object_detector import ObjectDetector
from storage import PlateLogger
from worker import CameraWorker


class LPRApp:
    def __init__(self, root):
        self.root = root
        self.root.title("سامانه ثبت خودکار پلاک")
        self.root.geometry("1000x650")

        # مدل‌های مشترک بین همه‌ی دوربین‌ها؛ چون بارگذاری EasyOCR چند ثانیه
        # طول می‌کشد، در یک ریسه‌ی جداگانه انجام می‌شود تا رابط کاربری قفل نشود.
        self.detector = None
        self.ocr = None
        self.logger = None
        self.object_detector = None
        self.object_detector_error = None
        self.models_ready = False

        self.workers = {}          # camera_id -> CameraWorker
        self.camera_status = {}    # camera_id -> str
        self.preview_queue = queue.Queue()
        self.log_queue = queue.Queue()
        self.status_queue = queue.Queue()
        self.crossing_queue = queue.Queue()
        self.live_photo_cache = None  # جلوگیری از garbage-collect شدن تصویر Tk

        self._build_ui()
        self._refresh_camera_list()
        self._load_reports()
        self._load_crossing_reports()

        self.root.after(150, self._poll_queues)
        threading.Thread(target=self._load_models_background, daemon=True).start()

    # ------------------------------------------------------------------
    # ساخت رابط کاربری
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.status_bar = ttk.Label(
            self.root, text="در حال بارگذاری مدل‌های تشخیص پلاک...", anchor="e",
            relief="sunken", padding=4,
        )
        self.status_bar.pack(side="bottom", fill="x")

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True)

        self.tab_cameras = ttk.Frame(notebook)
        self.tab_live = ttk.Frame(notebook)
        self.tab_zones = ttk.Frame(notebook)
        self.tab_reports = ttk.Frame(notebook)
        self.tab_crossing_reports = ttk.Frame(notebook)

        notebook.add(self.tab_cameras, text="دوربین‌ها")
        notebook.add(self.tab_live, text="نمایش زنده")
        notebook.add(self.tab_zones, text="خط/محدوده هشدار")
        notebook.add(self.tab_reports, text="گزارش پلاک‌ها")
        notebook.add(self.tab_crossing_reports, text="گزارش عبور")

        self._build_cameras_tab()
        self._build_live_tab()
        self._build_zones_tab()
        self._build_reports_tab()
        self._build_crossing_reports_tab()

    # ---------------------- تب دوربین‌ها ----------------------
    def _build_cameras_tab(self):
        frame = self.tab_cameras

        columns = ("name", "source", "status")
        self.camera_tree = ttk.Treeview(frame, columns=columns, show="headings", height=12)
        self.camera_tree.heading("name", text="نام دوربین")
        self.camera_tree.heading("source", text="منبع (دوربین/فایل/RTSP)")
        self.camera_tree.heading("status", text="وضعیت")
        self.camera_tree.column("name", width=180)
        self.camera_tree.column("source", width=400)
        self.camera_tree.column("status", width=150)
        self.camera_tree.pack(fill="both", expand=True, padx=10, pady=10)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        ttk.Button(btn_frame, text="افزودن دوربین", command=self._open_add_camera_dialog).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="ویرایش", command=self._edit_selected_camera).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="حذف", command=self._remove_selected_camera).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="تست اتصال", command=self._test_selected_camera).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="▶ شروع پایش", command=self._start_selected_camera).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="■ توقف پایش", command=self._stop_selected_camera).pack(side="left", padx=4)

    # ---------------------- تب نمایش زنده ----------------------
    def _build_live_tab(self):
        frame = self.tab_live

        top = ttk.Frame(frame)
        top.pack(fill="x", padx=10, pady=10)
        ttk.Label(top, text="دوربین:").pack(side="right", padx=4)
        self.live_camera_combo = ttk.Combobox(top, state="readonly", width=30)
        self.live_camera_combo.pack(side="right", padx=4)

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.video_label = ttk.Label(body, background="#222", anchor="center")
        self.video_label.pack(side="right", fill="both", expand=True)

        log_frame = ttk.Frame(body, width=280)
        log_frame.pack(side="left", fill="y")
        ttk.Label(log_frame, text="آخرین پلاک‌های شناسایی‌شده:").pack(anchor="ne", pady=(0, 4))
        self.live_log_list = tk.Listbox(log_frame, width=36, height=30)
        self.live_log_list.pack(fill="y", expand=True)

    # ---------------------- تب خط/محدوده هشدار ----------------------
    def _build_zones_tab(self):
        frame = self.tab_zones

        top = ttk.Frame(frame)
        top.pack(fill="x", padx=10, pady=10)
        ttk.Label(top, text="دوربین:").pack(side="right", padx=4)
        self.zone_camera_combo = ttk.Combobox(top, state="readonly", width=30)
        self.zone_camera_combo.pack(side="right", padx=4)
        self.zone_camera_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_zone_list())

        ttk.Button(top, text="تعریف خط/محدوده‌ی جدید", command=self._open_zone_editor).pack(side="left", padx=4)
        ttk.Button(top, text="حذف ناحیه‌ی انتخاب‌شده", command=self._remove_selected_zone).pack(side="left", padx=4)

        columns = ("name", "mode", "classes")
        self.zone_tree = ttk.Treeview(frame, columns=columns, show="headings", height=14)
        self.zone_tree.heading("name", text="نام ناحیه")
        self.zone_tree.heading("mode", text="نوع")
        self.zone_tree.heading("classes", text="حساس به")
        self.zone_tree.column("name", width=200)
        self.zone_tree.column("mode", width=100)
        self.zone_tree.column("classes", width=400)
        self.zone_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        hint = ttk.Label(
            frame,
            text="نکته: برای دوربینی که خط/محدوده تعریف شده، پایش خودکار هم تشخیص پلاک و هم عبور از خط را انجام می‌دهد. "
                 "قابلیت تشخیص شیء نیاز به دانلود یک‌بار مدل دارد (فایل download_yolo_model.py را اجرا کنید).",
            foreground="#666", wraplength=850, justify="right",
        )
        hint.pack(anchor="e", padx=10, pady=(0, 10))

    def _open_zone_editor(self):
        sel = self.zone_camera_combo.get()
        if not sel:
            messagebox.showinfo("انتخاب دوربین", "لطفاً ابتدا یک دوربین را از لیست بالا انتخاب کنید.")
            return
        cam_id = self._extract_camera_id(sel)
        cameras = {c["id"]: c for c in camera_manager.load_cameras()}
        cam = cameras.get(cam_id)
        if not cam:
            return

        messagebox.showinfo(
            "در حال دریافت تصویر",
            "یک تصویر نمونه از دوربین گرفته می‌شود، چند لحظه صبر کنید...",
        )
        src = camera_manager.normalize_source(cam["source"])
        cap = cv2.VideoCapture(src)
        ok, frame = cap.read() if cap.isOpened() else (False, None)
        cap.release()

        if not ok or frame is None:
            messagebox.showerror("خطا", "نتوانستیم از این دوربین تصویری بگیریم. اتصال را بررسی کنید.")
            return

        ZoneEditorDialog(self.root, cam_id, cam["name"], frame, on_saved=self._refresh_zone_list)

    def _refresh_zone_list(self):
        self.zone_tree.delete(*self.zone_tree.get_children())
        sel = self.zone_camera_combo.get()
        if not sel:
            return
        cam_id = self._extract_camera_id(sel)
        for zone in zone_manager.get_zones_for_camera(cam_id):
            mode_label = "محدوده (چندضلعی)" if zone["mode"] == "polygon" else "خط"
            self.zone_tree.insert(
                "", "end", iid=zone["id"],
                values=(zone["name"], mode_label, "، ".join(zone["classes"]))
            )

    def _remove_selected_zone(self):
        sel = self.zone_tree.selection()
        if not sel:
            messagebox.showinfo("انتخاب ناحیه", "لطفاً یک ناحیه را از لیست انتخاب کنید.")
            return
        if messagebox.askyesno("حذف ناحیه", "آیا از حذف این ناحیه مطمئن هستید؟"):
            zone_manager.remove_zone(sel[0])
            self._refresh_zone_list()
            messagebox.showinfo(
                "توجه",
                "اگر پایش این دوربین از قبل روشن است، برای اعمال این تغییر یک بار پایش را متوقف و دوباره شروع کنید."
            )

    @staticmethod
    def _extract_camera_id(combo_text):
        # فرمت آیتم کمبوباکس: "نام دوربین (id)"
        return combo_text.rsplit("(", 1)[-1].rstrip(")")

    # ---------------------- تب گزارش‌ها ----------------------
    def _build_reports_tab(self):
        frame = self.tab_reports

        filter_frame = ttk.Frame(frame)
        filter_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(filter_frame, text="تاریخ (YYYY-MM-DD):").pack(side="right", padx=4)
        self.filter_date = ttk.Entry(filter_frame, width=14)
        self.filter_date.pack(side="right", padx=4)

        ttk.Label(filter_frame, text="پلاک:").pack(side="right", padx=4)
        self.filter_plate = ttk.Entry(filter_frame, width=14)
        self.filter_plate.pack(side="right", padx=4)

        ttk.Label(filter_frame, text="دوربین:").pack(side="right", padx=4)
        self.filter_camera = ttk.Entry(filter_frame, width=14)
        self.filter_camera.pack(side="right", padx=4)

        ttk.Button(filter_frame, text="فیلتر / بروزرسانی", command=self._load_reports).pack(side="right", padx=8)
        ttk.Button(filter_frame, text="پاک‌کردن فیلتر", command=self._clear_filters).pack(side="right", padx=4)
        ttk.Button(filter_frame, text="خروجی CSV کامل", command=self._export_csv).pack(side="left", padx=4)

        columns = ("time", "camera", "plate", "confidence")
        self.report_tree = ttk.Treeview(frame, columns=columns, show="headings", height=20)
        self.report_tree.heading("time", text="تاریخ و زمان عبور")
        self.report_tree.heading("camera", text="دوربین")
        self.report_tree.heading("plate", text="پلاک")
        self.report_tree.heading("confidence", text="اطمینان")
        self.report_tree.column("time", width=170)
        self.report_tree.column("camera", width=150)
        self.report_tree.column("plate", width=140)
        self.report_tree.column("confidence", width=90)
        self.report_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.report_tree.bind("<Double-1>", lambda e: self._show_report_image())

        bottom = ttk.Frame(frame)
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bottom, text="نمایش عکس رکورد انتخاب‌شده", command=self._show_report_image).pack(side="right")
        ttk.Label(bottom, text="(برای دیدن عکس می‌توانید روی رکورد دو بار کلیک کنید)").pack(side="right", padx=8)

        # نگه‌داری داده‌ی خام هر ردیف برای دسترسی به مسیر عکس هنگام دوبار-کلیک
        self._report_rows_data = {}

    # ---------------------- تب گزارش عبور ----------------------
    def _build_crossing_reports_tab(self):
        frame = self.tab_crossing_reports

        filter_frame = ttk.Frame(frame)
        filter_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(filter_frame, text="تاریخ (YYYY-MM-DD):").pack(side="right", padx=4)
        self.cross_filter_date = ttk.Entry(filter_frame, width=14)
        self.cross_filter_date.pack(side="right", padx=4)

        ttk.Label(filter_frame, text="نوع شیء:").pack(side="right", padx=4)
        self.cross_filter_category = ttk.Combobox(
            filter_frame, width=14, state="readonly",
            values=[""] + config.OBJECT_CATEGORIES,
        )
        self.cross_filter_category.pack(side="right", padx=4)

        ttk.Label(filter_frame, text="دوربین:").pack(side="right", padx=4)
        self.cross_filter_camera = ttk.Entry(filter_frame, width=14)
        self.cross_filter_camera.pack(side="right", padx=4)

        ttk.Button(filter_frame, text="فیلتر / بروزرسانی", command=self._load_crossing_reports).pack(side="right", padx=8)
        ttk.Button(filter_frame, text="پاک‌کردن فیلتر", command=self._clear_crossing_filters).pack(side="right", padx=4)

        columns = ("time", "camera", "zone", "category", "confidence")
        self.crossing_tree = ttk.Treeview(frame, columns=columns, show="headings", height=20)
        self.crossing_tree.heading("time", text="تاریخ و زمان")
        self.crossing_tree.heading("camera", text="دوربین")
        self.crossing_tree.heading("zone", text="ناحیه")
        self.crossing_tree.heading("category", text="نوع شیء")
        self.crossing_tree.heading("confidence", text="اطمینان")
        self.crossing_tree.column("time", width=160)
        self.crossing_tree.column("camera", width=150)
        self.crossing_tree.column("zone", width=150)
        self.crossing_tree.column("category", width=120)
        self.crossing_tree.column("confidence", width=90)
        self.crossing_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.crossing_tree.bind("<Double-1>", lambda e: self._show_crossing_image())

        bottom = ttk.Frame(frame)
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bottom, text="نمایش عکس رکورد انتخاب‌شده", command=self._show_crossing_image).pack(side="right")
        ttk.Label(bottom, text="(برای دیدن عکس می‌توانید روی رکورد دو بار کلیک کنید)").pack(side="right", padx=8)

        self._crossing_rows_data = {}

    # ------------------------------------------------------------------
    # بارگذاری مدل‌ها در پس‌زمینه
    # ------------------------------------------------------------------
    def _load_models_background(self):
        self.detector = PlateDetector()
        self.ocr = PlateOCR()
        self.logger = PlateLogger()

        # مدل تشخیص اشیاء اختیاری است؛ اگر کاربر هنوز download_yolo_model.py
        # را اجرا نکرده باشد، فقط قابلیت خط/محدوده هشدار غیرفعال می‌ماند و
        # بقیه‌ی برنامه (تشخیص پلاک) طبق معمول کار می‌کند.
        try:
            self.object_detector = ObjectDetector()
        except FileNotFoundError as e:
            self.object_detector = None
            self.object_detector_error = str(e)

        self.models_ready = True
        self.status_queue.put(("__global__", "آماده - می‌توانید پایش را شروع کنید"))

    # ------------------------------------------------------------------
    # مدیریت دوربین‌ها
    # ------------------------------------------------------------------
    def _refresh_camera_list(self):
        self.camera_tree.delete(*self.camera_tree.get_children())
        cameras = camera_manager.load_cameras()
        for cam in cameras:
            status = self.camera_status.get(cam["id"], "متوقف")
            self.camera_tree.insert("", "end", iid=cam["id"], values=(cam["name"], cam["source"], status))

        combo_values = [f'{c["name"]} ({c["id"]})' for c in cameras]
        self.live_camera_combo["values"] = combo_values
        if combo_values and not self.live_camera_combo.get():
            self.live_camera_combo.current(0)

        self.zone_camera_combo["values"] = combo_values
        if combo_values and not self.zone_camera_combo.get():
            self.zone_camera_combo.current(0)
            self._refresh_zone_list()

    def _get_selected_camera_id(self):
        sel = self.camera_tree.selection()
        if not sel:
            messagebox.showinfo("انتخاب دوربین", "لطفاً یک دوربین را از لیست انتخاب کنید.")
            return None
        return sel[0]

    def _open_add_camera_dialog(self, edit_camera=None):
        dialog = tk.Toplevel(self.root)
        dialog.title("ویرایش دوربین" if edit_camera else "افزودن دوربین جدید")
        dialog.geometry("480x260")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="نام دوربین (مثلاً «ورودی اصلی سایت»):").pack(anchor="e", padx=12, pady=(14, 2))
        name_entry = ttk.Entry(dialog, width=45)
        name_entry.pack(padx=12, fill="x")

        ttk.Label(dialog, text="نوع منبع:").pack(anchor="e", padx=12, pady=(12, 2))
        source_type = tk.StringVar(value="rtsp")
        type_frame = ttk.Frame(dialog)
        type_frame.pack(fill="x", padx=12)
        ttk.Radiobutton(type_frame, text="دوربین شبکه / مداربسته (RTSP)", variable=source_type, value="rtsp").pack(anchor="e")
        ttk.Radiobutton(type_frame, text="وبکم متصل به سیستم (شماره)", variable=source_type, value="webcam").pack(anchor="e")
        ttk.Radiobutton(type_frame, text="فایل ویدیویی (برای تست)", variable=source_type, value="file").pack(anchor="e")

        ttk.Label(dialog, text="مقدار منبع:").pack(anchor="e", padx=12, pady=(10, 2))
        source_row = ttk.Frame(dialog)
        source_row.pack(fill="x", padx=12)
        source_entry = ttk.Entry(source_row, width=38)
        source_entry.pack(side="right", fill="x", expand=True)

        def browse_file():
            path = filedialog.askopenfilename(title="انتخاب فایل ویدیویی")
            if path:
                source_entry.delete(0, tk.END)
                source_entry.insert(0, path)

        ttk.Button(source_row, text="انتخاب فایل...", command=browse_file).pack(side="left", padx=4)

        hint = ttk.Label(
            dialog,
            text="نمونه RTSP: rtsp://user:pass@192.168.1.64:554/Streaming/Channels/101   |   وبکم: 0",
            foreground="#666",
        )
        hint.pack(anchor="e", padx=12, pady=(4, 0))

        if edit_camera:
            name_entry.insert(0, edit_camera["name"])
            source_entry.insert(0, edit_camera["source"])
            if edit_camera["source"].isdigit():
                source_type.set("webcam")
            elif edit_camera["source"].startswith("rtsp://"):
                source_type.set("rtsp")
            else:
                source_type.set("file")

        def test_connection():
            src = source_entry.get().strip()
            if not src:
                messagebox.showwarning("خطا", "ابتدا مقدار منبع را وارد کنید.")
                return
            ok, msg = camera_manager.test_camera_connection(src)
            (messagebox.showinfo if ok else messagebox.showerror)("نتیجه‌ی تست اتصال", msg)

        def save():
            name = name_entry.get().strip()
            src = source_entry.get().strip()
            if not name or not src:
                messagebox.showwarning("خطا", "نام و منبع دوربین نباید خالی باشد.")
                return

            if edit_camera:
                camera_manager.update_camera(edit_camera["id"], name, src)
            else:
                camera_manager.add_camera(name, src)

            self._refresh_camera_list()
            dialog.destroy()

        btn_row = ttk.Frame(dialog)
        btn_row.pack(fill="x", padx=12, pady=16)
        ttk.Button(btn_row, text="تست اتصال", command=test_connection).pack(side="left")
        ttk.Button(btn_row, text="ذخیره", command=save).pack(side="right", padx=4)
        ttk.Button(btn_row, text="انصراف", command=dialog.destroy).pack(side="right")

    def _edit_selected_camera(self):
        cam_id = self._get_selected_camera_id()
        if not cam_id:
            return
        cameras = {c["id"]: c for c in camera_manager.load_cameras()}
        cam = cameras.get(cam_id)
        if cam:
            self._open_add_camera_dialog(edit_camera=cam)

    def _remove_selected_camera(self):
        cam_id = self._get_selected_camera_id()
        if not cam_id:
            return
        if cam_id in self.workers:
            messagebox.showwarning("خطا", "ابتدا پایش این دوربین را متوقف کنید.")
            return
        if messagebox.askyesno("حذف دوربین", "آیا از حذف این دوربین مطمئن هستید؟"):
            camera_manager.remove_camera(cam_id)
            self._refresh_camera_list()

    def _test_selected_camera(self):
        cam_id = self._get_selected_camera_id()
        if not cam_id:
            return
        cameras = {c["id"]: c for c in camera_manager.load_cameras()}
        cam = cameras.get(cam_id)
        ok, msg = camera_manager.test_camera_connection(cam["source"])
        (messagebox.showinfo if ok else messagebox.showerror)("نتیجه‌ی تست اتصال", msg)

    def _start_selected_camera(self):
        if not self.models_ready:
            messagebox.showinfo("لطفاً صبر کنید", "مدل‌های تشخیص هنوز در حال بارگذاری هستند.")
            return
        cam_id = self._get_selected_camera_id()
        if not cam_id:
            return
        if cam_id in self.workers:
            messagebox.showinfo("توجه", "این دوربین از قبل در حال پایش است.")
            return

        cameras = {c["id"]: c for c in camera_manager.load_cameras()}
        cam = cameras.get(cam_id)

        cam_zones = zone_manager.get_zones_for_camera(cam_id)
        if cam_zones and self.object_detector is None:
            messagebox.showwarning(
                "مدل تشخیص اشیاء موجود نیست",
                "برای این دوربین خط/محدوده هشدار تعریف شده، اما مدل تشخیص اشیاء دانلود نشده است.\n"
                "پایش پلاک انجام می‌شود ولی تشخیص عبور غیرفعال خواهد بود.\n\n"
                "برای فعال‌سازی، فایل download_yolo_model.py را یک‌بار اجرا کنید."
            )

        worker = CameraWorker(
            camera_id=cam_id, camera_name=cam["name"], source=cam["source"],
            shared_detector=self.detector, shared_ocr=self.ocr, shared_logger=self.logger,
            shared_object_detector=self.object_detector,
            on_preview=lambda cid, frame: self.preview_queue.put((cid, frame)),
            on_log=lambda cid, record: self.log_queue.put((cid, record)),
            on_status=lambda cid, text: self.status_queue.put((cid, text)),
            on_crossing=lambda cid, record: self.crossing_queue.put((cid, record)),
        )
        self.workers[cam_id] = worker
        worker.start()
        self._set_camera_status(cam_id, "در حال اتصال...")
        self._refresh_camera_list()

    def _stop_selected_camera(self):
        cam_id = self._get_selected_camera_id()
        if not cam_id:
            return
        worker = self.workers.pop(cam_id, None)
        if worker:
            worker.stop()
        self._set_camera_status(cam_id, "متوقف شد")
        self._refresh_camera_list()

    def _set_camera_status(self, cam_id, text):
        self.camera_status[cam_id] = text
        if self.camera_tree.exists(cam_id):
            vals = list(self.camera_tree.item(cam_id, "values"))
            if len(vals) == 3:
                vals[2] = text
                self.camera_tree.item(cam_id, values=vals)

    # ------------------------------------------------------------------
    # به‌روزرسانی نمایش زنده و لاگ (اجرا در ریسه‌ی اصلی GUI با after)
    # ------------------------------------------------------------------
    def _poll_queues(self):
        # تصویر پیش‌نمایش
        try:
            while True:
                cam_id, frame = self.preview_queue.get_nowait()
                self._maybe_update_live_view(cam_id, frame)
        except queue.Empty:
            pass

        # لاگ تشخیص‌های جدید (پلاک)
        try:
            while True:
                cam_id, record = self.log_queue.get_nowait()
                entry = f'{record["plate_text"]}   |   {record["camera_name"]}'
                self.live_log_list.insert(0, entry)
                self._load_reports()  # جدول گزارش را هم زنده به‌روز نگه می‌داریم
        except queue.Empty:
            pass

        # رویدادهای عبور از خط/محدوده
        try:
            while True:
                cam_id, record = self.crossing_queue.get_nowait()
                entry = f'⚠ {record["category"]}   |   {record["zone_name"]}   |   {record["camera_name"]}'
                self.live_log_list.insert(0, entry)
                self._load_crossing_reports()
        except queue.Empty:
            pass

        # وضعیت دوربین‌ها
        try:
            while True:
                cam_id, text = self.status_queue.get_nowait()
                if cam_id == "__global__":
                    self.status_bar.config(text=text)
                else:
                    self._set_camera_status(cam_id, text)
        except queue.Empty:
            pass

        self.root.after(150, self._poll_queues)

    def _maybe_update_live_view(self, cam_id, frame_bgr):
        selected = self.live_camera_combo.get()
        if not selected or f"({cam_id})" not in selected:
            return

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)

        max_w, max_h = 760, 560
        img.thumbnail((max_w, max_h))

        self.live_photo_cache = ImageTk.PhotoImage(img)
        self.video_label.configure(image=self.live_photo_cache)

    # ------------------------------------------------------------------
    # گزارش‌ها
    # ------------------------------------------------------------------
    def _load_reports(self):
        if self.logger is None:
            return  # هنوز مدل/دیتابیس آماده نشده

        date_f = self.filter_date.get().strip() or None
        plate_f = self.filter_plate.get().strip() or None
        cam_f = self.filter_camera.get().strip() or None

        rows = self.logger.fetch_records(date_filter=date_f, plate_filter=plate_f, camera_filter=cam_f)

        self.report_tree.delete(*self.report_tree.get_children())
        self._report_rows_data.clear()

        for row in rows:
            rec_id, camera_name, plate_text, confidence, timestamp, plate_img, vehicle_img = row
            iid = str(rec_id)
            self.report_tree.insert(
                "", "end", iid=iid,
                values=(timestamp, camera_name or "-", plate_text, f"{confidence:.2f}")
            )
            self._report_rows_data[iid] = {"plate_image_path": plate_img, "vehicle_image_path": vehicle_img}

    def _clear_filters(self):
        self.filter_date.delete(0, tk.END)
        self.filter_plate.delete(0, tk.END)
        self.filter_camera.delete(0, tk.END)
        self._load_reports()

    def _show_report_image(self):
        sel = self.report_tree.selection()
        if not sel:
            return
        data = self._report_rows_data.get(sel[0])
        if not data:
            return

        path = data.get("vehicle_image_path") or data.get("plate_image_path")
        if not path or not os.path.exists(path):
            messagebox.showinfo("عکس یافت نشد", "فایل عکس این رکورد در دسترس نیست.")
            return

        win = tk.Toplevel(self.root)
        win.title("عکس ثبت‌شده")
        img = Image.open(path)
        img.thumbnail((900, 700))
        photo = ImageTk.PhotoImage(img)
        lbl = ttk.Label(win, image=photo)
        lbl.image = photo  # جلوگیری از garbage collection
        lbl.pack(padx=8, pady=8)

    def _export_csv(self):
        messagebox.showinfo(
            "خروجی CSV",
            f"فایل کامل CSV به‌صورت خودکار به‌روز نگه‌داشته می‌شود و در مسیر زیر است:\n\n{config.CSV_PATH}"
        )

    # ------------------------------------------------------------------
    # گزارش عبور از خط/محدوده
    # ------------------------------------------------------------------
    def _load_crossing_reports(self):
        if self.logger is None:
            return

        date_f = self.cross_filter_date.get().strip() or None
        cam_f = self.cross_filter_camera.get().strip() or None
        cat_f = self.cross_filter_category.get().strip() or None

        rows = self.logger.fetch_crossing_events(
            date_filter=date_f, camera_filter=cam_f, category_filter=cat_f
        )

        self.crossing_tree.delete(*self.crossing_tree.get_children())
        self._crossing_rows_data.clear()

        for row in rows:
            rec_id, camera_name, zone_name, category, confidence, timestamp, image_path = row
            iid = str(rec_id)
            self.crossing_tree.insert(
                "", "end", iid=iid,
                values=(timestamp, camera_name or "-", zone_name or "-", category, f"{confidence:.2f}")
            )
            self._crossing_rows_data[iid] = {"image_path": image_path}

    def _clear_crossing_filters(self):
        self.cross_filter_date.delete(0, tk.END)
        self.cross_filter_camera.delete(0, tk.END)
        self.cross_filter_category.set("")
        self._load_crossing_reports()

    def _show_crossing_image(self):
        sel = self.crossing_tree.selection()
        if not sel:
            return
        data = self._crossing_rows_data.get(sel[0])
        if not data:
            return

        path = data.get("image_path")
        if not path or not os.path.exists(path):
            messagebox.showinfo("عکس یافت نشد", "فایل عکس این رکورد در دسترس نیست.")
            return

        win = tk.Toplevel(self.root)
        win.title("عکس رویداد عبور")
        img = Image.open(path)
        img.thumbnail((900, 700))
        photo = ImageTk.PhotoImage(img)
        lbl = ttk.Label(win, image=photo)
        lbl.image = photo
        lbl.pack(padx=8, pady=8)

    # ------------------------------------------------------------------
    def on_close(self):
        for worker in self.workers.values():
            worker.stop()
        self.root.destroy()


class ZoneEditorDialog:
    """
    پنجره‌ی رسم خط یا محدوده روی یک عکس نمونه‌ی گرفته‌شده از دوربین.
    کاربر با کلیک چپ نقطه اضافه می‌کند؛ اگر گزینه‌ی «محدوده‌ی بسته» را
    فعال کند، در پایان اولین نقطه به آخرین نقطه هم وصل می‌شود (چندضلعی).
    """

    MAX_W, MAX_H = 960, 600

    def __init__(self, parent, camera_id, camera_name, frame_bgr, on_saved=None):
        self.camera_id = camera_id
        self.on_saved = on_saved
        self.points = []  # لیستی از (canvas_x, canvas_y)

        orig_h, orig_w = frame_bgr.shape[:2]
        scale = min(self.MAX_W / orig_w, self.MAX_H / orig_h, 1.0)
        self.disp_w, self.disp_h = int(orig_w * scale), int(orig_h * scale)

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb).resize((self.disp_w, self.disp_h))
        self.photo = ImageTk.PhotoImage(img)

        self.win = tk.Toplevel(parent)
        self.win.title(f"تعریف خط/محدوده هشدار — {camera_name}")
        self.win.transient(parent)
        self.win.grab_set()

        ttk.Label(
            self.win,
            text="با کلیک چپ روی تصویر، نقاط خط یا محدوده را به ترتیب مشخص کنید (کلیک راست = حذف آخرین نقطه).",
            foreground="#333",
        ).pack(padx=10, pady=(10, 4), anchor="e")

        self.canvas = tk.Canvas(self.win, width=self.disp_w, height=self.disp_h, cursor="cross")
        self.canvas.pack(padx=10, pady=4)
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        self.canvas.bind("<Button-1>", self._on_left_click)
        self.canvas.bind("<Button-3>", self._on_right_click)

        options_frame = ttk.Frame(self.win)
        options_frame.pack(fill="x", padx=10, pady=6)

        self.closed_mode = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_frame, text="محدوده‌ی بسته (چندضلعی) به‌جای خط ساده",
            variable=self.closed_mode, command=self._redraw,
        ).pack(anchor="e")

        name_row = ttk.Frame(self.win)
        name_row.pack(fill="x", padx=10, pady=4)
        ttk.Label(name_row, text="نام ناحیه:").pack(side="right", padx=4)
        existing_count = len(zone_manager.get_zones_for_camera(camera_id))
        self.name_entry = ttk.Entry(name_row, width=30)
        self.name_entry.insert(0, f"ناحیه {existing_count + 1}")
        self.name_entry.pack(side="right", padx=4)

        classes_frame = ttk.LabelFrame(self.win, text="حساس به عبور کدام موارد باشد؟")
        classes_frame.pack(fill="x", padx=10, pady=8)

        self.class_vars = {}
        default_checked = {"فرد", "خودرو"}
        for i, cat in enumerate(config.OBJECT_CATEGORIES):
            var = tk.BooleanVar(value=(cat in default_checked))
            self.class_vars[cat] = var
            ttk.Checkbutton(classes_frame, text=cat, variable=var).grid(
                row=i // 4, column=i % 4, sticky="e", padx=10, pady=4
            )

        note = ttk.Label(
            self.win,
            text="نکته: «تریلی» جزو دسته‌ی «کامیون/تریلی» تشخیص داده می‌شود.",
            foreground="#777",
        )
        note.pack(anchor="e", padx=10)

        btn_row = ttk.Frame(self.win)
        btn_row.pack(fill="x", padx=10, pady=12)
        ttk.Button(btn_row, text="پاک کردن نقاط", command=self._clear_points).pack(side="left")
        ttk.Button(btn_row, text="ذخیره", command=self._save).pack(side="right", padx=4)
        ttk.Button(btn_row, text="انصراف", command=self.win.destroy).pack(side="right")

    def _on_left_click(self, event):
        self.points.append((event.x, event.y))
        self._redraw()

    def _on_right_click(self, event):
        if self.points:
            self.points.pop()
            self._redraw()

    def _clear_points(self):
        self.points = []
        self._redraw()

    def _redraw(self):
        self.canvas.delete("drawing")
        for i, (x, y) in enumerate(self.points):
            r = 5
            self.canvas.create_oval(x - r, y - r, x + r, y + r, fill="#ff8c00", outline="", tags="drawing")
            if i > 0:
                px, py = self.points[i - 1]
                self.canvas.create_line(px, py, x, y, fill="#ff8c00", width=3, tags="drawing")

        if self.closed_mode.get() and len(self.points) >= 3:
            fx, fy = self.points[0]
            lx, ly = self.points[-1]
            self.canvas.create_line(lx, ly, fx, fy, fill="#ff8c00", width=3, dash=(6, 3), tags="drawing")

    def _save(self):
        min_points = 3 if self.closed_mode.get() else 2
        if len(self.points) < min_points:
            messagebox.showwarning(
                "نقاط ناکافی",
                f"برای {'محدوده' if self.closed_mode.get() else 'خط'} حداقل به {min_points} نقطه نیاز است."
            )
            return

        selected_classes = [cat for cat, var in self.class_vars.items() if var.get()]
        if not selected_classes:
            messagebox.showwarning("انتخاب دسته", "حداقل یک دسته (مثل فرد یا خودرو) را انتخاب کنید.")
            return

        name = self.name_entry.get().strip()
        mode = "polygon" if self.closed_mode.get() else "line"
        points_relative = [(x / self.disp_w, y / self.disp_h) for x, y in self.points]

        zone_manager.add_zone(self.camera_id, name, points_relative, mode, selected_classes)

        if self.on_saved:
            self.on_saved()
        self.win.destroy()


def main():
    root = tk.Tk()
    app = LPRApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
