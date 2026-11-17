"""Local storage and overlap-aware time accounting for DayLedger."""

from __future__ import annotations

import datetime as dt
import colorsys
import hashlib
import os
from pathlib import Path
import re
import sqlite3
from contextlib import contextmanager


CATEGORIES = ("做 case", "学习", "讨论", "健身", "娱乐")
REST = "休息 / 未记录"
CATEGORY_ADD_OPTION = "＋ 添加分类…"
COLORS = dict(zip((*CATEGORIES, REST),
                  ("#5078ef", "#9970db", "#19a896", "#ec9a42", "#df7197", "#dce3ed")))
WORK_START, WORK_END = 9 * 60, 17 * 60
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "DayLedger"


def category_color(category):
    if category in COLORS:
        return COLORS[category]
    hue = int.from_bytes(hashlib.sha256(category.encode("utf-8")).digest()[:2], "big") / 65536
    rgb = colorsys.hls_to_rgb(hue, .56, .60)
    return "#" + "".join(f"{round(channel * 255):02x}" for channel in rgb)


def validate_category(category):
    category = category.strip()
    if not category or len(category) > 40:
        raise ValueError("分类名称请填写 1–40 个字符。")
    if category in (REST, CATEGORY_ADD_OPTION):
        raise ValueError("该名称是系统保留名称，请使用其他分类名称。")
    if any(ord(char) < 32 or ord(char) == 127 for char in category):
        raise ValueError("分类名称不能包含换行、制表符等控制字符。")
    return category


def parse_time(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    if not re.fullmatch(r"(?:[01]?\d|2[0-3]):[0-5]\d", value):
        raise ValueError("时间请使用 HH:MM 格式，例如 09:30。")
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def clock(value: int | None) -> str:
    return "" if value is None else f"{value // 60:02d}:{value % 60:02d}"


def duration(minutes: float) -> str:
    rounded = round(minutes)
    hours, mins = divmod(rounded, 60)
    return f"{hours} 小时 {mins:02d} 分" if hours else f"{mins} 分钟"


def validate_task(day, name, category, start, stop):
    dt.date.fromisoformat(day)
    if not name.strip():
        raise ValueError("请填写任务名称。")
    if len(name.strip()) > 500:
        raise ValueError("任务名称不能超过 500 个字符。")
    validate_category(category)
    for value in (start, stop):
        if value is not None and (type(value) is not int or not 0 <= value < 1440):
            raise ValueError("时间必须在 00:00–23:59 之间。")
    if start is not None and stop is not None and stop <= start:
        raise ValueError("Stop 必须晚于 Start；跨天任务请拆成两条记录。")


class Store:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else DATA_DIR / "ledger.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY,
                    day TEXT NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    start INTEGER,
                    stop INTEGER
                );
                CREATE INDEX IF NOT EXISTS tasks_day ON tasks(day);
                CREATE TABLE IF NOT EXISTS categories (
                    name TEXT PRIMARY KEY
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS deliveries (
                    day TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    updated TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT ''
                );
            """)
            db.executemany("INSERT OR IGNORE INTO categories(name) VALUES(?)",
                           [(name,) for name in CATEGORIES])
            db.execute("INSERT OR IGNORE INTO categories(name) "
                       "SELECT category FROM tasks GROUP BY category ORDER BY MIN(id)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def tasks(self, day):
        dt.date.fromisoformat(day)
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM tasks WHERE day=? ORDER BY start IS NULL, start, id", (day,))]

    def save(self, day, name, category, start, stop, task_id=None):
        category = validate_category(category)
        validate_task(day, name, category, start, stop)
        values = (day, name.strip(), category, start, stop)
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", (category,))
            if task_id is None:
                return db.execute(
                    "INSERT INTO tasks(day,name,category,start,stop) VALUES(?,?,?,?,?)",
                    values).lastrowid
            cursor = db.execute(
                "UPDATE tasks SET day=?,name=?,category=?,start=?,stop=? WHERE id=?",
                (*values, task_id))
            if cursor.rowcount != 1:
                raise ValueError("该任务已被删除，请刷新后重试。")
        return task_id

    def categories(self):
        with self.connect() as db:
            return tuple(row[0] for row in db.execute("SELECT name FROM categories ORDER BY rowid"))

    def add_category(self, name):
        name = validate_category(name)
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", (name,))
        return name

    def delete(self, task_id):
        with self.connect() as db:
            db.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    def get(self, key, default=""):
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set(self, **settings):
        with self.connect() as db:
            db.executemany("INSERT INTO settings(key,value) VALUES(?,?) "
                           "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                           [(key, str(value)) for key, value in settings.items()])

    def delivery(self, day):
        with self.connect() as db:
            row = db.execute("SELECT * FROM deliveries WHERE day=?", (day,)).fetchone()
        return dict(row) if row else None

    def claim(self, day):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM deliveries WHERE day=?", (day,)).fetchone()
            if row and row[0] in ("sending", "queued", "uncertain"):
                return False
            db.execute(
                "INSERT INTO deliveries(day,status,updated,detail) VALUES(?,?,?,'') "
                "ON CONFLICT(day) DO UPDATE SET status=excluded.status,"
                "updated=excluded.updated,detail=''",
                (day, "sending", dt.datetime.now().isoformat(timespec="seconds")))
        return True

    def finish(self, day, status, detail=""):
        with self.connect() as db:
            db.execute("UPDATE deliveries SET status=?,updated=?,detail=? WHERE day=?",
                       (status, dt.datetime.now().isoformat(timespec="seconds"), detail, day))


def summary(tasks, day: str, now: dt.datetime | None = None, full_day=False):
    selected = dt.date.fromisoformat(day)
    now = now or dt.datetime.now()
    boundary = WORK_END
    if not full_day:
        if selected == now.date():
            boundary = min(WORK_END, max(WORK_START, now.hour * 60 + now.minute))
        elif selected > now.date():
            boundary = WORK_START
    totals = dict.fromkeys(CATEGORIES, 0.0)
    raw = dict.fromkeys(CATEGORIES, 0)
    intervals, incomplete, in_progress = [], [], []
    for task in tasks:
        totals.setdefault(task["category"], 0.0)
        raw.setdefault(task["category"], 0)
        if task["start"] is None:
            incomplete.append(task)
            continue
        stop = task["stop"]
        if stop is None:
            if selected != now.date() or task["start"] > now.hour * 60 + now.minute:
                incomplete.append(task)
                continue
            stop = now.hour * 60 + now.minute
            in_progress.append(task)
        start, stop = max(WORK_START, task["start"]), min(boundary, stop)
        if stop > start:
            intervals.append((start, stop, task["category"], task["id"]))
            raw[task["category"]] += stop - start
    points = sorted({WORK_START, boundary, *(v for row in intervals for v in row[:2])})
    covered = rest = overlap = extra = 0
    segments = []
    for start, stop in zip(points, points[1:]):
        active = [row for row in intervals if row[0] <= start and row[1] >= stop]
        minutes = stop - start
        if not active:
            rest += minutes
        else:
            covered += minutes
            if len(active) > 1:
                overlap += minutes
                extra += minutes * (len(active) - 1)
            # Share wall-clock minutes between tasks, not just distinct categories.
            for row in active:
                totals[row[2]] += minutes / len(active)
        segments.append((start, stop, tuple(row[2] for row in active)))
    totals[REST] = rest
    return dict(day=day, boundary=boundary, elapsed=boundary - WORK_START,
                totals=totals, raw=raw, covered=covered, rest=rest, overlap=overlap,
                extra=extra, task_total=sum(raw.values()), incomplete=incomplete,
                in_progress=in_progress, as_of=now.isoformat(timespec="seconds"),
                segments=segments)


def validate_email(address):
    if not re.fullmatch(r"[^@\s;,<>]+@[^@\s;,<>]+\.[^@\s;,<>]+", address.strip()):
        raise ValueError("请填写一个有效的收件邮箱地址。")
    return address.strip()


def due_days(installed_on, now):
    first = max(dt.date.fromisoformat(installed_on), now.date() - dt.timedelta(days=7))
    result = []
    while first <= now.date():
        if first.weekday() < 5 and (first < now.date() or now.hour >= 17):
            result.append(first.isoformat())
        first += dt.timedelta(days=1)
    return result
