"""Native, dependency-free desktop interface for DayLedger."""

from __future__ import annotations

import csv
import ctypes
import datetime as dt
import logging
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core import (APP_DIR, CATEGORIES, CATEGORY_ADD_OPTION, Store, category_color, clock, duration,
                  parse_time, summary, validate_email)
from report import LivePreview


BG, WHITE, INK, MUTED, BLUE = "#f3f6fb", "#ffffff", "#21324b", "#7c8a9e", "#5078ef"


class CategorySelector(ttk.Combobox):
    def __init__(self, parent, store, variable):
        self.store, self.variable = store, variable
        self.previous = variable.get()
        self.on_change = None
        self.add_dialog = None
        super().__init__(parent, textvariable=variable,
                         values=(*store.categories(), CATEGORY_ADD_OPTION), state="readonly")
        self.bind("<<ComboboxSelected>>", self.select)

    def select(self, _=None):
        if self.variable.get() == CATEGORY_ADD_OPTION:
            self.variable.set(self.previous)
            self.add_category()
        else:
            self.previous = self.variable.get()
            if self.on_change:
                self.on_change()
        return "break"

    def add_category(self):
        if self.add_dialog is not None and self.add_dialog.winfo_exists():
            self.add_dialog.lift()
            return
        parent = self.winfo_toplevel()
        previous_grab = parent.grab_current()
        dialog = self.add_dialog = tk.Toplevel(parent)
        dialog.title("添加分类")
        dialog.configure(bg=BG)
        dialog.transient(parent)
        dialog.resizable(False, False)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="新分类名称（1–40 个字符）").pack(anchor="w")
        name = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=name, width=30)
        entry.pack(fill="x", pady=(10, 16))

        def close(_=None):
            dialog.destroy()
            self.add_dialog = None
            if previous_grab is not None and previous_grab.winfo_exists():
                previous_grab.grab_set()
            if self.winfo_exists():
                self.focus_set()
            return "break"

        def save(_=None):
            try:
                category = self.store.add_category(name.get())
            except ValueError as error:
                messagebox.showerror("无法添加分类", str(error), parent=dialog)
                return "break"
            self.configure(values=(*self.store.categories(), CATEGORY_ADD_OPTION))
            self.variable.set(category)
            self.previous = category
            close()
            if self.on_change:
                self.on_change()
            return "break"

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="取消", command=close).pack(side="right")
        ttk.Button(buttons, text="保存分类", command=save,
                   style="Primary.TButton").pack(side="right", padx=(0, 8))
        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.bind("<Escape>", close)
        dialog.bind("<Return>", save)
        entry.focus_set()


class TimeSelector(ttk.Frame):
    def __init__(self, parent, variable):
        super().__init__(parent)
        self.variable = variable
        self.hour, self.minute = tk.StringVar(), tk.StringVar()
        self.hours = ttk.Combobox(
            self, textvariable=self.hour, values=tuple(f"{n:02d}" for n in range(24)),
            state="readonly", width=4, height=12)
        self.hours.pack(side="left")
        ttk.Label(self, text=" : ").pack(side="left")
        self.minutes = ttk.Combobox(
            self, textvariable=self.minute, values=tuple(f"{n:02d}" for n in range(60)),
            state="readonly", width=4, height=12)
        self.minutes.pack(side="left")
        self.hours.bind("<<ComboboxSelected>>", self.select)
        self.minutes.bind("<<ComboboxSelected>>", self.select)
        ttk.Button(self, text="现在", command=self.now).pack(side="left", padx=(10, 4))
        ttk.Button(self, text="清空", command=lambda: self.set("")).pack(side="left")
        self.set(variable.get())

    def set(self, value):
        minutes = parse_time(value)
        self.variable.set(clock(minutes))
        self.hour.set("" if minutes is None else f"{minutes // 60:02d}")
        self.minute.set("" if minutes is None else f"{minutes % 60:02d}")

    def select(self, _=None):
        self.set(f"{self.hour.get() or '09'}:{self.minute.get() or '00'}")

    def now(self):
        self.set(dt.datetime.now().strftime("%H:%M"))


class App:
    def __init__(self, root, store=None):
        self.root, self.store = root, store or Store()
        self.day = dt.date.today()
        self.editor = None
        self.preview_server = None
        self.results = queue.Queue()
        self.rows = []
        root.title("时间账本 · DayLedger")
        root.configure(bg=BG)
        root.geometry(f"{min(1360, root.winfo_screenwidth()-80)}x"
                      f"{min(870, root.winfo_screenheight()-90)}")
        root.minsize(1060, 650)
        self.style()
        self.build()
        self.refresh()
        # Native font sizes grow with Windows DPI; reserve space for the footer.
        root.update_idletasks()
        available_height = root.winfo_screenheight() - 90
        required_height = root.winfo_reqheight()
        root.geometry(f"{min(1360, root.winfo_screenwidth()-80)}x"
                      f"{min(available_height, max(870, required_height + 16))}")
        root.minsize(1060, min(available_height, max(650, required_height)))
        root.after(1000, self.tick)
        root.after(150, self.drain_jobs)
        root.report_callback_exception = self.callback_error
        root.protocol("WM_DELETE_WINDOW", self.close)

    def style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 10), background=BG,
                        foreground=INK)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=WHITE)
        style.configure("TLabel", background=BG, foreground=INK)
        style.configure("Card.TLabel", background=WHITE)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("TButton", padding=(13, 8), background=WHITE, borderwidth=0)
        style.map("TButton", background=[("active", "#e7edfc")])
        style.configure("Primary.TButton", background=BLUE, foreground=WHITE)
        style.map("Primary.TButton", background=[("active", "#3b60cc")])
        style.configure("Treeview", background=WHITE, fieldbackground=WHITE,
                        foreground=INK, rowheight=45, borderwidth=0)
        style.configure("Treeview.Heading", background="#edf2fa",
                        foreground=MUTED, padding=(10, 12), relief="flat")
        style.map("Treeview", background=[("selected", "#e5edff")],
                  foreground=[("selected", INK)])
        style.configure("TEntry", padding=7)
        style.configure("TCombobox", padding=6)

    def build(self):
        outer = ttk.Frame(self.root, padding=24)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x")
        title = ttk.Frame(header)
        title.pack(side="left")
        ttk.Label(title, text="时间账本", font=("Microsoft YaHei UI", 23, "bold")).pack(anchor="w")
        ttk.Label(title, text="记录每一段投入，也为休息留白。", style="Muted.TLabel").pack(anchor="w", pady=(5, 0))
        ttk.Button(header, text="邮件设置", command=self.settings).pack(side="right", padx=(8, 0))
        ttk.Button(header, text="预览日报", command=self.preview).pack(side="right")

        nav = ttk.Frame(outer)
        nav.pack(fill="x", pady=(22, 16))
        ttk.Button(nav, text="‹", width=3, command=lambda: self.shift(-1)).pack(side="left")
        self.date_var = tk.StringVar(value=self.day.isoformat())
        date_entry = ttk.Entry(nav, textvariable=self.date_var, width=13, justify="center")
        date_entry.pack(side="left", padx=8)
        date_entry.bind("<Return>", lambda _: self.change_date())
        ttk.Button(nav, text="›", width=3, command=lambda: self.shift(1)).pack(side="left")
        ttk.Button(nav, text="今天", command=self.today).pack(side="left", padx=8)
        self.interval = ttk.Label(nav, style="Muted.TLabel")
        self.interval.pack(side="right")

        stats = ttk.Frame(outer)
        stats.pack(fill="x", pady=(0, 18))
        self.metrics = []
        for i, label in enumerate(("已记录覆盖", "休息 / 未记录", "同时进行时段", "任务数量")):
            stats.columnconfigure(i, weight=1, uniform="stats")
            box = ttk.Frame(stats, style="Card.TFrame", padding=(18, 12))
            box.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 10, 0))
            ttk.Label(box, text=label, style="Card.TLabel", foreground=MUTED).pack(anchor="w")
            value = ttk.Label(box, text="—", style="Card.TLabel",
                              font=("Microsoft YaHei UI", 18, "bold"))
            value.pack(anchor="w", pady=(4, 0))
            self.metrics.append(value)

        content = ttk.Frame(outer)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=0, minsize=310)
        content.rowconfigure(0, weight=1)
        left = ttk.Frame(content, style="Card.TFrame", padding=16)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        actions = ttk.Frame(left, style="Card.TFrame")
        actions.pack(fill="x", pady=(0, 14))
        ttk.Label(actions, text="任务清单", style="Card.TLabel",
                  font=("Microsoft YaHei UI", 13, "bold")).pack(side="left")
        ttk.Button(actions, text="+ 添加任务", style="Primary.TButton",
                   command=self.add_task).pack(side="right")
        tools = ttk.Frame(left, style="Card.TFrame")
        tools.pack(fill="x", pady=(0, 12))
        for text, command in (("Start 现在", lambda: self.stamp("start")),
                              ("Stop 现在", lambda: self.stamp("stop")),
                              ("删除", self.delete), ("导出 CSV", self.export)):
            ttk.Button(tools, text=text, command=command).pack(side="left", padx=(0, 6))
        table_frame = ttk.Frame(left, style="Card.TFrame")
        table_frame.pack(fill="both", expand=True)
        columns = ("name", "category", "start", "stop", "duration")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        for key, label, width, stretch in zip(
                columns, ("任务", "分类", "Start ▾", "Stop ▾", "时长"),
                (240, 150, 72, 72, 200), (True, False, False, False, False)):
            self.table.heading(key, text=label)
            self.table.column(key, width=width, minwidth=65, stretch=stretch,
                              anchor="w" if key == "name" else "center")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        horizontal = ttk.Scrollbar(table_frame, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.table.bind("<Double-1>", self.edit_cell)
        self.table.bind("<ButtonRelease-1>", self.pick_time_cell)
        self.table.bind("<Delete>", lambda _: self.delete())
        ttk.Label(left, text="单击时间选择 · 双击分类选择，或在下拉框中「＋ 添加分类…」",
                  style="Card.TLabel", foreground=MUTED).pack(anchor="w", pady=(12, 0))
        self.empty = ttk.Label(left, text="", style="Card.TLabel", foreground=MUTED)
        self.empty.pack(anchor="w", pady=(4, 0))

        right = ttk.Frame(content, style="Card.TFrame", padding=18)
        right.grid(row=0, column=1, sticky="nsew")
        ttk.Label(right, text="时间分布", style="Card.TLabel",
                  font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w")
        self.chart = tk.Canvas(right, width=270, height=235, bg=WHITE, highlightthickness=0)
        self.chart.pack(pady=(5, 0))
        legend_box = ttk.Frame(right, style="Card.TFrame")
        legend_box.pack(fill="x")
        self.legend_canvas = tk.Canvas(
            legend_box, width=300, height=round(135 * float(self.root.tk.call("tk", "scaling"))),
            bg=WHITE, highlightthickness=0)
        legend_scroll = ttk.Scrollbar(legend_box, orient="vertical",
                                      command=self.legend_canvas.yview)
        self.legend_canvas.configure(yscrollcommand=legend_scroll.set)
        self.legend_canvas.pack(side="left", fill="x", expand=True)
        legend_scroll.pack(side="right", fill="y")
        self.legend_frame = ttk.Frame(self.legend_canvas, style="Card.TFrame")
        legend_window = self.legend_canvas.create_window(
            (0, 0), window=self.legend_frame, anchor="nw", width=300)
        self.legend_frame.bind("<Configure>", lambda _: self.legend_canvas.configure(
            scrollregion=self.legend_canvas.bbox("all")))
        self.legend_canvas.bind("<Configure>", lambda event: self.legend_canvas.itemconfigure(
            legend_window, width=event.width))
        self.legend, self.legend_categories = [], ()
        ttk.Label(right, text="重叠时段按任务平分，饼图不重复计时。\n进行中任务暂计到现在，不自动填写 Stop。",
                  style="Card.TLabel", foreground=MUTED,
                  font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(12, 0))

        bottom = ttk.Frame(outer)
        bottom.pack(fill="x", pady=(14, 0))
        self.status = ttk.Label(bottom, style="Muted.TLabel", wraplength=1100)
        self.status.pack(anchor="w")
        self.mail_status = ttk.Label(bottom, style="Muted.TLabel", wraplength=1100)
        self.mail_status.pack(anchor="w", pady=(4, 0))

    def selected(self):
        selection = self.table.selection()
        return next((row for row in self.rows if str(row["id"]) in selection), None)

    def refresh(self):
        if self.editor is not None:
            return
        selected = self.table.selection()
        day = self.day.isoformat()
        self.rows = self.store.tasks(day)
        now = dt.datetime.now()
        result = summary(self.rows, day, now=now)
        active = {row["id"] for row in result["in_progress"]}
        self.table.delete(*self.table.get_children())
        for row in self.rows:
            complete = row["start"] is not None and row["stop"] is not None
            if complete:
                spent = duration(row["stop"] - row["start"])
            elif row["id"] in active:
                spent = duration(now.hour * 60 + now.minute - row["start"]) + " · 进行中"
            else:
                spent = "待补全"
            self.table.insert("", "end", iid=str(row["id"]), values=(
                row["name"], row["category"], clock(row["start"]), clock(row["stop"]), spent))
        for item in selected:
            if self.table.exists(item):
                self.table.selection_set(item)
        for widget, value in zip(self.metrics, (
                duration(result["covered"]), duration(result["rest"]),
                duration(result["overlap"]), f"{len(self.rows)} 项")):
            widget.configure(text=value)
        self.interval.configure(text=f"工作时段 09:00–17:00  ·  统计至 {clock(result['boundary'])}")
        self.empty.configure(text="" if self.rows else "还没有任务。点击「添加任务」，可以先列计划，再补时间。")
        self.draw_chart(result)
        self.status.configure(text=(
            f"已自动保存到本机  ·  区间内任务原始时长合计 {duration(result['task_total'])}"
            f"（含重叠）  ·  {len(result['incomplete'])} 项时间待补全"
            f"  ·  {len(result['in_progress'])} 项进行中（暂计到现在）"
            "  ·  工作时段外的时间不计入饼图"))
        delivery = self.store.delivery(day)
        if delivery:
            states = {"queued": "已交给 Outlook（请以发件箱 / 已发送邮件为准）",
                      "sending": "发送处理中；若长时间未更新，请查邮件日志",
                      "failed": "发送失败，计划任务将重试；可在邮件设置中查看日志",
                      "uncertain": "发送结果待确认，为避免重复未自动重发；请查 Outlook 和日志"}
            mail = f"{day} 日报：{states.get(delivery['status'], delivery['status'])}"
        elif self.store.get("email_enabled") == "1":
            installed = self.store.get("schedule_installed") == "1"
            mail = ("工作日 17:00 自动发送日报" if installed else "自动邮件尚未安装，请打开邮件设置安装") + (
                "  ·  关闭本窗口仍有效；电脑需开机、用户保持登录，Outlook 需可用")
        else:
            mail = "自动邮件已暂停，可在「邮件设置」中启用。"
        self.mail_status.configure(text=mail)

    def draw_chart(self, result):
        canvas = self.chart
        canvas.delete("all")
        total, angle = result["elapsed"], 90
        bounds = (29, 10, 241, 222)
        if not total:
            canvas.create_oval(*bounds, fill="#e9eef5", outline="")
        else:
            for category, minutes in result["totals"].items():
                extent = minutes / total * 360
                if extent >= 359.999:
                    canvas.create_oval(*bounds, fill=category_color(category), outline="")
                elif extent > 0:
                    canvas.create_arc(*bounds, start=angle, extent=-extent,
                                      fill=category_color(category), outline=WHITE, width=2)
                angle -= extent
        canvas.create_oval(65, 46, 205, 186, fill=WHITE, outline=WHITE)
        canvas.create_text(135, 101, text=duration(total), fill=INK,
                           font=("Microsoft YaHei UI", 17, "bold"))
        canvas.create_text(135, 132, text="已过工作时间" if total else "工作时段尚未开始",
                           fill=MUTED, font=("Microsoft YaHei UI", 9))
        categories = tuple(result["totals"])
        if categories != self.legend_categories:
            for child in self.legend_frame.winfo_children():
                child.destroy()
            self.legend, self.legend_categories = [], categories
            for category in categories:
                line = ttk.Frame(self.legend_frame, style="Card.TFrame")
                line.pack(fill="x", pady=4)
                line.columnconfigure(1, weight=1)
                ttk.Label(line, text="●", foreground=category_color(category),
                          style="Card.TLabel").grid(row=0, column=0, sticky="nw")
                ttk.Label(line, text=category, style="Card.TLabel",
                          wraplength=110).grid(row=0, column=1, sticky="w", padx=6)
                amount = ttk.Label(line, style="Card.TLabel", foreground=MUTED,
                                   font=("Microsoft YaHei UI", 9))
                amount.grid(row=0, column=2, sticky="e")
                self.legend.append(amount)
            self.legend_canvas.yview_moveto(0)
        for widget, minutes in zip(self.legend, result["totals"].values()):
            percent = f"{minutes / total:.0%}" if total else "—"
            widget.configure(text=f"{duration(minutes)}  ·  {percent}")

    def change_date(self):
        try:
            day = dt.date.fromisoformat(self.date_var.get().strip())
            self.close_editor()
            self.day = day
            self.date_var.set(day.isoformat())
            self.refresh()
        except ValueError:
            messagebox.showerror("日期格式", "请使用 YYYY-MM-DD，例如 2026-11-17。", parent=self.root)
            self.date_var.set(self.day.isoformat())

    def shift(self, amount):
        self.date_var.set((self.day + dt.timedelta(days=amount)).isoformat())
        self.change_date()

    def today(self):
        self.date_var.set(dt.date.today().isoformat())
        self.change_date()

    def add_task(self):
        dialog = tk.Toplevel(self.root)
        dialog.title(f"添加任务 · {self.day}")
        dialog.configure(bg=BG)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=24)
        frame.pack(fill="both", expand=True)
        name, category, start, stop = (tk.StringVar() for _ in range(4))
        category.set(CATEGORIES[0])
        variables = (name, category, start, stop)
        first = None
        for i, (label, variable) in enumerate(zip(
                ("任务名称", "分类", "Start（可留空）", "Stop（可留空）"), variables)):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky="w", pady=8, padx=(0, 16))
            if i >= 2:
                widget = TimeSelector(frame, variable)
            elif i == 1:
                widget = CategorySelector(frame, self.store, variable)
            else:
                widget = ttk.Entry(frame, textvariable=variable, width=34)
            widget.grid(row=i, column=1, sticky="ew", pady=8)
            if first is None:
                first = widget
        ttk.Label(frame, text="分类下拉框中可「＋ 添加分类…」；时间可选择，也可留空。",
                  style="Muted.TLabel").grid(row=4, column=0, columnspan=2, pady=12)

        def save(_=None):
            try:
                task_id = self.store.save(self.day.isoformat(), name.get(), category.get(),
                                          parse_time(start.get()), parse_time(stop.get()))
            except ValueError as error:
                messagebox.showerror("无法保存", str(error), parent=dialog)
                return
            dialog.destroy()
            self.refresh()
            self.table.selection_set(str(task_id))
            self.table.see(str(task_id))

        ttk.Button(frame, text="保存任务", command=save, style="Primary.TButton").grid(
            row=5, column=1, sticky="e")
        dialog.bind("<Return>", save)
        dialog.bind("<Escape>", lambda _: dialog.destroy())
        first.focus_set()

    def close_editor(self):
        if self.editor is not None:
            widget, self.editor = self.editor, None
            widget.destroy()

    def pick_time_cell(self, event):
        if self.table.identify_column(event.x) in ("#3", "#4"):
            self.edit_cell(event)

    def edit_cell(self, event):
        self.close_editor()
        item = self.table.identify_row(event.y)
        column = self.table.identify_column(event.x)
        if not item or column not in ("#1", "#2", "#3", "#4"):
            return
        row = next(row for row in self.rows if str(row["id"]) == item)
        key = ("name", "category", "start", "stop")[int(column[1:]) - 1]
        box = self.table.bbox(item, column)
        if not box:
            return
        if key in ("start", "stop"):
            self.pick_time(row, key)
            return "break"
        value = row[key]
        variable = tk.StringVar(value=value)
        widget = (CategorySelector(self.table, self.store, variable)
                  if key == "category" else ttk.Entry(self.table, textvariable=variable))
        self.editor = widget
        widget.place(x=box[0], y=box[1], width=box[2], height=box[3])
        widget.focus_set()
        if isinstance(widget, ttk.Entry):
            widget.selection_range(0, "end")

        def finish(_=None):
            if self.editor is not widget:
                return
            text = variable.get()
            self.close_editor()
            edited = dict(row)
            try:
                edited[key] = text
                self.store.save(edited["day"], edited["name"], edited["category"],
                                edited["start"], edited["stop"], edited["id"])
            except ValueError as error:
                messagebox.showerror("无法保存", str(error), parent=self.root)
            self.refresh()

        widget.bind("<Return>", finish)
        widget.bind("<Escape>", lambda _: self.close_editor())
        if key == "category":
            widget.on_change = finish
        else:
            widget.bind("<FocusOut>", finish)
        return "break"

    def pick_time(self, row, key):
        dialog = tk.Toplevel(self.root)
        self.editor = dialog
        label = "Start" if key == "start" else "Stop"
        dialog.title(f"选择 {label} 时间")
        dialog.configure(bg=BG)
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"{row['name'][:40]} · {label}",
                  font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", pady=(0, 14))
        value = tk.StringVar(value=clock(row[key]))
        selector = TimeSelector(frame, value)
        selector.pack(fill="x")
        ttk.Label(frame, text="从左到右选择小时、分钟；清空后该时间留待补全。",
                  style="Muted.TLabel").pack(anchor="w", pady=14)

        def save(_=None):
            edited = dict(row)
            edited[key] = parse_time(value.get())
            try:
                self.store.save(edited["day"], edited["name"], edited["category"],
                                edited["start"], edited["stop"], edited["id"])
            except ValueError as error:
                messagebox.showerror("无法保存", str(error), parent=dialog)
                return "break"
            self.close_editor()
            self.refresh()
            return "break"

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="取消", command=self.close_editor).pack(side="right")
        ttk.Button(buttons, text="确定", command=save,
                   style="Primary.TButton").pack(side="right", padx=(0, 8))
        dialog.protocol("WM_DELETE_WINDOW", self.close_editor)
        dialog.bind("<Escape>", lambda _: self.close_editor())
        dialog.bind("<Return>", save)
        selector.hours.focus_set()

    def stamp(self, key):
        self.close_editor()
        row = self.selected()
        if not row:
            messagebox.showinfo("选择任务", "请先选择一条任务。", parent=self.root)
            return
        if self.day != dt.date.today():
            messagebox.showinfo("仅用于今天", "历史或未来日期请单击时间单元格选择时间。", parent=self.root)
            return
        now = dt.datetime.now()
        edited = dict(row)
        edited[key] = now.hour * 60 + now.minute
        try:
            self.store.save(edited["day"], edited["name"], edited["category"],
                            edited["start"], edited["stop"], edited["id"])
        except ValueError as error:
            messagebox.showerror("无法更新时间", str(error), parent=self.root)
        self.refresh()

    def delete(self):
        self.close_editor()
        row = self.selected()
        if row and messagebox.askyesno("删除任务", f"确定删除「{row['name']}」？", parent=self.root):
            self.store.delete(row["id"])
            self.refresh()

    def export(self):
        path = filedialog.asksaveasfilename(
            parent=self.root, title="导出任务", defaultextension=".csv",
            initialfile=f"时间账本-{self.day}.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("日期", "任务", "分类", "Start", "Stop", "原始分钟数"))
            for row in self.rows:
                # Prevent user-defined text from becoming spreadsheet formulas.
                fields = [("'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text)
                          for text in (row["name"], row["category"])]
                minutes = row["stop"] - row["start"] if (
                    row["start"] is not None and row["stop"] is not None) else ""
                writer.writerow((row["day"], *fields,
                                 clock(row["start"]), clock(row["stop"]), minutes))
        os.startfile(path)

    def preview(self):
        self.refresh()
        if self.preview_server is None:
            self.preview_server = LivePreview(self.store)
        os.startfile(self.preview_server.url(self.day.isoformat()))

    def close(self):
        if self.preview_server is not None:
            self.preview_server.close()
            self.preview_server = None
        self.root.destroy()

    def background(self, work, success):
        def run():
            try:
                self.results.put((success, work(), None))
            except Exception as error:
                self.results.put((success, None, str(error)))
        threading.Thread(target=run, daemon=True).start()

    def drain_jobs(self):
        try:
            while True:
                callback, value, error = self.results.get_nowait()
                if error:
                    messagebox.showerror("操作失败", error, parent=self.root)
                else:
                    callback(value)
        except queue.Empty:
            pass
        self.root.after(150, self.drain_jobs)

    def settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("邮件与本机数据")
        dialog.configure(bg=BG)
        dialog.transient(self.root)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=24)
        frame.pack(fill="both", expand=True)
        recipient = tk.StringVar(value=self.store.get("recipient"))
        enabled = tk.BooleanVar(value=self.store.get("email_enabled") == "1")
        ttk.Label(frame, text="日报收件邮箱").pack(anchor="w")
        ttk.Entry(frame, textvariable=recipient, width=56).pack(fill="x", pady=(8, 14))
        ttk.Checkbutton(frame, text="工作日 17:00 自动发送（本机时区）",
                        variable=enabled).pack(anchor="w")
        ttk.Label(frame, text=(
            "统计时段：09:00–17:00。重叠时段平分，空档归为休息。\n"
            "关闭窗口不影响计划任务；电脑需开机，Windows 用户需保持登录。\n"
            "使用已登录的经典 Outlook；离线时邮件可能留在发件箱。\n"
            "错过发送时间后会补发最近 7 天的未处理日报，不会重复自动发送。"),
            style="Muted.TLabel", justify="left").pack(anchor="w", pady=16)
        installed = self.store.get("schedule_installed") == "1"
        ttk.Label(frame, text="计划任务：" + ("已安装" if installed else "尚未安装")).pack(anchor="w")

        def save():
            try:
                address = validate_email(recipient.get())
            except ValueError as error:
                messagebox.showerror("邮箱格式", str(error), parent=dialog)
                return False
            self.store.set(recipient=address, email_enabled="1" if enabled.get() else "0")
            self.refresh()
            return True

        def repair():
            if not save():
                return
            address, active = recipient.get().strip(), enabled.get()
            dialog.destroy()

            def work():
                result = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                     "-File", str(APP_DIR / "install.ps1"), "-Recipient", address,
                     "-Executable" if getattr(sys, "frozen", False) else "-Python",
                     sys.executable, "-NoLaunch"],
                    capture_output=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode:
                    raise RuntimeError(result.stderr.decode(errors="replace") or "计划任务安装失败。")
                if not active:
                    self.store.set(email_enabled="0")
                return "计划任务已安装 / 修复。"

            def done(value):
                self.refresh()
                messagebox.showinfo("完成", value, parent=self.root)
            self.background(work, done)

        def open_log():
            path = self.store.path.parent / "mail.log"
            path.touch(exist_ok=True)
            os.startfile(str(path))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(18, 0))
        ttk.Button(buttons, text="打开数据文件夹",
                   command=lambda: os.startfile(str(self.store.path.parent))).pack(side="left")
        ttk.Button(buttons, text="邮件日志", command=open_log).pack(side="left", padx=8)
        ttk.Button(frame, text="安装 / 修复计划任务", command=repair).pack(anchor="w", pady=12)
        ttk.Button(frame, text="保存设置", style="Primary.TButton",
                   command=lambda: dialog.destroy() if save() else None).pack(anchor="e")

    def tick(self):
        if self.editor is None:
            self.refresh()
        self.root.after(30_000, self.tick)

    def callback_error(self, kind, value, traceback):
        logging.error("Desktop callback failed", exc_info=(kind, value, traceback))
        messagebox.showerror("操作失败", str(value), parent=self.root)


def main():
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except OSError:
            pass
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DayLedger.Desktop")
    root = tk.Tk()
    store = Store()
    logging.basicConfig(filename=store.path.parent / "desktop.log", encoding="utf-8",
                        level=logging.WARNING)
    App(root, store)
    root.mainloop()


if __name__ == "__main__":
    main()
