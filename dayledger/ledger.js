(function (root) {
  "use strict";
  const categories = ["做 case", "学习", "讨论", "健身", "娱乐"];
  const REST = "休息 / 未记录";
  const ADD = "＋ 添加分类…";
  const dayKey = (date = new Date()) =>
    `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  function validDay(day) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return false;
    const date = new Date(`${day}T12:00:00`);
    return !Number.isNaN(+date) && dayKey(date) === day;
  }
  function parseTime(value) {
    if (!value) return null;
    if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value)) throw Error("请选择有效的小时和分钟。");
    const [hour, minute] = value.split(":").map(Number);
    return hour * 60 + minute;
  }
  const clock = (minutes) => minutes == null ? "" :
    `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
  function categoryName(value) {
    if (typeof value !== "string") throw Error("分类名称无效。");
    const name = value.trim();
    if (!name || Array.from(name).length > 40 || /[\u0000-\u001f\u007f]/.test(name) ||
        [REST, ADD, "__proto__", "constructor", "prototype"].includes(name)) {
      throw Error("分类请使用 1–40 个字符，且不能使用系统保留名称。");
    }
    return name;
  }
  function task(value) {
    if (!value || typeof value !== "object" || typeof value.id !== "string" ||
        !value.id || value.id.length > 100 || !validDay(value.day) ||
        typeof value.name !== "string" || !value.name.trim() || value.name.length > 500) {
      throw Error("任务名称或日期无效。");
    }
    for (const time of [value.start, value.stop]) {
      if (time !== null && (!Number.isInteger(time) || time < 0 || time >= 1440)) {
        throw Error("任务时间必须在 00:00–23:59 之间。");
      }
    }
    if (value.start !== null && value.stop !== null && value.stop <= value.start) {
      throw Error("Stop 必须晚于 Start，跨天任务请拆开记录。");
    }
    return {id: value.id, day: value.day, name: value.name.trim(),
      category: categoryName(value.category), start: value.start, stop: value.stop};
  }
  function data(value) {
    if (!value || value.version !== 1 || !Array.isArray(value.tasks) ||
        !Array.isArray(value.categories) || value.tasks.length > 50000 ||
        value.categories.length > 2000) throw Error("备份格式无效或记录数量过多。");
    const tasks = value.tasks.map(task);
    if (new Set(tasks.map(row => row.id)).size !== tasks.length) throw Error("任务 ID 重复。");
    return {version: 1, tasks, categories: [...new Set([
      ...categories, ...value.categories.map(categoryName), ...tasks.map(row => row.category)
    ])]};
  }
  const empty = () => ({version: 1, tasks: [], categories: [...categories]});
  function summarize(tasks, day, now = new Date()) {
    const minute = now.getHours() * 60 + now.getMinutes();
    const today = dayKey(now);
    const end = day < today ? 1020 : day > today ? 540 : Math.min(1020, Math.max(540, minute));
    const totals = new Map(categories.map(name => [name, 0]));
    let taskTotal = 0, covered = 0, rest = 0, overlap = 0;
    const active = new Set(), incomplete = new Set(), intervals = [];
    for (const row of tasks.filter(row => row.day === day)) {
      if (!totals.has(row.category)) totals.set(row.category, 0);
      let stop = row.stop;
      if (row.start === null) { incomplete.add(row.id); continue; }
      if (stop === null) {
        if (day !== today || row.start > minute) { incomplete.add(row.id); continue; }
        stop = minute;
        active.add(row.id);
      }
      const start = Math.max(540, row.start);
      stop = Math.min(end, stop);
      if (stop > start) { intervals.push({start, stop, category: row.category}); taskTotal += stop - start; }
    }
    const points = [...new Set([540, end, ...intervals.flatMap(row => [row.start, row.stop])])].sort((a, b) => a - b);
    for (let i = 1; i < points.length; i++) {
      const start = points[i - 1], stop = points[i], minutes = stop - start;
      const rows = intervals.filter(row => row.start <= start && row.stop >= stop);
      if (!rows.length) rest += minutes;
      else {
        covered += minutes;
        if (rows.length > 1) overlap += minutes;
        rows.forEach(row => totals.set(row.category, totals.get(row.category) + minutes / rows.length));
      }
    }
    totals.set(REST, rest);
    return {totals, active, incomplete, covered, rest, overlap, taskTotal, end, elapsed: end - 540};
  }
  const duration = (minutes) => {
    const value = Math.max(0, Math.round(minutes));
    return value >= 60 ? `${Math.floor(value / 60)} 小时 ${value % 60} 分` : `${value} 分钟`;
  };
  const api = {categories, REST, ADD, dayKey, validDay, parseTime, clock, categoryName, task, data, empty, summarize, duration};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.DayLedger = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
