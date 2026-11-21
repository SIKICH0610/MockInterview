/* Drag-on-tablet tasks (see app/dragq.py for the data shape and the scoring rule).
   MIDrag.play(cfg, opts)   full-screen task for the child; the teacher taps Check
   MIDrag.editor(host, input) the task editor in the question form: "show the answer by placing the pieces" */
window.MIDrag = (function () {
  "use strict";
  const LANG = (window.I18N && window.I18N.lang) === "zh" ? "zh" : "en";
  const TXT = {
    en: {
      check: "Check", reset: "Start over", close: "Close", turn: "Tap a piece to turn it.",
      bg: "Background picture", addPieces: "Add pieces (pictures)", addSlot: "Add a place (one piece)", addBox: "Add a box (many pieces)",
      canTurn: "Pieces can be turned (direction counts)", layout: "1 · Lay out the start", answer: "2 · Show the correct answer", tryIt: "Try it",
      layoutHint: "Drag pieces to where they start. Drag places to where pieces should go; pull the corner to resize. Tap an item for its options.",
      answerHint: "Drag each piece to where it belongs. What you build here is the answer. Pieces you leave in the tray are extras that belong nowhere.",
      startTurn: "Turn at start", anyDir: "Any direction is fine", dup: "Duplicate", del: "Delete", size: "Size",
      label: "Label", picAdd: "Add a picture to the box", picChange: "Change the picture", picRemove: "Remove the picture", circle: "Round", outline: "Show outline", removeBg: "Remove background",
      uploading: "Uploading…", uploadFail: "Upload failed", result: "Score {s}: {r} of {t} right",
      empty: "Start with a background picture or some pieces.", needAnswer: "No answer set yet: open step 2 and place the pieces.",
      piece: "Piece", place: "Place", box: "Box",
      tidy: "Line the pieces up at the bottom", again: "Try again", resultHead: "Result of this try",
      points: "{s} of 2 points", detail: "{r} of {t} right", legend: "✓ right   ↻ right place, wrong direction   ✗ wrong   (no mark: left outside)",
      notInPlace: "Pieces start outside the places, so it went back. To say where a piece belongs, open step 2 and drop it there.",
    },
    zh: {
      check: "检查", reset: "重来", close: "关闭", turn: "点一下可以转动。",
      bg: "背景图", addPieces: "添加物件（图片）", addSlot: "添加位置（放一个）", addBox: "添加筐（放多个）",
      canTurn: "物件可以转动（方向计入对错）", layout: "1 · 摆好起始位置", answer: "2 · 摆出正确答案", tryIt: "试玩",
      layoutHint: "把物件拖到起始位置；把“位置”拖到物件应该去的地方，拉右下角可调整大小。点一下可看选项。",
      answerHint: "把每个物件拖到它该去的地方，摆出来的就是答案。留在外面的物件是干扰项，不属于任何位置。",
      startTurn: "起始方向", anyDir: "任何方向都算对", dup: "复制", del: "删除", size: "大小",
      label: "名称", picAdd: "给筐加一张图片", picChange: "更换图片", picRemove: "去掉图片", circle: "圆形", outline: "显示边框", removeBg: "去掉背景图",
      uploading: "上传中…", uploadFail: "上传失败", result: "得分 {s}：{t} 处对了 {r} 处",
      empty: "先放一张背景图，或添加几个物件。", needAnswer: "还没有设置答案：打开第 2 步，把物件摆到位。",
      piece: "物件", place: "位置", box: "筐",
      tidy: "把物件排到底部", again: "再试一次", resultHead: "这次试玩的结果",
      points: "{s} 分（满分 2 分）", detail: "{t} 处对了 {r} 处", legend: "✓ 正确   ↻ 位置对、方向不对   ✗ 错误   （没有标记：留在外面）",
      notInPlace: "起始位置要在框外，所以物件跳回了原处。要设置它属于哪里，请打开第 2 步再拖进去。",
    },
  }[LANG];
  const src = (id) => "/wb/dragasset/" + id;
  const el = (tag, cls, parent, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; if (parent) parent.appendChild(e); return e; };
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const r2 = (v) => Math.round(v * 100) / 100;

  // same rule as app/dragq.py (the server's answer is the one that is recorded; this one is for "Try it")
  function score(cfg, placement) {
    const slots = {}, pieces = {};
    cfg.slots.forEach((s) => (slots[s.id] = s));
    cfg.pieces.forEach((p) => (pieces[p.id] = p));
    const where = {};
    Object.keys(placement || {}).forEach((pid) => { const v = placement[pid]; if (pieces[pid] && v && slots[v.slot]) where[pid] = [slots[v.slot], ((v.rot || 0) % 360 + 360) % 360]; });
    const turned = (p, rot) => !cfg.rotate || p.free || rot === 0;
    const marks = {}, checks = [];
    const homes = new Set();
    cfg.slots.forEach((s) => { if (s.many) s.accept.forEach((k) => homes.add(k)); });
    cfg.slots.forEach((s) => {
      if (s.many || !s.accept.length) return;
      const pid = Object.keys(where).find((id) => where[id][0].id === s.id);
      if (!pid) { checks.push([false, false]); return; }
      const pos = s.accept.includes(pieces[pid].kind), ok = pos && turned(pieces[pid], where[pid][1]);
      checks.push([pos, ok]);
      marks[pid] = ok ? "ok" : pos ? "turn" : "no";
    });
    cfg.pieces.forEach((p) => {
      const w = where[p.id], sl = w ? w[0] : null;
      if (sl && !sl.many) { if (!sl.accept.length && !marks[p.id]) marks[p.id] = "no"; return; }
      if (homes.has(p.kind)) {
        const pos = !!sl && sl.accept.includes(p.kind), ok = pos && turned(p, w ? w[1] : 0);
        checks.push([pos, ok]);
        if (sl) marks[p.id] = ok ? "ok" : pos ? "turn" : "no";
      } else if (sl) { checks.push([false, false]); marks[p.id] = "no"; }
    });
    const total = checks.length, placed = checks.filter((c) => c[0]).length, right = checks.filter((c) => c[1]).length;
    return { score: total && right === total ? 2 : placed ? 1 : 0, right, total, placed, marks };
  }

  // ---------- drawing ----------
  function board(host, cfg) {
    host.textContent = "";
    const canvas = el("div", "dg-canvas", host);
    canvas.style.aspectRatio = String(cfg.ratio || 1.6);
    if (cfg.bg) { const b = el("img", "dg-bg", canvas); b.src = src(cfg.bg); b.alt = ""; b.draggable = false; }
    const slotEls = {}, pieceEls = {};
    cfg.slots.forEach((s) => {
      const d = el("div", "dg-slot" + (s.many ? " dg-many" : "") + (s.shape === "circle" ? " dg-round" : "") + (s.show ? "" : " dg-hidden"), canvas);
      d.dataset.id = s.id;
      if (s.label) el("div", "dg-slot-label", d, s.label);
      if (s.pic) {  // a picture at the top of a box, for children who cannot read the label
        const i = el("img", "dg-slot-pic", d); i.src = src(s.pic); i.alt = ""; i.draggable = false;
        i.style.top = ((s.label ? 9 : 1.5) / s.h) * 100 + "%"; i.style.height = (picRoom(s) / s.h) * 100 + "%";
      }
      slotEls[s.id] = d;
    });
    cfg.pieces.forEach((p) => {
      const d = el("div", "dg-piece", canvas);
      d.dataset.id = p.id;
      const i = el("img", "", d); i.src = src(p.img); i.alt = ""; i.draggable = false;
      pieceEls[p.id] = d;
    });
    const putSlot = (s) => { const d = slotEls[s.id]; d.style.left = s.x + "%"; d.style.top = s.y + "%"; d.style.width = s.w + "%"; d.style.height = s.h + "%"; };
    const putPiece = (p, x, y, rot, k) => {
      const d = pieceEls[p.id];
      d.style.left = x + "%"; d.style.top = y + "%"; d.style.width = p.w * (k || 1) + "%"; d.style.height = p.h * (k || 1) + "%";
      d.style.transform = "translate(-50%, -50%) rotate(" + (rot || 0) + "deg)";
    };
    cfg.slots.forEach(putSlot);
    return { canvas, slotEls, pieceEls, putSlot, putPiece };
  }
  // where pieces sit inside a box: rows of equal cells, centred, never on top of each other.
  // When the box is too small for them at full size, they are drawn smaller (k < 1) so they still fit.
  function picRoom(s) { return s.pic ? clamp(s.h * 0.36, 5, 24) : 0; }  // height kept for the picture of a box (% of the canvas)
  function boxCells(s, items) {
    if (!items.length) return { cells: [], k: 1 };
    const pw = Math.max.apply(null, items.map((p) => p.w)) + 1.2, ph = Math.max.apply(null, items.map((p) => p.h)) + 1.8;
    const top = (s.label ? 9 : 0) + (s.pic ? picRoom(s) + 1.5 : 0);  // room for the label and the picture
    const aw = Math.max(4, s.w - 2), ah = Math.max(4, s.h - top - 2);
    let best = null;
    for (let cols = 1; cols <= items.length; cols++) {
      const rows = Math.ceil(items.length / cols), k = Math.min(1, aw / (cols * pw), ah / (rows * ph));
      if (!best || k > best.k + 0.001) best = { cols, rows, k };
    }
    const cw = pw * best.k, chh = ph * best.k, y0 = s.y + top / 2 - ((best.rows - 1) * chh) / 2;
    const cells = items.map((p, i) => {
      const row = Math.floor(i / best.cols), inRow = Math.min(best.cols, items.length - row * best.cols);
      return [s.x - ((inRow - 1) * cw) / 2 + (i % best.cols) * cw, y0 + row * chh];
    });
    return { cells, k: best.k };
  }
  // rows along the bottom of the canvas, left to right, nothing overlapping: where pieces wait at the start
  function tray(cfg, pieces) {
    let y = 98, i = 0;
    while (i < pieces.length) {
      let x = 2, rowH = 0; const row = [];
      while (i < pieces.length && (row.length === 0 || x + pieces[i].w <= 98)) { row.push(pieces[i]); x += pieces[i].w + 1.5; rowH = Math.max(rowH, pieces[i].h); i++; }
      let cx = (100 - (x - 1.5 - 2)) / 2;
      row.forEach((p) => { p.x = r2(cx + p.w / 2); p.y = r2(y - rowH / 2); cx += p.w + 1.5; });
      y -= rowH + 2;
    }
  }
  function slotAt(cfg, x, y, slack) {
    let best = null, bd = 1e9;
    cfg.slots.forEach((s) => {
      const k = s.many ? 1 : slack;
      if (Math.abs(x - s.x) <= (s.w / 2) * k && Math.abs(y - s.y) <= (s.h / 2) * k) {
        const d = Math.hypot(x - s.x, (y - s.y) / (cfg.ratio || 1.6));
        if (d < bd) { bd = d; best = s; }
      }
    });
    return best;
  }
  // pointer dragging of one element; cb gets positions in % of the canvas
  function dragger(canvas, target, cb) {
    target.addEventListener("pointerdown", (e) => {
      if (e.button) return;
      e.preventDefault(); e.stopPropagation();
      const rect = canvas.getBoundingClientRect();
      const st = { x0: e.clientX, y0: e.clientY, moved: false, t: Date.now() };
      const pct = (ev) => [((ev.clientX - rect.left) / rect.width) * 100, ((ev.clientY - rect.top) / rect.height) * 100];
      const start = pct(e);
      if (cb.down) cb.down(start, e);
      try { target.setPointerCapture(e.pointerId); } catch (err) { /* older WebKit */ }
      const move = (ev) => {
        if (!st.moved && Math.hypot(ev.clientX - st.x0, ev.clientY - st.y0) < 7) return;
        st.moved = true;
        const p = pct(ev);
        cb.move(p[0] - start[0], p[1] - start[1], p, ev);
      };
      const up = (ev) => {
        target.removeEventListener("pointermove", move); target.removeEventListener("pointerup", up); target.removeEventListener("pointercancel", up);
        if (st.moved) cb.drop(pct(ev), ev); else if (cb.tap) cb.tap(ev);
      };
      target.addEventListener("pointermove", move); target.addEventListener("pointerup", up); target.addEventListener("pointercancel", up);
    });
  }

  // ---------- the child's screen ----------
  function play(cfg, opts) {
    opts = opts || {};
    const review = !!opts.review;
    const ov = el("div", "dg-overlay", document.body);
    const head = el("div", "dg-head", ov);
    const ttl = el("div", "dg-title", head);
    el("b", "", ttl, opts.title || "");
    if (cfg.rotate && !review) el("span", "dg-tip", ttl, TXT.turn);
    const btns = el("div", "dg-btns", head);
    const body = el("div", "dg-body", ov);
    const B = board(body, cfg);
    const fit = () => {  // the largest canvas of this shape that fits under the header
      const w = body.clientWidth - 24, h = body.clientHeight - 24, r = cfg.ratio || 1.6;
      B.canvas.style.width = Math.max(120, Math.min(w, h * r)) + "px";
    };
    fit();
    window.addEventListener("resize", fit);
    const place = {}, rot = {};
    cfg.pieces.forEach((p) => { rot[p.id] = p.rot || 0; });
    Object.keys(opts.placement || {}).forEach((pid) => { const v = opts.placement[pid]; if (v && v.slot) { place[pid] = v.slot; rot[pid] = v.rot || 0; } });
    const slotOf = (id) => cfg.slots.find((s) => s.id === id);
    function layout() {
      const inBox = {};
      cfg.pieces.forEach((p) => { const s = place[p.id] && slotOf(place[p.id]); if (s && s.many) (inBox[s.id] = inBox[s.id] || []).push(p); });
      const cell = {}, small = {};
      Object.keys(inBox).forEach((sid) => { const c = boxCells(slotOf(sid), inBox[sid]); inBox[sid].forEach((p, i) => { cell[p.id] = c.cells[i]; small[p.id] = c.k; }); });
      cfg.pieces.forEach((p) => {
        const s = place[p.id] && slotOf(place[p.id]);
        const xy = !s ? [p.x, p.y] : s.many ? cell[p.id] : [s.x, s.y];
        B.putPiece(p, xy[0], xy[1], rot[p.id], small[p.id]);
      });
    }
    layout();
    const close = () => { window.removeEventListener("resize", fit); document.body.classList.remove("dg-open"); ov.remove(); };
    document.body.classList.add("dg-open");
    if (review) {
      const marks = opts.marks || score(cfg, opts.placement || {}).marks;
      Object.keys(marks).forEach((pid) => { if (B.pieceEls[pid]) el("span", "dg-mark dg-mark-" + marks[pid], B.pieceEls[pid], marks[pid] === "ok" ? "✓" : marks[pid] === "turn" ? "↻" : "✗"); });
      ov.classList.add("dg-review");
      if (opts.result) {
        const r = opts.result, box = el("div", "dg-result dg-result-" + r.score, ov);
        ov.insertBefore(box, body);
        el("span", "dg-result-head", box, TXT.resultHead);
        el("b", "dg-result-score", box, TXT.points.replace("{s}", r.score));
        el("span", "dg-result-detail", box, TXT.detail.replace("{r}", r.right).replace("{t}", r.total));
        el("span", "dg-result-legend", box, TXT.legend);
        fit();
      }
      if (opts.onAgain) { const ag = el("button", "btn btn-sm", btns, TXT.again); ag.type = "button"; ag.addEventListener("click", () => { close(); opts.onAgain(); }); }
    } else {
      cfg.pieces.forEach((p) => {
        const d = B.pieceEls[p.id];
        let base = null;
        dragger(B.canvas, d, {
          down() { base = [parseFloat(d.style.left), parseFloat(d.style.top)]; d.classList.add("dg-drag"); },
          move(dx, dy) { d.style.left = base[0] + dx + "%"; d.style.top = base[1] + dy + "%"; },
          drop() {
            d.classList.remove("dg-drag");
            const s = slotAt(cfg, parseFloat(d.style.left), parseFloat(d.style.top), 1.5);
            if (s) {
              if (!s.many) Object.keys(place).forEach((o) => { if (place[o] === s.id && o !== p.id) delete place[o]; });  // the piece that was there goes back
              place[p.id] = s.id;
            } else delete place[p.id];
            layout();
          },
          tap() { d.classList.remove("dg-drag"); if (cfg.rotate) { rot[p.id] = (rot[p.id] + 90) % 360; layout(); } },
        });
      });
      const reset = el("button", "btn btn-ghost btn-sm", btns, TXT.reset); reset.type = "button";
      reset.addEventListener("click", () => { Object.keys(place).forEach((k) => delete place[k]); cfg.pieces.forEach((p) => { rot[p.id] = p.rot || 0; }); layout(); });
      const chk = el("button", "btn dg-check", btns, TXT.check); chk.type = "button";
      chk.addEventListener("click", () => {
        const out = {};
        Object.keys(place).forEach((pid) => { out[pid] = { slot: place[pid], rot: rot[pid] }; });
        if (opts.onCheck) opts.onCheck(out, close); else close();
      });
    }
    const x = el("button", "btn btn-ghost btn-sm", btns, TXT.close); x.type = "button";
    x.addEventListener("click", close);
    return { close };
  }

  // ---------- the editor in the question form ----------
  function editor(host, input) {
    let cfg;
    try { cfg = JSON.parse(input.value || ""); } catch (e) { cfg = null; }
    if (!cfg || !cfg.pieces) cfg = { v: 1, ratio: 1.6, rotate: false, bg: null, slots: [], pieces: [] };
    let mode = "layout", selected = null, seq = Date.now() % 100000;
    const nid = (p) => p + (++seq).toString(36);
    host.textContent = "";
    const bar = el("div", "dge-bar", host);
    const file = (multiple, cb) => {
      const i = el("input"); i.type = "file"; i.accept = "image/png,image/jpeg,image/webp"; i.multiple = multiple;
      i.addEventListener("change", () => cb([...i.files]));
      i.click();
    };
    const status = el("span", "dge-status muted small");
    async function upload(f) {
      const fd = new FormData(); fd.append("file", f);
      const r = await fetch("/admin/drag/asset", { method: "POST", body: fd, credentials: "same-origin" });
      const j = await r.json().catch(() => ({}));
      if (!j.ok) throw new Error(j.error || TXT.uploadFail);
      return j;
    }
    const button = (text, fn, cls) => { const b = el("button", "btn btn-ghost btn-sm " + (cls || ""), bar, text); b.type = "button"; b.addEventListener("click", fn); return b; };
    button(TXT.bg, () => file(false, async (fs) => {
      if (!fs[0]) return;
      status.textContent = TXT.uploading;
      try { const a = await upload(fs[0]); cfg.bg = a.id; if (a.w && a.h) cfg.ratio = r2(clamp(a.w / a.h, 0.5, 3)); status.textContent = ""; draw(); } catch (e) { status.textContent = e.message; }
    }));
    button(TXT.addPieces, () => file(true, async (fs) => {
      status.textContent = TXT.uploading;
      try {
        for (const f of fs) {
          const a = await upload(f);
          let w = 10, h = w * cfg.ratio * ((a.h || 1) / (a.w || 1));
          if (h > 22) { w = (w * 22) / h; h = 22; }  // tall pictures: not taller than a fifth of the canvas
          cfg.pieces.push({ id: nid("p"), img: a.id, kind: "k" + a.id, x: 50, y: 90, w: r2(w), h: r2(h), rot: 0, free: false });
        }
        tray(cfg, cfg.pieces);  // everything waits along the bottom, side by side
        status.textContent = ""; draw();
      } catch (e) { status.textContent = e.message; draw(); }
    }));
    button(TXT.addSlot, () => { const s = { id: nid("s"), x: 50, y: 40, w: 12, h: r2(clamp(12 * cfg.ratio, 2, 90)), many: false, shape: "rect", show: true, label: "", accept: [] }; cfg.slots.push(s); selected = s.id; mode = "layout"; draw(); });
    button(TXT.addBox, () => { const n = cfg.slots.filter((s) => s.many).length; const s = { id: nid("s"), x: n % 2 ? 74 : 26, y: 36, w: 44, h: 56, many: true, shape: "rect", show: true, label: "", accept: [] }; cfg.slots.push(s); selected = s.id; mode = "layout"; draw(); });
    button(TXT.tidy, () => { tray(cfg, cfg.pieces); mode = "layout"; draw(); });
    const turnL = el("label", "inline-check dge-turn", bar);
    const turnC = el("input", "", turnL); turnC.type = "checkbox"; turnC.checked = !!cfg.rotate;
    turnL.appendChild(document.createTextNode(" " + TXT.canTurn));
    turnC.addEventListener("change", () => { cfg.rotate = turnC.checked; draw(); });
    bar.appendChild(status);

    const tabs = el("div", "dge-tabs", host);
    const tab = {};
    ["layout", "answer"].forEach((m) => { tab[m] = el("button", "wbn", tabs, TXT[m]); tab[m].type = "button"; tab[m].addEventListener("click", () => { mode = m; selected = null; draw(); }); });
    const tryB = el("button", "btn btn-sm dge-try", tabs, TXT.tryIt); tryB.type = "button";
    const title = () => (document.querySelector("#qform [name=prompt]") || {}).value || (document.querySelector("#qform [name=title]") || {}).value || "";
    function tryIt() {
      if (!cfg.slots.some((s) => s.accept.length)) { alert(TXT.needAnswer); return; }
      const copy = () => JSON.parse(JSON.stringify(cfg));
      play(copy(), { title: title(), onCheck(pl, close) {
        const r = score(cfg, pl);
        close();  // then show the author what the teacher will get: the score, and which pieces were right
        play(copy(), { title: title(), review: true, placement: pl, marks: r.marks, result: r, onAgain: tryIt });
      } });
    }
    tryB.addEventListener("click", tryIt);
    const hint = el("p", "muted small dge-hint", host);
    const stage = el("div", "dge-stage", host);
    const props = el("div", "dge-props", host);

    const save = () => { input.value = cfg.pieces.length || cfg.slots.length ? JSON.stringify(cfg) : ""; };
    const find = (id) => cfg.pieces.find((p) => p.id === id) || cfg.slots.find((s) => s.id === id);
    // in "answer" mode a piece sits where it belongs: its place, its box, or the tray when it belongs nowhere
    function answerSpots() {
      const spot = {}, used = new Set();
      cfg.slots.filter((s) => !s.many).forEach((s) => {
        const p = cfg.pieces.find((q) => s.accept.includes(q.kind) && !used.has(q.id));
        if (p) { used.add(p.id); spot[p.id] = [s.x, s.y, s.id]; }
      });
      cfg.slots.filter((s) => s.many).forEach((s) => {
        const items = cfg.pieces.filter((q) => s.accept.includes(q.kind) && !used.has(q.id));
        const c = boxCells(s, items);
        items.forEach((p, i) => { used.add(p.id); spot[p.id] = [c.cells[i][0], c.cells[i][1], s.id, c.k]; });
      });
      return spot;
    }
    let keepHint = false;
    function drawKeepHint() { keepHint = true; draw(); keepHint = false; }
    function draw() {
      save();
      Object.keys(tab).forEach((m) => tab[m].classList.toggle("on", m === mode));
      if (!keepHint) {
        hint.classList.remove("dge-warn");
        hint.textContent = !cfg.pieces.length && !cfg.slots.length && !cfg.bg ? TXT.empty : mode === "layout" ? TXT.layoutHint : TXT.answerHint;
      }
      const B = board(stage, cfg);
      B.canvas.classList.add("dge-canvas", "dge-" + mode);
      B.canvas.addEventListener("pointerdown", () => { if (selected) { selected = null; draw(); } });
      const spots = mode === "answer" ? answerSpots() : {};
      cfg.pieces.forEach((p) => {
        const d = B.pieceEls[p.id], sp = spots[p.id];
        if (mode === "answer") { B.putPiece(p, sp ? sp[0] : p.x, sp ? sp[1] : p.y, 0, sp ? sp[3] : 1); d.classList.toggle("dge-extra", !sp); }
        else B.putPiece(p, p.x, p.y, cfg.rotate ? p.rot : 0);
        d.classList.toggle("dge-sel", selected === p.id);
        let base = null;
        dragger(B.canvas, d, {
          down() { base = [parseFloat(d.style.left), parseFloat(d.style.top)]; d.classList.add("dg-drag"); },
          move(dx, dy) { d.style.left = clamp(base[0] + dx, 0, 100) + "%"; d.style.top = clamp(base[1] + dy, 0, 100) + "%"; },
          drop() {
            const x = parseFloat(d.style.left), y = parseFloat(d.style.top);
            if (mode === "layout") {
              // a start position is always outside the places: dropped on one, the piece jumps back to where it was
              if (slotAt(cfg, x, y, 1)) { hint.textContent = TXT.notInPlace; hint.classList.add("dge-warn"); selected = p.id; drawKeepHint(); return; }
              p.x = r2(x); p.y = r2(y);
            }
            else {
              const s = slotAt(cfg, x, y, 1.5);
              // pieces made from one picture belong together: take the kind out of where it was
              cfg.slots.forEach((o) => { if (o.many || (sp && o.id === sp[2])) o.accept = o.accept.filter((k) => k !== p.kind); });
              if (s) { if (s.many) s.accept.push(p.kind); else s.accept = [p.kind]; }
            }
            selected = p.id; draw();
          },
          tap() { selected = p.id; draw(); },
        });
      });
      cfg.slots.forEach((s) => {
        const d = B.slotEls[s.id];
        d.classList.remove("dg-hidden");
        d.classList.toggle("dge-ghost", !s.show);
        d.classList.toggle("dge-sel", selected === s.id);
        if (mode !== "layout") return;
        let base = null;
        dragger(B.canvas, d, {
          down() { base = [s.x, s.y]; },
          move(dx, dy) { s.x = r2(clamp(base[0] + dx, 0, 100)); s.y = r2(clamp(base[1] + dy, 0, 100)); B.putSlot(s); },
          drop() { selected = s.id; draw(); },
          tap() { selected = s.id; draw(); },
        });
      });
      // resize handle on the selected item (layout mode)
      const it = selected && find(selected);
      if (it && mode === "layout") {
        const isPiece = cfg.pieces.includes(it), d = isPiece ? B.pieceEls[it.id] : B.slotEls[it.id];
        const hd = el("span", "dge-handle", d);
        let w0, h0;
        dragger(B.canvas, hd, {
          down() { w0 = it.w; h0 = it.h; },
          move(dx, dy) {
            if (isPiece) { const k = clamp((w0 + dx * 2) / w0, 0.2, 8); it.w = r2(clamp(w0 * k, 2, 100)); it.h = r2(clamp(h0 * k, 2, 100)); B.putPiece(it, it.x, it.y, cfg.rotate ? it.rot : 0); }
            else { it.w = r2(clamp(w0 + dx * 2, 2, 100)); it.h = r2(clamp(h0 + dy * 2, 2, 100)); B.putSlot(it); }
          },
          drop() { draw(); },
        });
      }
      drawProps();
    }
    function drawProps() {
      props.textContent = "";
      const it = selected && find(selected);
      if (!it) return;
      const isPiece = cfg.pieces.includes(it);
      el("b", "dge-props-name", props, isPiece ? TXT.piece : it.many ? TXT.box : TXT.place);
      const btn = (text, fn, cls) => { const b = el("button", "btn btn-ghost btn-sm " + (cls || ""), props, text); b.type = "button"; b.addEventListener("click", fn); };
      const check = (text, on, fn) => { const l = el("label", "inline-check", props); const c = el("input", "", l); c.type = "checkbox"; c.checked = on; l.appendChild(document.createTextNode(" " + text)); c.addEventListener("change", () => { fn(c.checked); draw(); }); };
      if (isPiece) {
        if (cfg.rotate) { btn(TXT.startTurn + " ↻ " + (it.rot || 0) + "°", () => { it.rot = ((it.rot || 0) + 90) % 360; draw(); }); check(TXT.anyDir, !!it.free, (v) => { it.free = v; }); }
        btn(TXT.dup, () => { const c = Object.assign({}, it, { id: nid("p"), x: r2(clamp(it.x + 4, 0, 100)), y: r2(clamp(it.y + 3, 0, 100)) }); cfg.pieces.push(c); selected = c.id; draw(); });
        btn(TXT.del, () => {
          cfg.pieces = cfg.pieces.filter((p) => p !== it);
          if (!cfg.pieces.some((p) => p.kind === it.kind)) cfg.slots.forEach((s) => { s.accept = s.accept.filter((k) => k !== it.kind); });
          selected = null; draw();
        }, "btn-danger");
      } else {
        if (it.many) {
          const l = el("label", "dge-label", props, TXT.label + " ");
          const i = el("input", "", l); i.type = "text"; i.value = it.label || ""; i.maxLength = 40;
          i.addEventListener("input", () => { it.label = i.value; save(); });
          i.addEventListener("change", draw);
          btn(it.pic ? TXT.picChange : TXT.picAdd, () => file(false, async (fs) => {
            if (!fs[0]) return;
            status.textContent = TXT.uploading;
            try { const a = await upload(fs[0]); it.pic = a.id; status.textContent = ""; draw(); } catch (e) { status.textContent = e.message; }
          }));
          if (it.pic) btn(TXT.picRemove, () => { it.pic = null; draw(); });
        }
        check(TXT.circle, it.shape === "circle", (v) => { it.shape = v ? "circle" : "rect"; });
        check(TXT.outline, !!it.show, (v) => { it.show = v; });
        btn(TXT.del, () => { cfg.slots = cfg.slots.filter((s) => s !== it); selected = null; draw(); }, "btn-danger");
      }
      if (cfg.bg && !isPiece) { /* nothing extra */ }
    }
    const rm = button(TXT.removeBg, () => { cfg.bg = null; draw(); });
    rm.classList.add("dge-rmbg");
    draw();
    return { get: () => cfg };
  }

  return { play, editor, score };
})();
