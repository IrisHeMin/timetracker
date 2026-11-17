const test = require("node:test");
const assert = require("node:assert/strict");
const L = require("./ledger.js");
const day = "2026-11-17";
const row = (id, start, stop, category = "做 case") =>
  ({id: String(id), day, name: "Task", category, start, stop});
const now = new Date(2026, 10, 17, 13, 30);
test("overlap is shared and the pie conserves elapsed time", () => {
  const result = L.summarize([row(1, 540, 660), row(2, 600, 720, "开发")], day, now);
  assert.equal(result.totals.get("做 case"), 90);
  assert.equal(result.totals.get("开发"), 90);
  assert.equal(result.overlap, 60);
  assert.equal(result.covered, 180);
  assert.equal(result.taskTotal, 240);
  assert.equal([...result.totals.values()].reduce((a, b) => a + b, 0), 270);
});
test("running task advances without setting Stop; future and historical gaps remain incomplete", () => {
  const running = row(1, 793, null);
  const result = L.summarize([running, row(2, null, null), row(3, 900, null)], day, now);
  assert.equal(result.covered, 17);
  assert.equal(result.active.size, 1);
  assert.equal(result.incomplete.size, 2);
  assert.equal(running.stop, null);
  assert.equal(L.summarize([running], day, new Date(2026, 10, 18, 12)).covered, 0);
});
test("work hours clip intervals and dates before work have no elapsed time", () => {
  const result = L.summarize([row(1, 480, 600), row(2, 960, 1080)], day, new Date(2026, 10, 17, 18));
  assert.equal(result.covered, 120);
  assert.equal(result.rest, 360);
  assert.equal(L.summarize([], day, new Date(2026, 10, 17, 8)).elapsed, 0);
});
test("backup validation preserves categories but rejects duplicate IDs and invalid times", () => {
  const value = L.data({version: 1, tasks: [row(1, 540, 600, " 开发 ")], categories: ["开发"]});
  assert.equal(value.tasks[0].category, "开发");
  assert.equal(value.categories.filter(name => name === "开发").length, 1);
  assert.throws(() => L.data({version: 1, tasks: [row(1, 540, 600), row(1, 600, 660)], categories: []}));
  assert.throws(() => L.task(row(1, 600, 540)));
  assert.throws(() => L.task({...row(1, 540, 600), day: "2026-02-30"}));
  assert.throws(() => L.categoryName("__proto__"));
  assert.throws(() => L.categoryName(L.ADD));
});
test("minutes are exact and invalid clocks are rejected", () => {
  assert.equal(L.parseTime("23:59"), 1439);
  assert.equal(L.parseTime(""), null);
  assert.equal(L.clock(545), "09:05");
  assert.throws(() => L.parseTime("24:00"));
});
