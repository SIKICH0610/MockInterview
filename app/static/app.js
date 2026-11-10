/* Workbench client: autosave scoring cards, question switching, events, admin selects */
(function () {
  "use strict";

  async function api(path, body) {
    const r = await fetch("/api" + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    let j = {};
    try { j = await r.json(); } catch (e) { /* ignore */ }
    return { status: r.status, j };
  }

  const teacherId = parseInt(document.body.dataset.teacher || "0", 10) || null;
  const I18N = window.I18N || {};
  const tr = (k, fb) => I18N[k] || fb;

  /* ---------- card state ---------- */

  function cardState(card) {
    const pick = (kind) => {
      const b = card.querySelector('.sbtn[data-kind="' + kind + '"].on');
      return b ? parseInt(b.dataset.val, 10) : null;
    };
    const academic = pick("a");
    const expression = pick("e");
    const tv = card.querySelector(".trial-val");
    const trial = tv && tv.dataset.val !== "" ? parseInt(tv.dataset.val, 10) : null;
    let status = null;
    if (card.querySelector('.pill[data-status="not_observed"].on')) status = "not_observed";
    else if (card.querySelector('.pill[data-status="not_completed"].on')) status = "not_completed";
    else if (academic !== null || expression !== null || trial !== null) status = "scored";
    const ta = card.querySelector(".note-ta");
    const note = ta ? ta.value : "";
    if (status === null && note.trim() !== "") status = "scored";
    return { academic, expression, trial, status, note };
  }

  function applyRecord(card, rec) {
    card.dataset.rev = rec.rev;
    card.querySelectorAll(".sbtn").forEach((b) => b.classList.remove("on"));
    if (rec.status !== "not_observed" && rec.status !== "not_completed") {
      if (rec.academic !== null && rec.academic !== undefined) {
        const b = card.querySelector('.sbtn[data-kind="a"][data-val="' + rec.academic + '"]');
        if (b) b.classList.add("on");
      }
      if (rec.expression !== null && rec.expression !== undefined) {
        const b = card.querySelector('.sbtn[data-kind="e"][data-val="' + rec.expression + '"]');
        if (b) b.classList.add("on");
      }
    }
    card.querySelectorAll(".pill").forEach((p) => {
      p.classList.toggle("on", p.dataset.status === rec.status);
    });
    const tv = card.querySelector(".trial-val");
    if (tv) {
      tv.dataset.val = rec.trial === null || rec.trial === undefined ? "" : String(rec.trial);
      tv.textContent = tv.dataset.val === "" ? "–" : tv.dataset.val;
    }
    const ta = card.querySelector(".note-ta");
    if (ta) ta.value = rec.note || "";
    card.dataset.status = rec.status || "";
    updateChips();
  }

  let saveTimers = new Map();

  function queueSave(card, delay) {
    const key = card.dataset.student + ":" + card.dataset.code;
    clearTimeout(saveTimers.get(key));
    saveTimers.set(key, setTimeout(() => saveCard(card), delay === undefined ? 350 : delay));
  }

  async function saveCard(card) {
    const state = cardState(card);
    const payload = Object.assign(state, {
      student_id: parseInt(card.dataset.student, 10),
      code: card.dataset.code,
      rev: parseInt(card.dataset.rev || "0", 10),
      teacher_id: teacherId,
    });
    card.classList.add("saving");
    const { status, j } = await api("/record/upsert", payload);
    card.classList.remove("saving");
    const ind = card.querySelector(".save-ind");
    if (status === 409 && j.conflict) {
      showConflict(card, j.current);
      return;
    }
    if (j.ok) {
      card.dataset.rev = j.rev;
      card.dataset.status = state.status || "";
      card.classList.toggle("st-not_observed", state.status === "not_observed");
      card.classList.toggle("st-not_completed", state.status === "not_completed");
      if (ind) {
        ind.textContent = tr("saved", "Saved");
        ind.classList.add("show");
        ind.classList.remove("err");
        setTimeout(() => ind.classList.remove("show"), 1400);
      }
      updateChips();
    } else if (ind) {
      ind.textContent = tr("saveFailed", "Save failed");
      ind.classList.add("show", "err");
    }
  }

  function showConflict(card, current) {
    const bar = card.querySelector(".conflict-bar");
    if (!bar) return;
    bar.innerHTML = "";
    const span = document.createElement("span");
    span.textContent = tr("updatedBy", "Updated by") + " " + (current.by || tr("another", "another teacher"));
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = tr("loadLatest", "Load latest");
    btn.addEventListener("click", () => {
      applyRecord(card, current);
      bar.classList.remove("show");
    });
    bar.appendChild(span);
    bar.appendChild(btn);
    bar.classList.add("show");
  }

  /* ---------- question switching (group page) ---------- */

  function showSection(code) {
    document.querySelectorAll(".code-section").forEach((s) => {
      s.classList.toggle("hidden", s.dataset.code !== code);
    });
    document.querySelectorAll(".qchip").forEach((c) => {
      c.classList.toggle("on", c.dataset.code === code);
    });
    window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
  }

  function updateChips() {
    document.querySelectorAll(".code-section").forEach((sec) => {
      const cards = sec.querySelectorAll(".qcard");
      if (!cards.length) return;
      let done = 0;
      cards.forEach((c) => { if (c.dataset.status) done += 1; });
      const chip = document.querySelector('.qchip[data-code="' + sec.dataset.code + '"]');
      if (chip) {
        const prog = chip.querySelector(".qchip-prog");
        if (prog) prog.textContent = cards.length === 1 ? (done ? "✓" : "") : done + "/" + cards.length;
        chip.classList.toggle("done", done === cards.length);
      }
    });
  }

  function currentSectionIndex() {
    const secs = Array.from(document.querySelectorAll(".code-section"));
    return secs.findIndex((s) => !s.classList.contains("hidden"));
  }

  /* ---------- clicks ---------- */

  document.addEventListener("click", (ev) => {
    const chip = ev.target.closest(".qchip");
    if (chip) {
      if (document.body.dataset.page === "student") {
        const sec = document.querySelector('.code-section[data-code="' + chip.dataset.code + '"]');
        if (sec) sec.scrollIntoView({ behavior: "smooth", block: "start" });
      } else {
        showSection(chip.dataset.code);
      }
      return;
    }

    const nav = ev.target.closest(".qprev, .qnext");
    if (nav) {
      const secs = Array.from(document.querySelectorAll(".code-section"));
      let i = currentSectionIndex();
      i += nav.classList.contains("qnext") ? 1 : -1;
      if (i >= 0 && i < secs.length) showSection(secs[i].dataset.code);
      return;
    }

    const card = ev.target.closest(".qcard");
    if (!card) return;

    const sbtn = ev.target.closest(".sbtn");
    if (sbtn) {
      const kind = sbtn.dataset.kind;
      const was = sbtn.classList.contains("on");
      card.querySelectorAll('.sbtn[data-kind="' + kind + '"]').forEach((b) => b.classList.remove("on"));
      if (!was) sbtn.classList.add("on");
      card.querySelectorAll(".pill").forEach((p) => p.classList.remove("on"));
      queueSave(card, 150);
      return;
    }

    const pill = ev.target.closest(".pill");
    if (pill) {
      const was = pill.classList.contains("on");
      card.querySelectorAll(".pill").forEach((p) => p.classList.remove("on"));
      card.querySelectorAll(".sbtn").forEach((b) => b.classList.remove("on"));
      const tv = card.querySelector(".trial-val");
      if (tv) { tv.dataset.val = ""; tv.textContent = "–"; }
      if (!was) pill.classList.add("on");
      queueSave(card, 150);
      return;
    }

    const step = ev.target.closest(".tminus, .tplus");
    if (step) {
      const tv = card.querySelector(".trial-val");
      const max = parseInt(tv.dataset.max, 10);
      let v = tv.dataset.val === "" ? null : parseInt(tv.dataset.val, 10);
      if (step.classList.contains("tplus")) v = v === null ? 1 : Math.min(max, v + 1);
      else v = v === null || v === 0 ? null : v - 1;
      tv.dataset.val = v === null ? "" : String(v);
      tv.textContent = v === null ? "–" : String(v);
      card.querySelectorAll(".pill").forEach((p) => p.classList.remove("on"));
      queueSave(card, 400);
      return;
    }

    const noteBtn = ev.target.closest(".note-btn");
    if (noteBtn) {
      const wrap = card.querySelector(".note-wrap");
      wrap.classList.toggle("open");
      if (wrap.classList.contains("open")) wrap.querySelector(".note-ta").focus();
      return;
    }
  });

  document.addEventListener(
    "blur",
    (ev) => {
      if (ev.target && ev.target.classList && ev.target.classList.contains("note-ta")) {
        const card = ev.target.closest(".qcard");
        if (!card) return;
        const btn = card.querySelector(".note-btn");
        if (btn) btn.classList.toggle("has-note", ev.target.value.trim() !== "");
        queueSave(card, 0);
      }
    },
    true
  );

  updateChips();

  /* ---------- events (student page) ---------- */

  const evForm = document.getElementById("event-form");
  if (evForm) {
    evForm.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const fd = new FormData(evForm);
      const payload = {
        student_id: parseInt(document.body.dataset.student, 10),
        category: fd.get("category"),
        stage: fd.get("stage"),
        points: parseInt(fd.get("points") || "1", 10),
        reason: fd.get("reason"),
        support: fd.get("support"),
        teacher_id: teacherId,
      };
      const { j } = await api("/event/add", payload);
      if (j.ok) {
        const li = document.createElement("li");
        li.dataset.id = j.id;
        li.innerHTML =
          '<span class="ev-cat ev-' + j.category + '">' + j.category + "</span>" +
          '<span class="ev-stage">' + j.stage + "</span>" +
          '<span class="ev-points">−' + j.points + "</span>" +
          '<span class="ev-reason"></span>' +
          (j.support ? '<span class="ev-support"></span>' : "") +
          '<span class="by">' + (j.by || "") + " · " + j.time + "</span>" +
          '<button type="button" class="ev-del" title="Delete">×</button>';
        li.querySelector(".ev-reason").textContent = j.reason;
        if (j.support) {
          const prefix = document.getElementById("event-list").dataset.supportPrefix || "Support:";
          li.querySelector(".ev-support").textContent = prefix + " " + j.support;
        }
        document.getElementById("event-list").prepend(li);
        evForm.querySelector('input[name="reason"]').value = "";
        evForm.querySelector('input[name="support"]').value = "";
      }
    });
    document.getElementById("event-list").addEventListener("click", async (ev) => {
      const del = ev.target.closest(".ev-del");
      if (!del) return;
      const li = del.closest("li");
      if (!del.dataset.arm) {
        del.dataset.arm = "1";
        del.classList.add("ev-del-armed");
        del.textContent = I18N.tapAgainDel || "Tap again to delete";
        setTimeout(() => {
          if (del.dataset.arm) {
            del.dataset.arm = "";
            del.classList.remove("ev-del-armed");
            del.textContent = "×";
          }
        }, 3000);
        return;
      }
      const { j } = await api("/event/delete", { id: parseInt(li.dataset.id, 10) });
      if (j.ok) li.remove();
    });
  }

  /* ---------- stage observation page ---------- */

  if (document.body.dataset.page === "stage") {
    const stageName = document.body.dataset.stage;

    document.querySelectorAll(".prompt-chip").forEach((c) => {
      c.addEventListener("click", () => {
        document.querySelectorAll(".prompt-chip").forEach((x) => x.classList.remove("on"));
        c.classList.add("on");
        document.querySelectorAll(".prompt-text").forEach((pt) => {
          pt.classList.toggle("show", pt.dataset.idx === c.dataset.idx);
        });
      });
    });

    function flashInd(card, ok) {
      const ind = card.querySelector(".save-ind");
      if (!ind) return;
      ind.textContent = ok ? tr("saved", "Saved") : tr("saveFailed", "Save failed");
      ind.classList.add("show");
      ind.classList.toggle("err", !ok);
      setTimeout(() => ind.classList.remove("show"), 1400);
    }

    document.addEventListener("click", async (ev) => {
      const rb = ev.target.closest(".resp-btn");
      if (rb) {
        const card = rb.closest(".obs-card");
        const noteInput = card.querySelector(".obs-note");
        const promptChip = document.querySelector(".prompt-chip.on");
        const payload = {
          student_id: parseInt(card.dataset.student, 10),
          stage: stageName,
          prompt_index: stageName === "Circle Time" && promptChip ? parseInt(promptChip.dataset.idx, 10) : null,
          response: rb.dataset.resp,
          note: noteInput ? noteInput.value.trim() : "",
          teacher_id: teacherId,
        };
        const { j } = await api("/stage/add", payload);
        if (j.ok) {
          const pkey = j.prompt_index ? String(j.prompt_index) : "";
          card.querySelectorAll(".obs-item").forEach((it) => {
            if ((it.dataset.prompt || "") === pkey) it.remove();
          });
          const item = document.createElement("div");
          item.className = "obs-item";
          item.dataset.id = j.id;
          item.dataset.prompt = pkey;
          let html = "";
          if (j.prompt_index) html += '<span class="obs-p">P' + j.prompt_index + "</span>";
          html += '<span class="obs-resp r-' + j.response + '"></span>';
          if (j.note) html += '<span class="obs-note-txt"></span>';
          html += '<span class="by">' + (j.by || "") + " · " + j.time + "</span>";
          html += '<button type="button" class="obs-del" title="Delete">×</button>';
          item.innerHTML = html;
          item.querySelector(".obs-resp").textContent = rb.dataset.label;
          if (j.note) item.querySelector(".obs-note-txt").textContent = j.note;
          card.querySelector(".obs-log").prepend(item);
          if (noteInput) noteInput.value = "";
          flashInd(card, true);
        } else {
          flashInd(card, false);
        }
        return;
      }

      const od = ev.target.closest(".obs-del");
      if (od) {
        const item = od.closest(".obs-item");
        const { j } = await api("/stage/delete", { id: parseInt(item.dataset.id, 10) });
        if (j.ok) item.remove();
        return;
      }

      const dopt = ev.target.closest(".dim-opt");
      if (dopt) {
        const card = dopt.closest(".obs-card");
        const row = dopt.closest(".dim-row");
        const was = dopt.classList.contains("on");
        row.querySelectorAll(".dim-opt").forEach((b) => b.classList.remove("on"));
        if (!was) dopt.classList.add("on");
        const { j } = await api("/stage/dim", {
          student_id: parseInt(card.dataset.student, 10),
          stage: card.dataset.stage,
          dim: dopt.dataset.dim,
          value: was ? "" : dopt.dataset.val,
        });
        flashInd(card, !!j.ok);
        return;
      }

      const sp = ev.target.closest(".sep-pill");
      if (sp) {
        const card = sp.closest(".single-card");
        const was = sp.classList.contains("on");
        card.querySelectorAll(".sep-pill").forEach((p) => p.classList.remove("on"));
        if (!was) sp.classList.add("on");
        const { j } = await api("/stage/single", {
          student_id: parseInt(card.dataset.student, 10),
          stage: card.dataset.stage,
          response: was ? "" : sp.dataset.resp,
          teacher_id: teacherId,
        });
        flashInd(card, !!j.ok);
        return;
      }
    });

    document.addEventListener(
      "blur",
      async (ev) => {
        if (ev.target && ev.target.classList && ev.target.classList.contains("sep-note")) {
          const card = ev.target.closest(".single-card");
          const { j } = await api("/stage/single", {
            student_id: parseInt(card.dataset.student, 10),
            stage: card.dataset.stage,
            note: ev.target.value,
            teacher_id: teacherId,
          });
          flashInd(card, !!j.ok);
        }
      },
      true
    );
  }

  /* ---------- review page ---------- */

  if (document.body.dataset.page === "review") {
    document.addEventListener("click", async (ev) => {
      const btn = ev.target.closest(".review-btn");
      if (!btn) return;
      const row = btn.closest(".mx-row");
      const confirmed = btn.classList.contains("btn-ghost");
      if (confirmed) {
        // two-tap confirmation instead of a native dialog (blocked on some iPads)
        if (!btn.dataset.arm) {
          btn.dataset.arm = "1";
          btn.classList.add("btn-armed");
          btn.textContent = I18N.tapAgain || "Tap again to undo";
          setTimeout(() => {
            if (btn.dataset.arm) {
              btn.dataset.arm = "";
              btn.classList.remove("btn-armed");
              btn.textContent = I18N.unconfirm || "Undo";
            }
          }, 3000);
          return;
        }
        btn.dataset.arm = "";
        btn.classList.remove("btn-armed");
      }
      const { j } = await api("/review/toggle", {
        student_id: parseInt(row.dataset.student, 10),
        teacher_id: teacherId,
      });
      if (!j.ok) return;
      const meta = row.querySelector(".review-meta");
      const chip = row.querySelector(".status-chip");
      if (j.confirmed) {
        btn.classList.add("btn-ghost");
        btn.textContent = I18N.unconfirm || "Undo";
        meta.textContent = (j.by || "") + " · " + j.time;
        if (chip) {
          chip.className = "status-chip stc-reviewed";
          chip.textContent = I18N.stReviewed || "Reviewed";
        }
      } else {
        btn.classList.remove("btn-ghost");
        btn.textContent = I18N.confirmReview || "Confirm";
        meta.textContent = "";
        if (chip) {
          chip.className = "status-chip stc-in_progress";
          chip.textContent = I18N.stInProgress || "In progress";
        }
      }
    });
  }

  /* ---------- review page: admin batch archive ---------- */

  const batchBtn = document.getElementById("batch-archive");
  if (batchBtn) {
    batchBtn.addEventListener("click", async () => {
      batchBtn.disabled = true;
      batchBtn.textContent = batchBtn.dataset.busy;
      const r = await fetch("/report/batch/" + batchBtn.dataset.session, { method: "POST" });
      let j = {};
      try { j = await r.json(); } catch (e) { /* ignore */ }
      batchBtn.disabled = false;
      batchBtn.textContent = batchBtn.dataset.label;
      if (j.ok) {
        alert("PDF x" + j.pdf_count + (j.skipped ? " (skipped " + j.skipped + ")" : "") + " + " + j.csv_name);
        location.reload();
      } else {
        alert("Archive failed: " + (j.error || r.status));
      }
    });
  }

  /* ---------- report page: comparison cohort selector ---------- */

  const cmpSel = document.getElementById("cmp-select");
  if (cmpSel) {
    const from = document.getElementById("cmp-from");
    const to = document.getElementById("cmp-to");
    const go = () => {
      const v = cmpSel.value;
      let url = location.pathname + "?cmp=" + v;
      if (v === "range") {
        if (!from.value || !to.value) return;
        url += "&from=" + from.value + "&to=" + to.value;
      }
      location.href = url;
    };
    cmpSel.addEventListener("change", () => {
      const r = cmpSel.value === "range";
      from.style.display = to.style.display = r ? "inline-block" : "none";
      if (!r) go();
    });
    [from, to].forEach((el) => {
      if (el) el.addEventListener("change", () => { if (from.value && to.value) go(); });
    });
  }

  /* ---------- student page: deep link to a question ---------- */

  if (document.body.dataset.page === "student" && location.hash) {
    const sec = document.querySelector('.code-section[data-code="' + location.hash.slice(1) + '"]');
    if (sec) setTimeout(() => sec.scrollIntoView({ block: "start" }), 60);
  }

  /* ---------- roster drawer (student page, narrow screens) ---------- */

  const rosterToggle = document.querySelector(".roster-toggle");
  if (rosterToggle) {
    rosterToggle.addEventListener("click", () => document.body.classList.toggle("roster-open"));
    const backdrop = document.querySelector(".roster-backdrop");
    if (backdrop) backdrop.addEventListener("click", () => document.body.classList.remove("roster-open"));
  }

  /* ---------- report page ---------- */

  const printBtn = document.getElementById("print-btn");
  if (printBtn) printBtn.addEventListener("click", () => window.print());

  const aiBtn = document.getElementById("summary-ai");
  if (aiBtn) {
    aiBtn.addEventListener("click", async () => {
      const ta = document.getElementById("summary-text");
      aiBtn.disabled = true;
      aiBtn.textContent = aiBtn.dataset.busy;
      const { j } = await api("/summary/ai", {
        student_id: parseInt(document.body.dataset.student, 10),
        draft: ta.value,
      });
      aiBtn.disabled = false;
      aiBtn.textContent = aiBtn.dataset.label;
      const meta = document.getElementById("summary-meta");
      if (j.ok) {
        ta.value = j.text;
        if (meta) meta.textContent = aiBtn.dataset.done;
      } else if (j.error === "not_configured") {
        alert(aiBtn.dataset.notconf);
      } else if (j.error === "billing_error") {
        alert(aiBtn.dataset.billing);
      } else {
        alert(aiBtn.dataset.failed + (j.error || ""));
      }
    });
  }

  const pdfBtn = document.getElementById("pdf-btn");
  if (pdfBtn) {
    pdfBtn.addEventListener("click", async () => {
      pdfBtn.disabled = true;
      pdfBtn.textContent = pdfBtn.dataset.busy;
      const sid = document.body.dataset.student;
      const r = await fetch("/report/" + sid + "/pdf", { method: "POST" });
      let j = {};
      try { j = await r.json(); } catch (e) { /* ignore */ }
      pdfBtn.disabled = false;
      pdfBtn.textContent = pdfBtn.dataset.label;
      const list = document.getElementById("pdf-list");
      if (j.ok && list) {
        const none = document.getElementById("pdf-none");
        if (none) none.remove();
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = "/report/pdf/" + j.id;
        a.target = "_blank";
        a.textContent = j.filename;
        const span = document.createElement("span");
        span.className = "by";
        span.textContent = j.size_kb + " KB · " + (j.by || "") + " · " + j.time;
        li.appendChild(a);
        li.appendChild(document.createTextNode(" "));
        li.appendChild(span);
        list.prepend(li);
      } else if (!j.ok) {
        alert((list ? list.dataset.failed : "PDF failed: ") + (j.error || r.status));
      }
    });
  }

  const sumSave = document.getElementById("summary-save");
  if (sumSave) {
    sumSave.addEventListener("click", async () => {
      const ta = document.getElementById("summary-text");
      const { j } = await api("/summary/save", {
        student_id: parseInt(document.body.dataset.student, 10),
        text: ta.value,
      });
      const meta = document.getElementById("summary-meta");
      if (j.ok && meta) meta.textContent = (j.by || "") + " · " + j.time;
      const print = document.querySelector(".rp-summary-print");
      if (print) print.textContent = ta.value;
    });
  }

  /* ---------- header account switcher (admins) ---------- */

  const chipBtn = document.getElementById("user-chip");
  if (chipBtn) {
    const panel = document.getElementById("user-menu-panel");
    let loaded = false;
    chipBtn.addEventListener("click", async () => {
      panel.classList.toggle("open");
      if (loaded || !panel.classList.contains("open")) return;
      const r = await fetch("/api/teachers/switchable");
      let j = {};
      try { j = await r.json(); } catch (e) { /* ignore */ }
      if (!j.ok) return;
      panel.innerHTML = "";
      const head = document.createElement("div");
      head.className = "user-menu-head";
      head.textContent = panel.dataset.head || "Switch account";
      panel.appendChild(head);
      j.teachers.forEach((te) => {
        const f = document.createElement("form");
        f.method = "post";
        f.action = "/switch/" + te.id;
        const b = document.createElement("button");
        b.type = "submit";
        b.className = "user-menu-item";
        b.textContent = te.name;
        if (te.role === "admin") {
          const r2 = document.createElement("span");
          r2.className = "user-menu-role";
          r2.textContent = "admin";
          b.appendChild(r2);
        }
        f.appendChild(b);
        panel.appendChild(f);
      });
      loaded = true;
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".user-menu")) panel.classList.remove("open");
    });
  }

  /* ---------- grouping board ---------- */

  const gbBoard = document.querySelector(".gb-board");
  if (gbBoard) {
    let sel = null;
    let drag = null;

    function setSelected(chip) {
      document.querySelectorAll(".gb-chip.sel").forEach((c) => c.classList.remove("sel"));
      sel = chip || null;
      document.body.classList.toggle("gb-selecting", !!sel);
      if (chip) chip.classList.add("sel");
    }

    function updateCounts() {
      document.querySelectorAll(".gb-col[data-group]").forEach((c) => {
        const cnt = c.querySelector(".gb-count");
        if (cnt) cnt.textContent = c.querySelectorAll(".gb-chip").length;
      });
    }

    function refreshBanner() {
      const pool = document.querySelector('.gb-col[data-group=""]');
      const remaining = pool ? pool.querySelectorAll(".gb-chip").length : 0;
      const hasGroups = document.querySelectorAll('.gb-col[data-group]:not([data-group=""])').length > 0;
      const total = document.querySelectorAll(".gb-chip").length;
      const banner = document.getElementById("gb-banner");
      if (!banner) return;
      const ok = total > 0 && hasGroups && remaining === 0;
      banner.classList.toggle("ok", ok);
      const txt = banner.querySelector(".gb-banner-text");
      if (txt) {
        if (ok) txt.textContent = I18N.gbDone || "Grouping complete.";
        else if (!hasGroups) txt.textContent = I18N.gbNeedGroup || "Create a group first.";
        else txt.textContent = remaining + " " + (I18N.gbNotDone || "students not grouped yet.");
      }
      const start = banner.querySelector(".gb-start");
      if (start) start.classList.toggle("disabled", !ok);
    }

    async function moveChip(chip, col) {
      const fromList = chip.closest(".gb-list");
      const toList = col.querySelector(".gb-list");
      if (!toList || fromList === toList) return;
      toList.appendChild(chip);
      updateCounts();
      refreshBanner();
      const gid = col.dataset.group;
      const { j } = await api("/student/group", {
        student_id: parseInt(chip.dataset.student, 10),
        group_id: gid ? parseInt(gid, 10) : null,
      });
      if (!j.ok) {
        fromList.appendChild(chip);
        updateCounts();
        refreshBanner();
      }
    }

    gbBoard.addEventListener("click", (ev) => {
      if (ev.target.closest(".gb-handle") || ev.target.closest("select") ||
          ev.target.closest("button") || ev.target.closest("input")) return;
      const chip = ev.target.closest(".gb-chip");
      if (chip) {
        setSelected(chip === sel ? null : chip);
        return;
      }
      const col = ev.target.closest(".gb-col[data-group]");
      if (col && sel) {
        const c = sel;
        setSelected(null);
        moveChip(c, col);
      }
    });

    gbBoard.addEventListener("pointerdown", (ev) => {
      const handle = ev.target.closest(".gb-handle");
      if (!handle) return;
      const chip = handle.closest(".gb-chip");
      drag = { chip, moved: false, ghost: null };
      handle.setPointerCapture(ev.pointerId);
      ev.preventDefault();
    });

    gbBoard.addEventListener("pointermove", (ev) => {
      if (!drag) return;
      if (!drag.moved) {
        drag.moved = true;
        const g = drag.chip.cloneNode(true);
        g.classList.add("gb-ghost");
        g.style.width = drag.chip.offsetWidth + "px";
        document.body.appendChild(g);
        drag.ghost = g;
        drag.chip.classList.add("gb-dragging");
        setSelected(null);
      }
      drag.ghost.style.left = ev.clientX - 60 + "px";
      drag.ghost.style.top = ev.clientY - 20 + "px";
      document.querySelectorAll(".gb-col").forEach((c) => c.classList.remove("gb-over"));
      const el = document.elementFromPoint(ev.clientX, ev.clientY);
      const col = el && el.closest ? el.closest(".gb-col[data-group]") : null;
      if (col) col.classList.add("gb-over");
    });

    gbBoard.addEventListener("pointerup", (ev) => {
      if (!drag) return;
      const d = drag;
      drag = null;
      if (d.ghost) d.ghost.remove();
      d.chip.classList.remove("gb-dragging");
      document.querySelectorAll(".gb-col.gb-over").forEach((c) => c.classList.remove("gb-over"));
      if (d.moved) {
        const el = document.elementFromPoint(ev.clientX, ev.clientY);
        const col = el && el.closest ? el.closest(".gb-col[data-group]") : null;
        if (col) moveChip(d.chip, col);
      }
    });

    const rndBtn = document.getElementById("gb-random");
    if (rndBtn) {
      rndBtn.addEventListener("click", async () => {
        const hasGroups = document.querySelectorAll('.gb-col[data-group]:not([data-group=""])').length > 0;
        if (!hasGroups) { alert(I18N.gbNeedGroup || "Create a group first."); return; }
        if (!confirm(I18N.gbConfirmRandom || "Randomly re-assign all students?")) return;
        const { j } = await api("/groups/randomize", {
          session_id: parseInt(document.body.dataset.session, 10),
        });
        if (j.ok) location.reload();
      });
    }
  }

  /* ---------- admin selects ---------- */

  document.querySelectorAll(".student-group").forEach((sel) => {
    sel.addEventListener("change", async () => {
      const { j } = await api("/student/group", {
        student_id: parseInt(sel.dataset.student, 10),
        group_id: sel.value || null,
      });
      sel.style.outline = j.ok ? "2px solid #2e7d32" : "2px solid #b3261e";
      setTimeout(() => (sel.style.outline = ""), 900);
    });
  });

  document.querySelectorAll(".student-level").forEach((sel) => {
    sel.addEventListener("change", async () => {
      if (!sel.value) return;
      const { j } = await api("/student/level", {
        student_id: parseInt(sel.dataset.student, 10),
        level: sel.value,
      });
      if (j.ok) sel.classList.remove("lv-missing");
      sel.style.outline = j.ok ? "2px solid #2e7d32" : "2px solid #b3261e";
      setTimeout(() => (sel.style.outline = ""), 900);
    });
  });

  document.querySelectorAll(".group-teacher").forEach((sel) => {
    sel.addEventListener("change", async () => {
      const { j } = await api("/group/teacher", {
        group_id: parseInt(sel.dataset.group, 10),
        teacher_id: sel.value || null,
      });
      sel.style.outline = j.ok ? "2px solid #2e7d32" : "2px solid #b3261e";
      setTimeout(() => (sel.style.outline = ""), 900);
    });
  });
})();
