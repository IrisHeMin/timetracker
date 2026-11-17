import datetime as dt
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import zlib
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from core import (CATEGORIES, CATEGORY_ADD_OPTION, REST, Store, category_color, clock, due_days, parse_time,
                  summary, validate_email, validate_task)
import report


DAY = "2026-11-17"


def task(identity, start, stop, category=CATEGORIES[0], name="A task"):
    return dict(id=identity, day=DAY, name=name, category=category, start=start, stop=stop)


class AccountingTests(unittest.TestCase):
    def full(self, rows):
        return summary(rows, DAY, now=dt.datetime(2026, 11, 18, 18), full_day=True)

    def test_disjoint_intervals_and_gaps(self):
        result = self.full([task(1, 540, 600), task(2, 630, 690, CATEGORIES[1])])
        self.assertEqual((result["covered"], result["rest"], result["overlap"]), (120, 360, 0))
        self.assertEqual(sum(result["totals"].values()), 480)

    def test_overlap_shares_wall_clock_but_preserves_raw_time(self):
        result = self.full([task(1, 540, 660), task(2, 600, 720, CATEGORIES[1])])
        self.assertEqual(result["totals"][CATEGORIES[0]], 90)
        self.assertEqual(result["totals"][CATEGORIES[1]], 90)
        self.assertEqual((result["task_total"], result["covered"], result["rest"]), (240, 180, 300))
        self.assertEqual((result["overlap"], result["extra"]), (60, 60))
        self.assertEqual(sum(result["totals"].values()), 480)

    def test_shares_by_task_not_distinct_category(self):
        result = self.full([
            task(1, 540, 600), task(2, 540, 600), task(3, 540, 600, CATEGORIES[1])])
        self.assertEqual(result["totals"][CATEGORIES[0]], 40)
        self.assertEqual(result["totals"][CATEGORIES[1]], 20)
        self.assertEqual(result["extra"], 120)

    def test_adjacent_intervals_are_not_overlapping(self):
        result = self.full([task(1, 540, 600), task(2, 600, 660)])
        self.assertEqual(result["overlap"], 0)
        self.assertEqual(result["covered"], 120)

    def test_clips_work_hours_without_changing_tasks(self):
        rows = [task(1, 480, 600), task(2, 960, 1080), task(3, 300, 360)]
        result = self.full(rows)
        self.assertEqual(result["covered"], 120)
        self.assertEqual(result["task_total"], 120)
        self.assertEqual(rows[1]["stop"], 1080)

    def test_partial_tasks_are_excluded_and_reported(self):
        result = self.full([task(1, None, None), task(2, 550, None), task(3, None, 600)])
        self.assertEqual(len(result["incomplete"]), 3)
        self.assertEqual(result["rest"], 480)
        self.assertEqual(result["covered"], 0)

    def test_today_counts_only_elapsed_work_time(self):
        now = dt.datetime(2026, 11, 17, 10, 30)
        result = summary([task(1, 540, 720)], DAY, now)
        self.assertEqual(result["elapsed"], 90)
        self.assertEqual(result["covered"], 90)
        self.assertEqual(result["rest"], 0)

    def test_before_work_and_future_have_no_elapsed_time(self):
        self.assertEqual(summary([], DAY, dt.datetime(2026, 11, 17, 8))["elapsed"], 0)
        self.assertEqual(summary([], DAY, dt.datetime(2026, 11, 16, 18))["elapsed"], 0)

    def test_past_day_and_full_report_have_whole_workday(self):
        self.assertEqual(summary([], DAY, dt.datetime(2026, 11, 18, 8))["rest"], 480)
        self.assertEqual(self.full([])["rest"], 480)

    def test_fractional_allocation_still_conserves_time(self):
        result = self.full([
            task(1, 540, 541), task(2, 540, 541, CATEGORIES[1]),
            task(3, 540, 541, CATEGORIES[2])])
        self.assertAlmostEqual(sum(result["totals"].values()), 480)

    def test_custom_categories_share_overlap_and_include_incomplete_tasks(self):
        result = self.full([task(1, 540, 660, "项目开发"),
                            task(2, 600, 720, "邮件跟进"),
                            task(3, None, None, "计划")])
        self.assertEqual(result["totals"]["项目开发"], 90)
        self.assertEqual(result["totals"]["邮件跟进"], 90)
        self.assertEqual(result["totals"]["计划"], 0)
        self.assertEqual(result["raw"]["项目开发"], 120)
        self.assertAlmostEqual(sum(result["totals"].values()), 480)

    def test_running_task_is_provisional_and_shares_overlap_without_writing_stop(self):
        running = task(2, 13 * 60 + 13, None, "项目开发")
        rows = [task(1, 13 * 60, 13 * 60 + 20), running, task(3, None, None)]
        result = summary(rows, DAY, now=dt.datetime(2026, 11, 17, 13, 30))
        self.assertEqual((result["covered"], result["rest"], result["overlap"]), (30, 240, 7))
        self.assertEqual(result["task_total"], 37)
        self.assertEqual(result["totals"]["项目开发"], 13.5)
        self.assertEqual(len(result["in_progress"]), 1)
        self.assertEqual(len(result["incomplete"]), 1)
        self.assertIsNone(running["stop"])
        later = summary(rows, DAY, now=dt.datetime(2026, 11, 17, 13, 35))
        self.assertEqual(later["covered"], 35)
        self.assertEqual(later["totals"]["项目开发"], 18.5)

    def test_running_tasks_clip_at_workday_boundary_and_future_starts_do_not_count(self):
        rows = [task(1, 16 * 60 + 30, None), task(2, 19 * 60, None)]
        result = summary(rows, DAY, now=dt.datetime(2026, 11, 17, 18), full_day=True)
        self.assertEqual(result["covered"], 30)
        self.assertEqual(result["rest"], 450)
        self.assertEqual(len(result["in_progress"]), 1)
        self.assertEqual(len(result["incomplete"]), 1)
        self.assertAlmostEqual(sum(result["totals"].values()), 480)


class ValidationTests(unittest.TestCase):
    def test_parse_time_and_blank(self):
        self.assertEqual(parse_time(" 9:05 "), 545)
        self.assertIsNone(parse_time(""))
        self.assertEqual(clock(545), "09:05")
        for value in ("24:00", "12:60", "09:2", "-1:00", "text", "9", "9:05:00"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_time(value)

    def test_invalid_task_values(self):
        for name, category, start, stop in (
                (" ", CATEGORIES[0], None, None),
                ("A", "", 540, 600),
                ("A", REST, 540, 600),
                ("A", "x" * 41, 540, 600),
                ("A", "invalid\ncategory", 540, 600),
                ("A", CATEGORIES[0], 600, 600),
                ("A", CATEGORIES[0], 700, 600),
                ("A", CATEGORIES[0], -1, 600),
                ("A", CATEGORIES[0], 1.5, 600),
                ("A", CATEGORIES[0], 540, 1440)):
            with self.subTest(values=(name, category, start, stop)), self.assertRaises(ValueError):
                validate_task(DAY, name, category, start, stop)

    def test_single_recipient_only(self):
        self.assertEqual(validate_email(" sample@example.com "), "sample@example.com")
        for address in ("x", "a@b", "a@example.com;b@example.com", "a@example.com\nBcc:x@x.com"):
            with self.subTest(address=address), self.assertRaises(ValueError):
                validate_email(address)

    def test_due_days_weekends_cutoff_and_catchup(self):
        self.assertEqual(due_days(DAY, dt.datetime(2026, 11, 17, 16, 59)), [])
        self.assertEqual(due_days(DAY, dt.datetime(2026, 11, 17, 17)), [DAY])
        self.assertEqual(due_days("2026-11-13", dt.datetime(2026, 11, 16, 8)),
                         ["2026-11-13"])
        self.assertEqual(due_days(DAY, dt.datetime(2026, 11, 18, 18)),
                         [DAY, "2026-11-18"])


class StorageAndMailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "ledger.sqlite3")
        self.store.set(recipient="sample@example.com", installed_on=DAY, email_enabled="1")

    def tearDown(self):
        self.temp.cleanup()

    def test_roundtrip_updates_overlap_and_delete(self):
        identity = self.store.save(DAY, " first ", CATEGORIES[0], None, None)
        self.store.save(DAY, "edited", CATEGORIES[1], 540, 600, identity)
        self.store.save(DAY, "overlap", CATEGORIES[2], 550, 590)
        reopened = Store(self.store.path)
        self.assertEqual(len(reopened.tasks(DAY)), 2)
        self.assertEqual(reopened.tasks(DAY)[0]["name"], "edited")
        reopened.delete(identity)
        self.assertEqual(len(self.store.tasks(DAY)), 1)
        self.assertEqual(self.store.tasks("2026-11-18"), [])

    def test_custom_categories_persist_and_deduplicate_after_task_deletion(self):
        identity = self.store.save(DAY, "A", " 项目开发 ", 540, 600)
        self.store.save(DAY, "B", "项目开发", 600, 660)
        self.assertEqual(self.store.tasks(DAY)[0]["category"], "项目开发")
        self.store.delete(identity)
        reopened = Store(self.store.path)
        self.assertEqual(reopened.categories().count("项目开发"), 1)
        self.assertTrue(set(CATEGORIES).issubset(reopened.categories()))
        reopened.delete(reopened.tasks(DAY)[0]["id"])
        self.assertIn("项目开发", Store(self.store.path).categories())

    def test_add_category_without_task_persists_and_rejects_action_label(self):
        self.assertEqual(self.store.add_category(" 项目开发 "), "项目开发")
        self.store.add_category("项目开发")
        self.assertEqual(Store(self.store.path).categories().count("项目开发"), 1)
        self.assertEqual(self.store.tasks(DAY), [])
        with self.assertRaises(ValueError):
            self.store.add_category(CATEGORY_ADD_OPTION)

    def test_category_migration_preserves_existing_tasks(self):
        with self.store.connect() as db:
            db.execute("DROP TABLE categories")
            db.execute("INSERT INTO tasks(day,name,category,start,stop) VALUES(?,?,?,?,?)",
                       (DAY, "Existing task", "旧分类", 540, 600))
        reopened = Store(self.store.path)
        self.assertIn("旧分类", reopened.categories())
        self.assertEqual(reopened.tasks(DAY)[0]["name"], "Existing task")

    def test_custom_category_report_contains_escaped_label_and_stable_color(self):
        category = "<b>开发</b>"
        self.store.save(DAY, "Custom task", category, 540, 600)
        folder, result = report.generate(self.store, DAY, full_day=True)
        body = (folder / "email.html").read_text(encoding="utf-8")
        self.assertIn("&lt;b&gt;开发&lt;/b&gt;", body)
        self.assertNotIn(category, body)
        self.assertEqual(result["totals"][category], 60)
        self.assertIn(category_color(category), body)
        actual = subprocess.check_output(
            [sys.executable, "-c",
             "from core import category_color; print(category_color('<b>开发</b>'))"],
            cwd=Path(report.__file__).parent).decode().strip()
        self.assertEqual(actual, category_color(category))

    def test_claim_serializes_concurrent_senders(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.store.claim(DAY), range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.store.finish(DAY, "failed")
        self.assertTrue(self.store.claim(DAY))
        self.store.finish(DAY, "uncertain")
        self.assertFalse(self.store.claim(DAY))

    @patch("report.outlook")
    def test_successful_send_is_not_repeated(self, outlook):
        outlook.return_value = subprocess.CompletedProcess([], 0, b"queued", b"")
        self.assertEqual(report.send_day(self.store, DAY), "queued")
        self.assertEqual(report.send_day(self.store, DAY), "already-processed")
        self.assertEqual(outlook.call_count, 1)
        self.assertEqual(self.store.delivery(DAY)["status"], "queued")
        payload = json.loads(Path(outlook.call_args.args[0]).read_text(encoding="utf-8"))
        self.assertEqual(payload["recipient"], "sample@example.com")
        self.assertIn("cid:dayledger-chart", Path(payload["body"]).read_text(encoding="utf-8"))

    @patch("report.outlook")
    def test_pre_send_failure_can_retry(self, outlook):
        outlook.return_value = subprocess.CompletedProcess([], 2, b"", b"not available")
        with self.assertRaises(RuntimeError):
            report.send_day(self.store, DAY)
        self.assertEqual(self.store.delivery(DAY)["status"], "failed")
        outlook.return_value = subprocess.CompletedProcess([], 0, b"queued", b"")
        report.send_day(self.store, DAY)
        self.assertEqual(self.store.delivery(DAY)["status"], "queued")

    @patch("report.outlook", side_effect=subprocess.TimeoutExpired("outlook", 100))
    def test_ambiguous_handoff_blocks_duplicate(self, outlook):
        with self.assertRaises(subprocess.TimeoutExpired):
            report.send_day(self.store, DAY)
        self.assertEqual(self.store.delivery(DAY)["status"], "uncertain")
        self.assertEqual(report.send_day(self.store, DAY), "already-processed")
        self.assertEqual(outlook.call_count, 1)

    @patch("report.outlook")
    def test_verify_does_not_consume_daily_delivery(self, outlook):
        outlook.return_value = subprocess.CompletedProcess([], 0, b"verified", b"")
        report.send_day(self.store, DAY, verify=True)
        self.assertIsNone(self.store.delivery(DAY))
        self.assertEqual(outlook.call_args.args[1], "Verify")

    @patch("report.send_day")
    def test_due_runner_respects_pause_and_cutoff(self, sender):
        report.run_due(self.store, dt.datetime(2026, 11, 17, 16))
        sender.assert_not_called()
        report.run_due(self.store, dt.datetime(2026, 11, 17, 17))
        sender.assert_called_once_with(self.store, DAY)
        sender.reset_mock()
        self.store.set(email_enabled="0")
        report.run_due(self.store, dt.datetime(2026, 11, 18, 18))
        sender.assert_not_called()

    def test_report_escapes_names_and_creates_valid_png(self):
        self.store.save(DAY, '<script>alert("x")</script>', CATEGORIES[0], 540, 600)
        folder, result = report.generate(self.store, DAY, full_day=True)
        body = (folder / "summary.html").read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;", body)
        self.assertNotIn("<script>", body)
        self.assertIn("file:", body)
        image = (folder / "time-distribution.png").read_bytes()
        self.assertEqual(image[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", image[16:24]), (360, 360))
        offset, data = 8, bytearray()
        while offset < len(image):
            length = struct.unpack(">I", image[offset:offset + 4])[0]
            kind = image[offset + 4:offset + 8]
            chunk = image[offset + 8:offset + 8 + length]
            crc = struct.unpack(">I", image[offset + 8 + length:offset + 12 + length])[0]
            self.assertEqual(zlib.crc32(kind + chunk) & 0xffffffff, crc)
            if kind == b"IDAT":
                data.extend(chunk)
            offset += 12 + length
        self.assertEqual(len(zlib.decompress(data)), 360 * (360 * 3 + 1))
        self.assertEqual(result["elapsed"], 480)

    def test_live_preview_rereads_tasks_and_time_without_caching_or_setting_stop(self):
        identity = self.store.save(DAY, "Running task", CATEGORIES[0], 13 * 60 + 13, None)
        current = [dt.datetime(2026, 11, 17, 13, 20)]
        snapshot = self.store.tasks(DAY)
        with patch("report.summary", side_effect=lambda rows, day: summary(rows, day, now=current[0])):
            preview = report.LivePreview(self.store)
            try:
                self.assertEqual(preview.server.server_address[0], "127.0.0.1")
                with urlopen(preview.url(DAY), timeout=5) as response:
                    first = response.read().decode("utf-8")
                    self.assertIn("no-store", response.headers["Cache-Control"])
                self.assertIn('http-equiv="refresh" content="15"', first)
                self.assertIn("2026-11-17 13:20:00", first)
                self.assertIn("7 分钟（暂计）", first)
                self.assertIn("data:image/png;base64,", first)
                self.assertEqual(self.store.tasks(DAY), snapshot)
                self.store.save(DAY, "Renamed task", CATEGORIES[1], 13 * 60 + 13, None, identity)
                current[0] = dt.datetime(2026, 11, 17, 13, 25)
                with urlopen(preview.url(DAY), timeout=5) as response:
                    second = response.read().decode("utf-8")
                self.assertIn("Renamed task", second)
                self.assertNotIn("Running task", second)
                self.assertIn("2026-11-17 13:25:00", second)
                self.assertIn("12 分钟（暂计）", second)
                self.assertIsNone(self.store.tasks(DAY)[0]["stop"])
            finally:
                preview.close()
        self.assertFalse(preview.thread.is_alive())
        with self.assertRaises(URLError):
            urlopen(preview.url(DAY), timeout=1)

    def test_live_preview_rejects_unknown_urls_and_email_remains_a_snapshot(self):
        preview = report.LivePreview(self.store)
        try:
            for url in (preview.url(DAY).replace(preview.token, "incorrect"),
                        preview.url(DAY).replace(DAY, "not-a-date")):
                with self.subTest(url=url), self.assertRaises(HTTPError) as error:
                    urlopen(url, timeout=5)
                self.assertEqual(error.exception.code, 404)
        finally:
            preview.close()
        folder, _ = report.generate(self.store, DAY, full_day=True)
        body = (folder / "email.html").read_text(encoding="utf-8")
        self.assertNotIn('http-equiv="refresh"', body)
        self.assertIn("cid:dayledger-chart", body)


if __name__ == "__main__":
    unittest.main()
