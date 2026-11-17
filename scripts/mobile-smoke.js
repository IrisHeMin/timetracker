async (page) => {
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.setViewportSize({width: 390, height: 844});
  const base = await page.evaluate(() => location.origin);
  const engine = await page.evaluate(() => navigator.userAgent.includes("Chrome") ? "chromium" : "webkit");
  const day = await page.evaluate(() => DayLedger.dayKey());
  const name = "手机端长任务名称与不间断内容".repeat(12);
  const category = "自定义分类名称".repeat(5);
  const checkLayout = async label => {
    const problems = await page.evaluate(viewport => {
      const failures = [];
      if (document.documentElement.scrollWidth > viewport.width + 1) failures.push("page overflows");
      const dialog = [...document.querySelectorAll("dialog[open]")].at(-1);
      const root = dialog || document;
      if (dialog && (dialog.scrollWidth > dialog.clientWidth + 1 ||
          dialog.getBoundingClientRect().height > viewport.height - 16)) failures.push("dialog overflows");
      for (const element of root.querySelectorAll("button,input:not([hidden]),select,.button,canvas,img,.entry-table td")) {
        const box = element.getBoundingClientRect();
        if (!box.width || !box.height || !element.getClientRects().length) continue;
        if (box.left < -1 || box.right > viewport.width + 1) failures.push(`${element.tagName} outside viewport`);
        if (element.matches("button,input,select,.button") && box.height < 43) failures.push("small touch target");
        if (element.matches("input,select") && parseFloat(getComputedStyle(element).fontSize) < 16) failures.push("small input font");
      }
      return failures;
    }, page.viewportSize());
    if (problems.length) throw Error(`${label}: ${problems.join(", ")}`);
  };
  await page.evaluate(() => localStorage.removeItem("dayledger.web.v1"));
  await page.reload();
  await checkLayout("empty phone");
  await page.locator("#add-task").tap();
  await page.locator("#task-name").fill(name);
  await page.locator("#task-category").selectOption("＋ 添加分类…");
  await page.locator("#category-name").fill(category);
  await checkLayout("nested category dialog");
  await page.getByRole("button", {name: "保存分类", exact: true}).tap();
  await page.locator("#task-start").fill("09:00");
  await page.locator("#task-stop").fill("10:00");
  await page.getByRole("button", {name: "保存任务", exact: true}).tap();
  const fixtures = [
    {width: 320, height: 568}, {width: 360, height: 640},
    {width: 375, height: 667}, {width: 390, height: 844},
    {width: 430, height: 932}, {width: 650, height: 900},
    {width: 844, height: 390}, {width: 932, height: 430},
    {width: 768, height: 1024}, {width: 1024, height: 768}
  ];
  for (const viewport of fixtures) {
    await page.setViewportSize(viewport);
    await page.locator("#today").tap();
    await checkLayout(`${viewport.width}px task list`);
    if (viewport.width <= 1050) {
      const table = page.locator("#tasks");
      if (await table.evaluate(element => element.scrollWidth > element.clientWidth + 1))
        throw Error("Task cards require horizontal scrolling");
      await table.getByRole("button", {name, exact: true}).tap();
      await checkLayout(`${viewport.width}px edit dialog`);
      await page.locator('#task-dialog [data-close]').tap();
    }
    await page.locator("#preview").tap();
    await checkLayout(`${viewport.width}px report`);
    await page.locator('#report-dialog [data-close]').tap();
  }
  await page.setViewportSize({width: 390, height: 844});
  const row = page.locator("#tasks tr").first();
  await row.locator('input[type="time"]').nth(1).fill("10:30");
  await row.locator('input[type="time"]').nth(1).dispatchEvent("change");
  if (!await row.locator(".duration").innerText().then(text => text.includes("1 小时 30 分")))
    throw Error("Mobile inline time edit failed");
  await row.locator("select").selectOption("＋ 添加分类…");
  await page.locator("#category-name").fill("手机保存分类");
  await page.getByRole("button", {name: "保存分类", exact: true}).tap();
  if (await row.locator("select").inputValue() !== "手机保存分类") throw Error("Inline category failed");
  await page.locator("#theme").tap();
  await checkLayout("alternate theme");
  await page.locator("#tasks tr").first().getByRole("button", {name, exact: true}).tap();
  await page.locator("#task-name").fill("手机任务 · 编辑时间与分类");
  await page.getByRole("button", {name: "保存任务", exact: true}).tap();
  await page.screenshot({path: `.playwright-cli\\dayledger-phone-${engine}.png`, fullPage: true});
  await page.locator("#preview").tap();
  const downloadEvent = page.waitForEvent("download");
  await page.locator("#save-report").tap();
  const download = await downloadEvent;
  const reportName = `mobile-report-${engine}.html`;
  const reportPath = `.playwright-cli\\${reportName}`;
  await download.saveAs(reportPath);
  await page.locator('#report-dialog [data-close]').tap();
  const reportResponse = await page.goto(`${base}/.playwright-cli/${reportName}`);
  if (!reportResponse.ok() || await page.locator("img").count() !== 1) throw Error("Downloaded report did not load");
  await checkLayout("downloaded mobile report");
  await page.goto(`${base}/dist/DayLedger-offline.html`);
  if (await page.locator("script[src]").count()) throw Error("Offline file uses external scripts");
  await page.context().setOffline(true);
  await page.locator("#day").fill(day);
  await page.locator("#day").dispatchEvent("change");
  await checkLayout("offline phone");
  await page.locator("#add-task").tap();
  await page.locator("#task-name").fill("手机离线任务");
  await page.getByRole("button", {name: "保存任务", exact: true}).tap();
  if (!await page.locator("#tasks").innerText().then(text => text.includes("手机离线任务")))
    throw Error("Offline mobile save failed");
  await page.context().setOffline(false);
  await page.reload();
  if (!await page.locator("#tasks").innerText().then(text => text.includes("手机离线任务")))
    throw Error("Mobile task did not persist");
  await page.setViewportSize({width: 1440, height: 1000});
  if (await page.locator("#tasks tr").first().evaluate(element => getComputedStyle(element).display) !== "table-row")
    throw Error("Desktop table layout regressed");
  await page.screenshot({path: `.playwright-cli\\dayledger-desktop-${engine}.png`, fullPage: true});
  if (errors.length) throw Error(errors.join("\n"));
  return {result: "passed", widths: fixtures.map(item => item.width), touchEditing: true,
    categoryCreation: true, reportDownload: true, offline: true, desktopTable: true};
}
