"""Focused native-widget tests. Run in an interactive Windows session."""

import datetime as dt
import ctypes
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.request import urlopen

from app import App, CategorySelector, TimeSelector
from core import CATEGORIES, CATEGORY_ADD_OPTION, Store


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ctypes.windll.shcore.SetProcessDpiAwareness(1)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "ledger.sqlite3")
        self.day = dt.date.today().isoformat()
        self.identity = self.store.save(self.day, "Sample case", CATEGORIES[0], 540, 600)
        self.root = tk.Tk()
        self.app = App(self.root, self.store)
        self.root.update()
        self.root.focus_force()
        self.root.update()

    def tearDown(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.app.close()
        self.temp.cleanup()

    def edit(self, column, value, combo=False):
        item = str(self.identity)
        self.app.table.selection_set(item)
        box = self.app.table.bbox(item, column)
        self.app.edit_cell(SimpleNamespace(x=box[0] + 10, y=box[1] + 10))
        self.root.update()
        widget = self.app.editor
        self.assertIsNotNone(widget)
        if isinstance(widget, tk.Toplevel):
            frame = widget.winfo_children()[0]
            selector = next(child for child in frame.winfo_children()
                            if isinstance(child, TimeSelector))
            self.assertEqual(str(selector.hours.cget("state")), "readonly")
            self.assertEqual(str(selector.minutes.cget("state")), "readonly")
            hour, minute = value.split(":")
            selector.hours.set(hour)
            selector.hours.event_generate("<<ComboboxSelected>>")
            selector.minutes.set(minute)
            selector.minutes.event_generate("<<ComboboxSelected>>")
            buttons = frame.winfo_children()[-1]
            save = next(child for child in buttons.winfo_children()
                        if child.cget("text") == "确定")
            save.invoke()
        elif isinstance(widget, CategorySelector) and not combo:
            self.add_category(widget, value)
        elif combo:
            widget.set(value)
            widget.event_generate("<<ComboboxSelected>>")
        else:
            widget.delete(0, "end")
            widget.insert(0, value)
            widget.event_generate("<Return>")
        self.root.update()

    def add_category(self, selector, name):
        selector.set(CATEGORY_ADD_OPTION)
        selector.event_generate("<<ComboboxSelected>>")
        self.root.update()
        dialog = selector.add_dialog
        self.assertIsNotNone(dialog)
        frame = dialog.winfo_children()[0]
        entry = next(child for child in frame.winfo_children() if type(child) is ttk.Entry)
        entry.insert(0, name)
        buttons = frame.winfo_children()[-1]
        next(child for child in buttons.winfo_children()
             if child.cget("text") == "保存分类").invoke()
        self.root.update()
        return dialog

    def test_editable_task_time_and_category_persist(self):
        self.edit("#1", "Updated task")
        self.edit("#3", "09:15")
        self.edit("#4", "10:30")
        self.edit("#2", CATEGORIES[2], combo=True)
        reopened = Store(self.store.path)
        row = reopened.tasks(self.day)[0]
        self.assertEqual((row["name"], row["category"], row["start"], row["stop"]),
                         ("Updated task", CATEGORIES[2], 555, 630))
        self.assertEqual(self.app.table.item(str(self.identity), "values")[-1], "1 小时 15 分")

    def test_invalid_time_is_rejected_without_losing_saved_row(self):
        with patch("app.messagebox.showerror") as error:
            self.edit("#4", "08:00")
            error.assert_called_once()
        self.assertEqual(self.store.tasks(self.day)[0]["stop"], 600)

    def test_add_plan_without_times(self):
        self.app.add_task()
        self.root.update()
        dialog = next(child for child in self.root.winfo_children() if isinstance(child, tk.Toplevel))
        frame = dialog.winfo_children()[0]
        name = next(child for child in frame.winfo_children()
                    if type(child) is ttk.Entry)
        name.insert(0, "Plan for later")
        save = next(child for child in frame.winfo_children() if isinstance(child, ttk.Button))
        save.invoke()
        self.root.update()
        self.assertEqual(len(self.store.tasks(self.day)), 2)
        planned = next(row for row in self.store.tasks(self.day) if row["name"] == "Plan for later")
        self.assertIsNone(planned["start"])
        self.assertIsNone(planned["stop"])

    def test_custom_category_edit_is_saved_and_reusable_in_new_tasks(self):
        self.edit("#2", "项目开发")
        self.assertEqual(self.store.tasks(self.day)[0]["category"], "项目开发")
        self.assertIn("项目开发", self.app.legend_categories)
        self.app.add_task()
        self.root.update()
        dialog = next(child for child in self.root.winfo_children() if isinstance(child, tk.Toplevel))
        frame = dialog.winfo_children()[0]
        category = next(child for child in frame.winfo_children() if isinstance(child, CategorySelector))
        self.assertIn("项目开发", category.cget("values"))
        self.assertEqual(category.cget("values")[-1], CATEGORY_ADD_OPTION)
        name = next(child for child in frame.winfo_children() if type(child) is ttk.Entry)
        name.insert(0, "New category task")
        self.add_category(category, "客户沟通")
        self.assertEqual(category.get(), "客户沟通")
        self.assertIs(self.root.grab_current(), dialog)
        next(child for child in frame.winfo_children() if isinstance(child, ttk.Button)).invoke()
        self.root.update()
        self.assertIn("客户沟通", Store(self.store.path).categories())
        self.assertIn("客户沟通", self.app.legend_categories)

    def test_cancel_or_invalid_add_keeps_existing_task_category(self):
        box = self.app.table.bbox(str(self.identity), "#2")
        self.app.edit_cell(SimpleNamespace(x=box[0] + 10, y=box[1] + 10))
        self.root.update()
        selector = self.app.editor
        with patch("app.messagebox.showerror") as error:
            dialog = self.add_category(selector, " ")
            error.assert_called_once()
        self.assertEqual(self.store.tasks(self.day)[0]["category"], CATEGORIES[0])
        self.assertEqual(selector.get(), CATEGORIES[0])
        frame = dialog.winfo_children()[0]
        buttons = frame.winfo_children()[-1]
        next(child for child in buttons.winfo_children() if child.cget("text") == "取消").invoke()
        self.root.update()
        self.assertIsNone(selector.add_dialog)
        self.assertEqual(selector.get(), CATEGORIES[0])
        self.assertNotIn(CATEGORY_ADD_OPTION, self.store.categories())

    def test_added_category_remains_selected_after_reopening_editor(self):
        self.edit("#2", "项目开发")
        box = self.app.table.bbox(str(self.identity), "#2")
        self.app.edit_cell(SimpleNamespace(x=box[0] + 10, y=box[1] + 10))
        self.root.update()
        self.assertEqual(self.app.editor.get(), "项目开发")
        self.assertIn("项目开发", self.app.editor.cget("values"))
        self.app.close_editor()
        self.edit("#2", CATEGORIES[1], combo=True)
        self.assertEqual(Store(self.store.path).tasks(self.day)[0]["category"], CATEGORIES[1])

    def test_many_custom_categories_use_scrollable_legend(self):
        for index in range(15):
            self.store.save(self.day, f"Task {index}", f"分类 {index}", 540, 600)
        self.app.refresh()
        self.root.update()
        first, last = self.app.legend_canvas.yview()
        self.assertEqual(first, 0)
        self.assertLess(last, 1)
        self.app.legend_canvas.yview_moveto(1)
        self.root.update()
        self.assertEqual(self.app.legend_canvas.yview()[1], 1)

    def test_select_times_in_new_task_dialog(self):
        self.app.add_task()
        self.root.update()
        dialog = next(child for child in self.root.winfo_children() if isinstance(child, tk.Toplevel))
        frame = dialog.winfo_children()[0]
        name = next(child for child in frame.winfo_children() if type(child) is ttk.Entry)
        name.insert(0, "Dropdown task")
        selectors = [child for child in frame.winfo_children() if isinstance(child, TimeSelector)]
        for selector, hour, minute in ((selectors[0], "14", "05"), (selectors[1], "15", "25")):
            selector.hours.set(hour)
            selector.hours.event_generate("<<ComboboxSelected>>")
            selector.minutes.set(minute)
            selector.minutes.event_generate("<<ComboboxSelected>>")
        next(child for child in frame.winfo_children() if isinstance(child, ttk.Button)).invoke()
        self.root.update()
        row = next(row for row in self.store.tasks(self.day) if row["name"] == "Dropdown task")
        self.assertEqual((row["start"], row["stop"]), (845, 925))

    def test_time_picker_clear_cancel_and_single_click(self):
        item = str(self.identity)
        box = self.app.table.bbox(item, "#3")
        self.app.pick_time_cell(SimpleNamespace(x=box[0] + 10, y=box[1] + 10))
        self.root.update()
        dialog = self.app.editor
        frame = dialog.winfo_children()[0]
        selector = next(child for child in frame.winfo_children() if isinstance(child, TimeSelector))
        selector.set("")
        buttons = frame.winfo_children()[-1]
        next(child for child in buttons.winfo_children() if child.cget("text") == "取消").invoke()
        self.assertEqual(self.store.tasks(self.day)[0]["start"], 540)
        self.app.pick_time_cell(SimpleNamespace(x=box[0] + 10, y=box[1] + 10))
        self.root.update()
        frame = self.app.editor.winfo_children()[0]
        selector = next(child for child in frame.winfo_children() if isinstance(child, TimeSelector))
        next(child for child in selector.winfo_children()
             if isinstance(child, ttk.Button) and child.cget("text") == "清空").invoke()
        buttons = frame.winfo_children()[-1]
        next(child for child in buttons.winfo_children() if child.cget("text") == "确定").invoke()
        self.assertIsNone(self.store.tasks(self.day)[0]["start"])
        self.assertEqual(self.store.tasks(self.day)[0]["stop"], 600)

    def test_navigation_and_status_fit_window(self):
        self.app.shift(-1)
        self.root.update()
        self.assertEqual(self.app.rows, [])
        self.app.today()
        self.assertEqual(len(self.app.rows), 1)
        self.assertLessEqual(
            self.app.mail_status.winfo_rooty() + self.app.mail_status.winfo_height(),
            self.root.winfo_rooty() + self.root.winfo_height())
        self.assertLessEqual(
            self.app.legend[-1].winfo_rooty() + self.app.legend[-1].winfo_height(),
            self.root.winfo_rooty() + self.root.winfo_height())

    def test_csv_export_escapes_spreadsheet_formula(self):
        self.store.save(self.day, "=1+1", "=2+2", 600, 660)
        self.app.refresh()
        destination = Path(self.temp.name) / "tasks.csv"
        with patch("app.filedialog.asksaveasfilename", return_value=str(destination)), \
                patch("app.os.startfile"):
            self.app.export()
        contents = destination.read_text(encoding="utf-8-sig")
        self.assertIn("'=1+1", contents)
        self.assertIn("'=2+2", contents)

    def test_preview_uses_current_selected_date_and_reuses_live_service(self):
        with patch("app.os.startfile") as opener:
            self.app.preview()
            first = opener.call_args.args[0]
            self.assertTrue(first.startswith("http://127.0.0.1:"))
            self.store.save(self.day, "Added after opening preview", CATEGORIES[1], 600, 660)
            with urlopen(first, timeout=5) as response:
                self.assertIn("Added after opening preview", response.read().decode("utf-8"))
            server = self.app.preview_server
            self.app.shift(-1)
            self.app.preview()
            self.assertIs(self.app.preview_server, server)
            self.assertTrue(opener.call_args.args[0].endswith(self.app.day.isoformat()))


if __name__ == "__main__":
    unittest.main()
