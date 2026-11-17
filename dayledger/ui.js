/* Browser data never leaves this device; downloads are user-initiated. */
(() => {
  "use strict";
  const L = window.DayLedger, $ = id => document.getElementById(id);
  const KEY = "dayledger.web.v1";
  let state = L.empty(), editing = null, categoryTarget = null, storageReady = false;
  const colors = ["--cp-accent", "--cp-link", "--cp-success", "--cp-warning",
    "--cp-danger", "--cp-text-soft", "--cp-accent-hover", "--cp-border-strong"];
  const node = (tag, text, className) => {
    const result = document.createElement(tag);
    if (text !== undefined) result.textContent = text;
    if (className) result.className = className;
    return result;
  };
  function message(text, error = false) {
    $("message").textContent = text;
    $("message").className = error ? "error" : "muted small";
  }
  function read() {
    const saved = localStorage.getItem(KEY);
    return saved ? L.data(JSON.parse(saved)) : L.empty();
  }
  function mutate(action) {
    if (!storageReady) throw Error("浏览器存储不可用，未保存。请检查浏览器设置后重新打开页面。");
    const fresh = read();
    action(fresh);
    const validated = L.data(fresh);
    localStorage.setItem(KEY, JSON.stringify(validated));
    state = validated;
    render();
    message("已保存到当前浏览器。");
  }
  function attempt(action) {
    try { action(); } catch (error) { message(error.message, true); render(); }
  }
  function categoryOptions(select, selected) {
    select.replaceChildren();
    [...state.categories, L.ADD].forEach(name => select.add(new Option(name, name)));
    select.value = state.categories.includes(selected) ? selected : state.categories[0];
    select.dataset.previous = select.value;
  }
  function chooseCategory(select, previous, apply) {
    if (select.value !== L.ADD) { select.dataset.previous = select.value; apply(select.value); return; }
    select.value = previous;
    categoryTarget = apply;
    $("category-name").value = "";
    $("category-error").textContent = "";
    $("category-dialog").showModal();
    $("category-name").focus();
  }
  function rows() {
    return state.tasks.filter(row => row.day === $("day").value)
      .sort((a, b) => (a.start ?? 1440) - (b.start ?? 1440));
  }
  function updateTask(id, changes) {
    mutate(data => {
      const index = data.tasks.findIndex(row => row.id === id);
      if (index < 0) throw Error("任务已被其他窗口删除，请刷新后重试。");
      data.tasks[index] = L.task({...data.tasks[index], ...changes});
    });
  }
  function spent(row, result, now = new Date()) {
    if (row.start !== null && row.stop !== null) return L.duration(row.stop - row.start);
    return result.active.has(row.id) ?
      `${L.duration(now.getHours() * 60 + now.getMinutes() - row.start)} · 进行中` : "待补全";
  }
  function colorName(category) {
    if (category === L.REST) return "--cp-border";
    let hash = 0;
    for (const char of category) hash = (hash * 31 + char.codePointAt(0)) >>> 0;
    const index = L.categories.indexOf(category);
    return colors[index < 0 ? hash % colors.length : index];
  }
  function draw(result) {
    const canvas = $("chart"), context = canvas.getContext("2d");
    const styles = getComputedStyle(document.documentElement);
    const color = name => styles.getPropertyValue(name).trim();
    context.clearRect(0, 0, 512, 512);
    let angle = -Math.PI / 2;
    context.lineWidth = 68;
    if (!result.elapsed) {
      context.strokeStyle = color("--cp-border");
      context.beginPath(); context.arc(256, 256, 190, 0, Math.PI * 2); context.stroke();
    }
    $("legend").replaceChildren();
    for (const [category, minutes] of result.totals) {
      const end = angle + (result.elapsed ? minutes / result.elapsed * Math.PI * 2 : 0);
      if (minutes > 0) {
        context.strokeStyle = color(colorName(category));
        context.beginPath(); context.arc(256, 256, 190, angle, end); context.stroke();
      }
      angle = end;
      const line = node("div", undefined, "legend-row");
      const dot = node("span", undefined, "dot");
      dot.style.background = `var(${colorName(category)})`;
      line.append(dot, node("span", category, "name"),
        node("span", `${L.duration(minutes)} · ${result.elapsed ? Math.round(minutes / result.elapsed * 100) : 0}%`, "small muted"));
      $("legend").append(line);
    }
    context.textAlign = "center";
    context.fillStyle = color("--cp-text");
    context.font = 'bold 38px "Segoe UI", sans-serif';
    context.fillText(L.duration(result.elapsed), 256, 255);
    context.fillStyle = color("--cp-text-muted");
    context.font = '24px "Segoe UI", sans-serif';
    context.fillText("已过工作时间", 256, 295);
  }
  function render() {
    const now = new Date(), day = $("day").value;
    if (!L.validDay(day)) return;
    const result = L.summarize(state.tasks, day, now);
    $("covered").textContent = L.duration(result.covered);
    $("rest").textContent = L.duration(result.rest);
    $("overlap").textContent = L.duration(result.overlap);
    $("count").textContent = `${rows().length} 项`;
    $("interval").textContent = `09:00–17:00 · 统计至 ${L.clock(result.end)} · ${result.active.size} 项进行中`;
    const body = $("tasks");
    body.replaceChildren();
    if (!rows().length) {
      const cell = node("td", "还没有任务。先添加计划，再选择开始和结束时间。", "empty");
      cell.colSpan = 6;
      const row = node("tr"); row.append(cell); body.append(row);
    }
    rows().forEach(row => {
      const tr = node("tr");
      const name = node("button", row.name, "task-name");
      name.onclick = () => openTask(row);
      const category = node("select");
      category.setAttribute("aria-label", `${row.name} 分类`);
      categoryOptions(category, row.category);
      category.onchange = () => attempt(() => chooseCategory(category, row.category,
        value => updateTask(row.id, {category: value})));
      const times = ["start", "stop"].map(key => {
        const input = node("input"); input.type = "time"; input.step = "60";
        input.value = L.clock(row[key]);
        input.setAttribute("aria-label", `${row.name} ${key}`);
        input.onchange = () => attempt(() => updateTask(row.id, {[key]: L.parseTime(input.value)}));
        return input;
      });
      const actions = node("div", undefined, "toolbar");
      for (const [label, key] of [["▶", "start"], ["■", "stop"]]) {
        const button = node("button", label, "icon");
        button.title = key === "start" ? "Start 现在" : "Stop 现在";
        button.setAttribute("aria-label", `${row.name} ${button.title}`);
        button.disabled = day !== L.dayKey();
        button.onclick = () => attempt(() => {
          const current = new Date();
          updateTask(row.id, {[key]: current.getHours() * 60 + current.getMinutes()});
        });
        actions.append(button);
      }
      const remove = node("button", "删除", "icon danger");
      remove.onclick = () => {
        if (confirm(`删除「${row.name}」？`)) attempt(() => mutate(data => {
          data.tasks = data.tasks.filter(item => item.id !== row.id);
        }));
      };
      actions.append(remove);
      for (const child of [name, category, ...times, node("span", spent(row, result, now), "duration"), actions]) {
        const cell = node("td"); cell.append(child); tr.append(cell);
      }
      body.append(tr);
    });
    const selection = $("task-category").value;
    categoryOptions($("task-category"), selection);
    draw(result);
    if ($("report-dialog").open) report(result, now);
  }
  function openTask(row = null) {
    editing = row?.id || null;
    $("task-title").textContent = row ? "编辑任务" : "添加任务";
    $("task-name").value = row?.name || "";
    categoryOptions($("task-category"), row?.category || state.categories[0]);
    $("task-start").value = L.clock(row?.start ?? null);
    $("task-stop").value = L.clock(row?.stop ?? null);
    $("task-error").textContent = "";
    $("task-dialog").showModal(); $("task-name").focus();
  }
  function report(result, now) {
    const content = $("report-content"); content.replaceChildren();
    content.append(node("h2", `${$("day").value} · 每日时间开销`),
      node("p", `更新于 ${now.toLocaleString()} · 09:00–${L.clock(result.end)} · 每 15 秒更新`, "muted"));
    const chart = node("div", undefined, "report-chart"), image = node("img");
    image.src = $("chart").toDataURL("image/png"); image.alt = "时间分布饼图";
    const legend = $("legend").cloneNode(true);
    legend.removeAttribute("id");
    chart.append(image, legend); content.append(chart);
    content.append(node("p", `已记录 ${L.duration(result.covered)}；休息 / 未记录 ${L.duration(result.rest)}；重叠时段 ${L.duration(result.overlap)}。`, "muted"));
    const table = node("table"), head = node("tr");
    ["任务", "分类", "Start", "Stop", "原始时长"].forEach(text => head.append(node("th", text)));
    table.append(head);
    rows().forEach(row => {
      const line = node("tr");
      [row.name, row.category, L.clock(row.start), result.active.has(row.id) ? "进行中" : L.clock(row.stop),
        spent(row, result, now)].forEach(text => line.append(node("td", text)));
      table.append(line);
    });
    const wrap = node("div", undefined, "table-wrap"); wrap.append(table); content.append(wrap);
    content.append(node("p", "饼图按实际经过时间平分重叠时段。进行中任务暂计到现在，不自动修改 Stop。区间外时间不计入饼图。", "muted small"));
  }
  function download(name, content, type) {
    const url = URL.createObjectURL(new Blob([content], {type}));
    const link = node("a"); link.href = url; link.download = name; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }
  $("day").value = L.dayKey();
  try { state = read(); storageReady = true; }
  catch { message("无法读取浏览器存储，可能是备份损坏或浏览器禁止存储。请先保留原始数据，不要清除浏览器记录。", true); }
  $("day").onchange = render;
  const shift = amount => {
    const date = new Date(`${$("day").value}T12:00:00`);
    date.setDate(date.getDate() + amount); $("day").value = L.dayKey(date); render();
  };
  $("previous").onclick = () => shift(-1); $("next").onclick = () => shift(1);
  $("today").onclick = () => { $("day").value = L.dayKey(); render(); };
  $("add-task").onclick = () => openTask();
  document.querySelectorAll("[data-close]").forEach(button => button.onclick = () => $(button.dataset.close).close());
  $("task-category").onchange = () => attempt(() => chooseCategory($("task-category"),
    $("task-category").dataset.previous, value => {
      $("task-category").value = value; $("task-category").dataset.previous = value;
    }));
  $("category-form").onsubmit = event => {
    event.preventDefault();
    try {
      const name = L.categoryName($("category-name").value);
      const apply = categoryTarget;
      mutate(data => { if (!data.categories.includes(name)) data.categories.push(name); });
      $("category-dialog").close(); categoryTarget = null;
      if (apply) apply(name);
    } catch (error) { $("category-error").textContent = error.message; }
  };
  $("task-form").onsubmit = event => {
    event.preventDefault();
    try {
      const value = L.task({id: editing || (crypto.randomUUID ? crypto.randomUUID() :
        `${Date.now()}-${Math.random().toString(36).slice(2)}`),
        day: $("day").value, name: $("task-name").value, category: $("task-category").value,
        start: L.parseTime($("task-start").value), stop: L.parseTime($("task-stop").value)});
      mutate(data => {
        if (editing) {
          const index = data.tasks.findIndex(row => row.id === editing);
          if (index < 0) throw Error("任务已被删除，请关闭后重新添加。");
          data.tasks[index] = value;
        } else data.tasks.push(value);
      });
      $("task-dialog").close();
    } catch (error) { $("task-error").textContent = error.message; }
  };
  $("preview").onclick = () => { $("report-dialog").showModal(); render(); };
  $("theme").onclick = () => {
    document.documentElement.dataset.theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    render();
  };
  $("export-json").onclick = () => attempt(() => download(`DayLedger-${L.dayKey()}.json`,
    JSON.stringify(read(), null, 2), "application/json"));
  $("import-json").onclick = () => $("import-file").click();
  $("import-file").onchange = async event => {
    const file = event.target.files[0]; if (!file) return;
    try {
      if (file.size > 20000000) throw Error("备份文件不能超过 20 MB。");
      const imported = L.data(JSON.parse(await file.text()));
      if (!confirm(`导入 ${imported.tasks.length} 项任务？同 ID 记录以备份为准，其余现有记录保留。`)) return;
      mutate(data => {
        const combined = new Map(data.tasks.map(row => [row.id, row]));
        imported.tasks.forEach(row => combined.set(row.id, row));
        data.tasks = [...combined.values()];
        data.categories = [...new Set([...data.categories, ...imported.categories])];
      });
    } catch (error) { message(error.message, true); }
    finally { event.target.value = ""; }
  };
  $("export-csv").onclick = () => {
    const escape = value => {
      let text = String(value); if (/^\s*[=+\-@]/.test(text)) text = "'" + text;
      return `"${text.replaceAll('"', '""')}"`;
    };
    const lines = [["日期", "任务", "分类", "Start", "Stop", "原始分钟数"], ...rows().map(row =>
      [row.day, row.name, row.category, L.clock(row.start), L.clock(row.stop),
        row.start !== null && row.stop !== null ? row.stop - row.start : ""])];
    download(`DayLedger-${$("day").value}.csv`, "\ufeff" + lines.map(line => line.map(escape).join(",")).join("\r\n"), "text/csv;charset=utf-8");
  };
  $("save-report").onclick = () => {
    render();
    const style = document.querySelector("style").textContent;
    const theme = document.querySelector("[data-theme-detect]").textContent;
    download(`DayLedger-report-${$("day").value}.html`,
      `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><script>${theme}</` +
      `script><meta name="viewport" content="width=device-width,initial-scale=1"><title>每日时间账本</title><style>${style}</style></head><body><main class="card">${$("report-content").innerHTML}<p class="muted small">这是导出时的静态快照，不会自动更新。</p></main></body></html>`,
      "text/html;charset=utf-8");
  };
  window.addEventListener("storage", event => {
    if (event.key === KEY) attempt(() => { state = read(); render(); });
  });
  setInterval(() => {
    if (!$("task-dialog").open && !$("category-dialog").open &&
        !["INPUT", "SELECT"].includes(document.activeElement.tagName)) render();
  }, 15000);
  render();
})();
