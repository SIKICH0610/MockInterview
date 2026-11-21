/* Developmental-stage evidence rules of a question (see app/devstage.py): a small table in the question form.
   Each row: measure · stage · which number counts · "shown from" / "partly from" · what the child showed · next step. */
(function () {
  "use strict";
  const host = document.getElementById("ev-editor"), form = document.getElementById("qform"), meta = window.MI_DEV;
  if (!host || !form || !meta) return;
  const input = form.querySelector("[name=evidence]");
  const zh = (window.I18N && window.I18N.lang) === "zh";
  const T = zh ? {
    add: "添加一条证据", del: "删除", measure: "维度", stage: "阶段", none: "只记录表现（不定阶段）", by: "看哪个数",
    score: "任务得分 (0–2)", count: "答对个数", expr: "表达得分 (0–2)", full: "达到", part: "部分", partPh: "可不填",
    en: "孩子表现出了什么（英文）", zh: "孩子表现出了什么（中文）", nen: "下一步（英文）", nzh: "下一步（中文）",
    ren: "年龄参考（英文，可不填）", rzh: "年龄参考（中文，可不填）", empty: "还没有证据规则。", more: "下一步与年龄参考",
    fullTip: "这个数达到多少算「观察到」", partTip: "达到多少算「部分表现」",
  } : {
    add: "Add an evidence line", del: "Remove", measure: "Measure", stage: "Stage", none: "Record only (no stage)", by: "Number looked at",
    score: "Task score (0–2)", count: "Items right", expr: "Expression score (0–2)", full: "Shown from", part: "Partly from", partPh: "optional",
    en: "What the child showed (English)", zh: "What the child showed (Chinese)", nen: "Next step (English)", nzh: "Next step (Chinese)",
    ren: "Age reference (English, optional)", rzh: "Age reference (Chinese, optional)", empty: "No evidence lines yet.", more: "Next step and age reference",
    fullTip: "From this number up, the evidence counts as shown", partTip: "From this number up, it counts as partly shown",
  };
  let rules = [];
  try { rules = JSON.parse(input.value || "[]"); } catch (e) { rules = []; }
  if (!Array.isArray(rules)) rules = [];
  const el = (tag, cls, parent, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; if (parent) parent.appendChild(e); return e; };
  const save = () => { input.value = rules.length ? JSON.stringify(rules) : ""; };
  function field(parent, label, make) { const l = el("label", "eve-f", parent); el("span", "eve-l", l, label); const c = make(); l.appendChild(c); return c; }
  function select(opts, value, fn) {
    const s = document.createElement("select");
    opts.forEach(([v, text]) => { const o = el("option", "", s, text); o.value = v; });
    s.value = value; s.addEventListener("change", () => { fn(s.value); save(); });
    return s;
  }
  function text(value, fn, ph) {
    const i = document.createElement("input"); i.type = "text"; i.value = value || ""; i.maxLength = 300; if (ph) i.placeholder = ph;
    i.addEventListener("input", () => { fn(i.value); save(); });
    return i;
  }
  function num(value, max, fn, ph, title) {
    const i = document.createElement("input"); i.type = "number"; i.min = 1; i.max = max; i.value = value == null ? "" : value; i.title = title; if (ph) i.placeholder = ph;
    i.addEventListener("input", () => { fn(i.value === "" ? null : Math.max(1, Math.min(max, parseInt(i.value, 10) || 1))); save(); });
    return i;
  }
  function draw() {
    host.textContent = "";
    if (!rules.length) el("p", "muted small", host, T.empty);
    rules.forEach((r, idx) => {
      const row = el("div", "eve-row", host), top = el("div", "eve-line", row);
      field(top, T.measure, () => select(meta.measures.map((m) => [m[0], (zh ? m[3] : m[2]) + (m[1] ? " · " + m[1] : "")]), r.m, (v) => { r.m = v; }));
      field(top, T.stage, () => select([["", T.none]].concat(meta.stages.map((s) => [s[0], s[0] + " · " + (zh ? s[2] : s[1])])), r.st || "", (v) => { r.st = v; }));
      field(top, T.by, () => select([["score", T.score], ["count", T.count], ["expr", T.expr]], r.by || "score", (v) => { r.by = v; draw(); }));
      const max = r.by === "count" ? 30 : 2;
      field(top, T.full, () => num(r.full, max, (v) => { r.full = v || 1; }, "", T.fullTip)).classList.add("eve-n");
      field(top, T.part, () => num(r.part, max, (v) => { r.part = v; }, T.partPh, T.partTip)).classList.add("eve-n");
      const b = el("button", "btn btn-ghost btn-sm btn-danger eve-del", top, T.del); b.type = "button";
      b.addEventListener("click", () => { rules.splice(idx, 1); save(); draw(); });
      const mid = el("div", "eve-line eve-wide", row);
      field(mid, T.en, () => text(r.en, (v) => { r.en = v; }));
      field(mid, T.zh, () => text(r.zh, (v) => { r.zh = v; }));
      const more = el("details", "eve-more", row); el("summary", "", more, T.more);
      if (r.nen || r.nzh || r.ren || r.rzh) more.open = true;
      const l3 = el("div", "eve-line eve-wide", more);
      field(l3, T.nen, () => text(r.nen, (v) => { r.nen = v; }));
      field(l3, T.nzh, () => text(r.nzh, (v) => { r.nzh = v; }));
      const l4 = el("div", "eve-line eve-wide", more);
      field(l4, T.ren, () => text(r.ren, (v) => { r.ren = v; }));
      field(l4, T.rzh, () => text(r.rzh, (v) => { r.rzh = v; }));
    });
    const add = el("button", "btn btn-ghost btn-sm", host, "+ " + T.add); add.type = "button";
    add.addEventListener("click", () => {
      const counting = !!form.querySelector(".qf-count:not([hidden])");
      rules.push({ m: meta.measures[0][0], st: "", by: counting ? "count" : "score", full: counting ? 3 : 2, part: null, en: "", zh: "", nen: "", nzh: "", ren: "", rzh: "" });
      save(); draw();
    });
  }
  host.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.tagName === "INPUT") e.preventDefault(); });
  draw();
})();
