"""Generate local reports and hand daily mail to the signed-in Outlook profile."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import json
import logging
from logging.handlers import RotatingFileHandler
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import struct
import subprocess
import sys
import threading
from urllib.parse import urlsplit
import uuid
import zlib

from core import (APP_DIR, Store, category_color, clock,
                  due_days, duration, summary, validate_email)


def chart_png(totals, path=None, size=360):
    entries = [(category_color(key), value) for key, value in totals.items() if value > 0]
    total = sum(value for _, value in entries)
    stops, accumulated = [], 0
    for color, value in entries:
        accumulated += value / total
        stops.append((accumulated, bytes.fromhex(color.lstrip("#"))))
    white, empty = b"\xff\xff\xff", bytes.fromhex("e9eef5")
    scanlines = bytearray()
    center, outer, inner = size / 2, size * .46, size * .29
    for y in range(size):
        scanlines.append(0)
        for x in range(size):
            dx, dy = x + .5 - center, y + .5 - center
            radius = dx * dx + dy * dy
            color = white
            if inner * inner <= radius <= outer * outer:
                angle = ((math.atan2(dy, dx) + math.pi / 2) % math.tau) / math.tau
                color = next((rgb for end, rgb in stops if angle < end), empty)
            scanlines.extend(color)

    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload +
                struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))

    image = (b"\x89PNG\r\n\x1a\n" +
             chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) +
             chunk(b"IDAT", zlib.compress(bytes(scanlines))) + chunk(b"IEND", b""))
    if path is not None:
        Path(path).write_bytes(image)
    return image


def report_html(tasks, result, image, live=False):
    esc = html.escape
    total = result["elapsed"]
    legend = []
    for category, minutes in result["totals"].items():
        percent = f"{minutes / total:.1%}" if total else "—"
        legend.append(
            f'<tr><td style="padding:8px;color:{category_color(category)}">●</td>'
            f'<td style="padding:8px">{esc(category)}</td>'
            f'<td style="padding:8px">{duration(minutes)}</td>'
            f'<td style="padding:8px">{percent}</td></tr>')
    rows = []
    active = {task["id"] for task in result["in_progress"]}
    as_of = dt.datetime.fromisoformat(result["as_of"])
    for task in tasks:
        complete = task["start"] is not None and task["stop"] is not None
        stop = clock(task["stop"])
        if complete:
            spent = duration(task["stop"] - task["start"])
        elif task["id"] in active:
            spent = duration(as_of.hour * 60 + as_of.minute - task["start"]) + "（暂计）"
            stop = "进行中"
        else:
            spent = "待补全，不计入统计"
        cells = (task["name"], task["category"], clock(task["start"]),
                 stop, spent)
        rows.append("<tr>" + "".join(
            f'<td style="padding:10px;border-bottom:1px solid #e7ecf3">{esc(v)}</td>'
            for v in cells) + "</tr>")
    if not rows:
        rows.append('<tr><td colspan="5" style="padding:16px">今天没有任务记录。</td></tr>')
    refresh = '<meta http-equiv="refresh" content="15">' if live else ""
    mode = "实时预览 · 每 15 秒自动更新 · 应用关闭后停止更新" if live else "生成时的数据快照"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">{refresh}<title>每日时间账本</title></head>
<body style="margin:0;background:#f3f6fb;color:#21324b;font:14px 'Segoe UI','Microsoft YaHei',sans-serif">
<table role="presentation" width="100%"><tr><td align="center" style="padding:28px">
<table role="presentation" width="760" style="max-width:100%;background:white"><tr><td style="padding:30px">
<p style="color:#5078ef;font-weight:bold">DAYLEDGER · 时间账本</p>
<h1 style="font-size:27px">{esc(result['day'])} · 每日时间开销</h1>
<p style="color:#728198">统计区间 09:00–{clock(result['boundary'])} · 本机时区</p>
<p style="color:#5078ef">{mode}<br>数据更新于 {esc(result['as_of'].replace('T', ' '))}</p>
<table role="presentation" width="100%" style="background:#f5f7fc"><tr>
<td style="padding:18px">已记录覆盖<br><b>{duration(result['covered'])}</b></td>
<td style="padding:18px">休息 / 未记录<br><b>{duration(result['rest'])}</b></td>
<td style="padding:18px">同时进行时段<br><b>{duration(result['overlap'])}</b></td></tr></table>
<h2 style="font-size:19px">时间分布</h2>
<table role="presentation"><tr><td><img src="{esc(image, quote=True)}" width="280" height="280"
alt="时间分布饼图；详细数值见右侧表格"></td><td><table>{''.join(legend)}</table></td></tr></table>
<p style="color:#728198;line-height:1.8">饼图按实际经过时间统计，重叠时段在同时进行的任务间平分，
各分类与休息合计 {duration(total)}。逐任务原始时长可以重叠相加，
区间内合计 {duration(result['task_total'])}，不代表实际经过时间。<br>
未记录的空档按休息归类，并不证明实际休息。进行中任务共 {len(result['in_progress'])} 项，
用时暂计到当前时间（饼图仅统计到 17:00），不会自动填写 Stop；其他待补全任务共 {len(result['incomplete'])} 项，不计时。
09:00–17:00 以外的任务保留在明细中，不计入工作时段饼图。</p>
<h2 style="font-size:19px">任务明细（原始时长）</h2>
<table width="100%" cellspacing="0" style="border-collapse:collapse;text-align:left">
<tr style="background:#edf2fa"><th style="padding:10px">任务</th><th>分类</th>
<th>Start</th><th>Stop</th><th>时长</th></tr>{''.join(rows)}</table>
<p style="color:#98a3b4;font-size:12px;margin-top:24px">由本机时间账本生成。任务数据保存在本机；本报告通过 Outlook 发送。</p>
</td></tr></table></td></tr></table></body></html>"""


class LivePreview:
    def __init__(self, store):
        self.store = store
        self.token = secrets.token_urlsafe(24)
        preview = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parts = urlsplit(self.path).path.strip("/").split("/")
                if len(parts) != 2 or not secrets.compare_digest(parts[0], preview.token):
                    self.send_error(404)
                    return
                day = parts[1]
                try:
                    dt.date.fromisoformat(day)
                except ValueError:
                    self.send_error(404)
                    return
                try:
                    tasks = preview.store.tasks(day)
                    result = summary(tasks, day)
                    image = "data:image/png;base64," + base64.b64encode(
                        chart_png(result["totals"])).decode("ascii")
                    body = report_html(tasks, result, image, live=True).encode("utf-8")
                except Exception:
                    logging.exception("Live preview failed")
                    self.send_error(500, "Preview failed. Please check the desktop log.")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy",
                                 "default-src 'none'; img-src data:; style-src 'unsafe-inline'; "
                                 "frame-ancestors 'none'")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True,
                                       name="DayLedgerPreview")
        self.thread.start()

    def url(self, day):
        dt.date.fromisoformat(day)
        return f"http://127.0.0.1:{self.server.server_port}/{self.token}/{day}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def generate(store, day, full_day=False, root=None):
    tasks = store.tasks(day)
    result = summary(tasks, day, full_day=full_day)
    folder = (Path(root) if root else store.path.parent / "reports") / day / uuid.uuid4().hex[:12]
    folder.mkdir(parents=True, exist_ok=True)
    chart = folder / "time-distribution.png"
    chart_png(result["totals"], chart)
    preview = folder / "summary.html"
    preview.write_text(report_html(tasks, result, chart.as_uri()), encoding="utf-8")
    body = folder / "email.html"
    body.write_text(report_html(tasks, result, "cid:dayledger-chart"), encoding="utf-8")
    return folder, result


def outlook(payload, mode="Send", timeout=100):
    command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-STA",
               "-ExecutionPolicy", "Bypass", "-File", str(APP_DIR / "outlook.ps1"),
               "-Payload", str(payload), "-Mode", mode]
    return subprocess.run(command, capture_output=True, timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def send_day(store, day, verify=False):
    recipient = validate_email(store.get("recipient"))
    if not verify and not store.claim(day):
        return "already-processed"
    submitted = False
    try:
        folder, _ = generate(store, day, full_day=True)
        payload = folder / "mail.json"
        payload.write_text(json.dumps({
            "recipient": recipient,
            "subject": f"时间账本 | {day} 每日时间汇总 [DayLedger]",
            "body": str(folder / "email.html"),
            "chart": str(folder / "time-distribution.png"),
        }, ensure_ascii=False), encoding="utf-8")
        submitted = True
        completed = outlook(payload, "Verify" if verify else "Send")
        output = completed.stdout.decode("utf-8-sig", errors="replace").strip()
        error = completed.stderr.decode("utf-8-sig", errors="replace").strip()
        if completed.returncode:
            # Exit 2 means Send was not attempted; exit 3 is an ambiguous handoff.
            status = "failed" if completed.returncode == 2 else "uncertain"
            if not verify:
                store.finish(day, status, error[-2000:] or output[-2000:])
            raise RuntimeError(error or output or "Outlook 操作失败。")
        if not verify:
            store.finish(day, "queued", output)
        return output
    except Exception as error:
        if not verify:
            current = store.delivery(day)
            if current and current["status"] == "sending":
                store.finish(day, "uncertain" if submitted else "failed", str(error))
        raise


def run_due(store, now=None):
    now = now or dt.datetime.now()
    if store.get("email_enabled") != "1":
        return
    installed = store.get("installed_on", now.date().isoformat())
    failed = False
    for day in due_days(installed, now):
        try:
            logging.info("%s: %s", day, send_day(store, day))
        except Exception:
            failed = True
            logging.exception("Daily report failed for %s", day)
    if failed:
        raise RuntimeError("部分日报发送失败，请查看本机邮件日志。")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--due", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--preview")
    parser.add_argument("--configure")
    parser.add_argument("--schedule-installed", action="store_true")
    args = parser.parse_args()
    store = Store()
    handler = RotatingFileHandler(store.path.parent / "mail.log",
                                  maxBytes=500_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    if args.configure:
        store.set(recipient=validate_email(args.configure),
                  installed_on=store.get("installed_on", dt.date.today().isoformat()))
    if args.schedule_installed:
        store.set(schedule_installed="1", email_enabled="1")
    if args.verify:
        print(send_day(store, dt.date.today().isoformat(), verify=True))
    if args.preview:
        print(generate(store, args.preview)[0] / "summary.html")
    if args.due:
        run_due(store)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Report command failed")
        if sys.stderr:
            print("DayLedger report failed. See %LOCALAPPDATA%\\DayLedger\\mail.log",
                  file=sys.stderr)
        sys.exit(1)
