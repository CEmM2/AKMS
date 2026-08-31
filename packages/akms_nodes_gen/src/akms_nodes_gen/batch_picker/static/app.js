// AKMS Batch Picker — vanilla JS UI
// Two panes: batch tree + paper picker. Plus saved queries, compare, copy-to-batch.

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const el = (tag, attrs = {}, children = []) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "dataset") Object.assign(node.dataset, v);
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v === false || v == null) continue;
    else if (v === true) node.setAttribute(k, "");
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null) continue;
    node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return node;
};

const state = {
  batches: [],
  collections: [],
  savedQueries: [],
  selectedBatchId: null,
  selectedDetail: null,    // {batch, assignment, papers, unknown_citekeys}
  searchResults: [],
  papersById: new Map(),
  compareWith: null,
  compareData: null,       // {a,b,both,only_a,only_b,n_a,n_b}
};

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const text = await res.text();
  let body;
  try { body = text ? JSON.parse(text) : {}; }
  catch { body = { _raw: text }; }
  if (!res.ok) {
    throw new Error(body.detail || body.message || `${res.status} ${path}`);
  }
  return body;
}

// ---------------------------------------------------------------------------
// Toast / dialogs
// ---------------------------------------------------------------------------

let toastTimer = null;
function toast(msg, kind = "") {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast " + kind;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, kind === "bad" ? 8000 : 3500);
}

function confirmDialog(title, body) {
  return new Promise((resolve) => {
    $("#confirm-title").textContent = title;
    const bodyEl = $("#confirm-body");
    bodyEl.innerHTML = "";
    if (typeof body === "string") bodyEl.textContent = body;
    else bodyEl.appendChild(body);
    const dlg = $("#confirm-modal");
    const yes = $("[data-confirm-yes]", dlg);
    const no = $("[data-confirm-no]", dlg);
    const cleanup = () => {
      yes.removeEventListener("click", onYes);
      no.removeEventListener("click", onNo);
      dlg.close();
    };
    const onYes = () => { cleanup(); resolve(true); };
    const onNo = () => { cleanup(); resolve(false); };
    yes.addEventListener("click", onYes);
    no.addEventListener("click", onNo);
    dlg.showModal();
  });
}

function promptDialog(title, body, defaultValue = "") {
  return new Promise((resolve) => {
    $("#prompt-title").textContent = title;
    $("#prompt-body").textContent = body || "";
    const input = $("#prompt-input");
    input.value = defaultValue;
    const dlg = $("#prompt-modal");
    const ok = $("[data-prompt-ok]", dlg);
    const cancel = $("[data-prompt-cancel]", dlg);
    const close = $("[data-close]", dlg);
    const cleanup = () => {
      ok.removeEventListener("click", onOk);
      cancel.removeEventListener("click", onCancel);
      close.removeEventListener("click", onCancel);
      input.removeEventListener("keydown", onKey);
      dlg.close();
    };
    const onOk = () => { const v = input.value.trim(); cleanup(); resolve(v || null); };
    const onCancel = () => { cleanup(); resolve(null); };
    const onKey = (e) => {
      if (e.key === "Enter") onOk();
      if (e.key === "Escape") onCancel();
    };
    ok.addEventListener("click", onOk);
    cancel.addEventListener("click", onCancel);
    close.addEventListener("click", onCancel);
    input.addEventListener("keydown", onKey);
    dlg.showModal();
    setTimeout(() => input.focus(), 0);
  });
}

// ---------------------------------------------------------------------------
// Batches pane
// ---------------------------------------------------------------------------

function renderBatchList() {
  const filter = $("#batch-filter").value.trim().toLowerCase();
  const list = $("#batches-list");
  list.innerHTML = "";

  const byRound = new Map();
  for (const b of state.batches) {
    const matches = !filter
      || b.id.toLowerCase().includes(filter)
      || (b.title || "").toLowerCase().includes(filter)
      || (b.round_title || "").toLowerCase().includes(filter);
    if (!matches) continue;
    if (!byRound.has(b.round)) byRound.set(b.round, []);
    byRound.get(b.round).push(b);
  }

  const rounds = Array.from(byRound.keys()).sort((a, b) => a - b);
  for (const r of rounds) {
    const items = byRound.get(r);
    const roundTitle = items[0]?.round_title || "";
    list.appendChild(el("div", { class: "round-group" }, `R${r} — ${roundTitle}`));
    for (const b of items) {
      const cls = ["batch-item"];
      if (b.id === state.selectedBatchId) cls.push("active");
      if (b.id === state.compareWith) cls.push("compare-target");
      const item = el("div", {
        class: cls.join(" "),
        dataset: { id: b.id },
        onclick: () => selectBatch(b.id),
      }, [
        el("div", { class: "row1" }, [
          el("span", { class: "id" }, b.id),
          batchStatusBadge(b),
        ]),
        el("div", { class: "row1" }, [el("span", {}, b.title)]),
        el("div", { class: "row2" }, [
          `${b.n_assigned || 0} papers`,
          `${b.n_nodes_parsed}/${b.node_count} nodes`,
          b.has_notebook ? `nb ✓ (${b.n_uploaded || 0} up)` : "no nb",
        ].map(s => el("span", {}, s))),
      ]);
      list.appendChild(item);
    }
  }
}

function batchStatusBadge(b) {
  if (b.has_notebook && b.n_uploaded >= b.n_assigned && b.n_assigned > 0) {
    return el("span", { class: "badge good" }, "synced");
  }
  if (b.has_notebook) return el("span", { class: "badge warn" }, "partial");
  if (b.n_assigned > 0) return el("span", { class: "badge warn" }, "ready");
  return el("span", { class: "badge" }, "empty");
}

// ---------------------------------------------------------------------------
// Batch detail
// ---------------------------------------------------------------------------

async function selectBatch(id) {
  state.selectedBatchId = id;
  // Switching batches resets compare unless target is still valid.
  if (state.compareWith === id) state.compareWith = null;
  renderBatchList();
  const detail = await api(`/api/batches/${id}`);
  state.selectedDetail = detail;
  for (const p of detail.papers) state.papersById.set(p.citekey, p);
  populateCompareSelect();
  renderBatchDetail();
  if (state.compareWith) await refreshCompare();
  await runPaperSearch();
}

function renderBatchDetail() {
  const d = state.selectedDetail;
  if (!d) return;
  $("#batch-empty").hidden = true;
  $("#batch-view").hidden = false;

  const b = d.batch;
  $("#bh-title").textContent = `${b.id} — ${b.title}`;
  $("#bh-meta").textContent = `Round ${b.round}: ${b.round_title} · ${b.nodes.length}/${b.node_count} nodes parsed · slug=${b.pdf_slug || "—"}`;
  $("#bh-sources").textContent = b.sources_text || "—";
  $("#bh-zotsums").textContent = b.zotsums_text || "—";
  $("#bh-missing").textContent = b.missing_text || "—";
  $("#bh-notebook").textContent = d.assignment.nlm_notebook_id || "—";
  $("#bh-synced").textContent = d.assignment.synced_at || "never";
  $("#bh-uploaded").textContent =
    `${d.assignment.uploaded_papers.length} / ${d.assignment.papers.length}`;

  const tbody = $("#nodes-table tbody");
  tbody.innerHTML = "";
  b.nodes.forEach((n, i) => {
    tbody.appendChild(el("tr", {}, [
      el("td", {}, String(i + 1)),
      el("td", {}, el("code", {}, n.node_id)),
      el("td", {}, n.title),
      el("td", {}, n.size || ""),
    ]));
  });

  $("#assigned-count").textContent = String(d.papers.length);
  const list = $("#assigned-list");
  list.innerHTML = "";
  if (d.papers.length === 0) {
    list.appendChild(el("span", { class: "muted" }, "No papers yet — pick from the search below."));
  } else {
    for (const p of d.papers) {
      const pill = el("span", {
        class: "paper-pill" + (p.has_pdf ? "" : " no-pdf"),
        title: p.title,
      }, [
        el("span", {}, p.citekey),
        el("button", {
          class: "send",
          title: "Copy / move to another batch",
          onclick: (e) => { e.stopPropagation(); openCopyTarget([p.citekey], { source: d.batch.id }); },
        }, "→"),
        el("button", {
          class: "x",
          title: "remove",
          onclick: () => removePaperFromBatch(p.citekey),
        }, "×"),
      ]);
      list.appendChild(pill);
    }
  }
  for (const ck of d.unknown_citekeys) {
    list.appendChild(el("span", {
      class: "paper-pill no-pdf",
      title: "Citekey not found in BBT JSON",
    }, [
      el("span", {}, ck),
      el("button", { class: "x", onclick: () => removePaperFromBatch(ck) }, "×"),
    ]));
  }

  const haveAssign = d.papers.length > 0;
  $("#btn-export-plan").disabled = !haveAssign;
  $("#btn-stage-pdfs").disabled = !haveAssign;
  $("#btn-create-notebook").disabled = !haveAssign;
}

// ---------------------------------------------------------------------------
// Paper search / picker
// ---------------------------------------------------------------------------

function currentFilter() {
  return {
    q: $("#paper-search").value.trim(),
    collection: Array.from($("#collection-filter").selectedOptions).map(o => o.value),
    year_from: $("#year-from").value ? parseInt($("#year-from").value, 10) : null,
    year_to: $("#year-to").value ? parseInt($("#year-to").value, 10) : null,
    item_type: $("#type-filter").value,
    only_with_pdf: $("#only-pdf").checked,
    suggest_for: $("#suggest-toggle").checked && state.selectedBatchId ? state.selectedBatchId : "",
  };
}

function applyFilterToToolbar(f) {
  $("#paper-search").value = f.q || "";
  const colSel = $("#collection-filter");
  const wanted = new Set(f.collection || []);
  for (const opt of colSel.options) opt.selected = wanted.has(opt.value);
  $("#year-from").value = f.year_from ?? "";
  $("#year-to").value = f.year_to ?? "";
  $("#type-filter").value = f.item_type || "";
  $("#only-pdf").checked = !!f.only_with_pdf;
  // suggest_for is intentionally always tied to the current batch — set toggle if any value was saved
  $("#suggest-toggle").checked = !!f.suggest_for;
}

async function runPaperSearch() {
  const f = currentFilter();
  const params = new URLSearchParams();
  if (f.q) params.set("q", f.q);
  for (const c of f.collection) params.append("collection", c);
  if (f.year_from) params.set("year_from", f.year_from);
  if (f.year_to) params.set("year_to", f.year_to);
  if (f.item_type) params.set("item_type", f.item_type);
  if (f.only_with_pdf) params.set("only_with_pdf", "true");
  if (f.suggest_for) params.set("suggest_for", f.suggest_for);
  params.set("limit", "300");

  const res = await api(`/api/papers?${params.toString()}`);
  state.searchResults = res.results;
  for (const p of res.results) state.papersById.set(p.citekey, p);

  $("#search-stats").textContent = `${res.results.length} shown / ${res.total} match`;
  $("#btn-bulk-add").disabled = !state.selectedBatchId || res.total === 0;

  renderPaperTable();
}

function renderPaperTable() {
  const tbody = $("#papers-table tbody");
  tbody.innerHTML = "";

  const assignedSet = new Set(
    (state.selectedDetail?.papers || []).map(p => p.citekey)
  );

  const frag = document.createDocumentFragment();
  for (const p of state.searchResults) {
    const isAssigned = assignedSet.has(p.citekey);
    const elsewhere = (p.assigned_to || []).filter(b => b !== state.selectedBatchId);

    const tr = el("tr", {
      class: isAssigned ? "assigned" : (elsewhere.length ? "assigned-elsewhere" : ""),
      dataset: { citekey: p.citekey },
    }, [
      el("td", {}, el("input", {
        type: "checkbox",
        checked: isAssigned ? true : false,
        onchange: (e) => togglePaper(p.citekey, e.target.checked),
      })),
      el("td", {}, el("span", {
        class: "cit",
        onclick: () => showPaperModal(p.citekey),
      }, p.citekey)),
      el("td", {
        title: p.title,
      }, p.title.length > 80 ? p.title.slice(0, 78) + "…" : p.title),
      el("td", {}, p.year || ""),
      el("td", {
        title: p.authors.join("; ") + (p.n_authors > p.authors.length ? ` (+${p.n_authors - p.authors.length})` : ""),
      }, (p.authors[0] || "").split(",")[0] + (p.n_authors > 1 ? " et al." : "")),
      el("td", {}, (p.collections || []).slice(0, 3).join(", ")),
      el("td", {}, (p.keywords || []).slice(0, 4).map(k => el("span", { class: "kw" }, k))),
      el("td", {}, p.has_pdf ? "✓" : ""),
      el("td", {}, elsewhere.length ? elsewhere.join(", ") : ""),
      el("td", {}, p.score > 0 ? String(p.score) : ""),
      el("td", {}, el("button", {
        class: "icon-btn",
        title: "Copy / move to another batch",
        onclick: (e) => { e.stopPropagation(); openCopyTarget([p.citekey]); },
      }, "→")),
    ]);
    frag.appendChild(tr);
  }
  tbody.appendChild(frag);
}

async function togglePaper(citekey, checked) {
  const d = state.selectedDetail;
  if (!d) return;
  if (checked) {
    await api(`/api/batches/${d.batch.id}/papers/add`, {
      method: "POST",
      body: JSON.stringify({ citekeys: [citekey] }),
    });
  } else {
    await api(`/api/batches/${d.batch.id}/papers/remove`, {
      method: "POST",
      body: JSON.stringify({ citekeys: [citekey] }),
    });
  }
  await selectBatch(d.batch.id);
  await refreshBatches();
}

async function removePaperFromBatch(citekey) {
  const d = state.selectedDetail;
  if (!d) return;
  await api(`/api/batches/${d.batch.id}/papers/remove`, {
    method: "POST",
    body: JSON.stringify({ citekeys: [citekey] }),
  });
  await selectBatch(d.batch.id);
  await refreshBatches();
}

// ---------------------------------------------------------------------------
// Saved queries
// ---------------------------------------------------------------------------

async function loadSavedQueries() {
  state.savedQueries = await api("/api/saved_queries");
  const sel = $("#saved-select");
  const prev = sel.value;
  sel.innerHTML = "";
  sel.appendChild(el("option", { value: "" }, "— none —"));
  for (const q of state.savedQueries) {
    sel.appendChild(el("option", { value: q.name }, q.name));
  }
  if (state.savedQueries.some(q => q.name === prev)) sel.value = prev;
  updateSavedButtons();
}

function updateSavedButtons() {
  const v = $("#saved-select").value;
  $("#btn-apply-saved").disabled = !v;
  $("#btn-delete-saved").disabled = !v;
}

async function saveCurrentQuery() {
  const name = await promptDialog(
    "Save current filter as…",
    "Pick a name. Re-using an existing name overwrites that query.",
    ""
  );
  if (!name) return;
  const filter = currentFilter();
  await api(`/api/saved_queries/${encodeURIComponent(name)}`, {
    method: "PUT",
    body: JSON.stringify({ filter }),
  });
  await loadSavedQueries();
  $("#saved-select").value = name;
  updateSavedButtons();
  toast(`Saved query "${name}"`, "good");
}

async function applySavedQuery() {
  const name = $("#saved-select").value;
  if (!name) return;
  const q = state.savedQueries.find(x => x.name === name);
  if (!q) return;
  applyFilterToToolbar(q.filter);
  await runPaperSearch();
  toast(`Applied "${name}"`, "good");
}

async function deleteSavedQuery() {
  const name = $("#saved-select").value;
  if (!name) return;
  const ok = await confirmDialog("Delete saved query?", `Delete "${name}"? This cannot be undone.`);
  if (!ok) return;
  await api(`/api/saved_queries/${encodeURIComponent(name)}`, { method: "DELETE" });
  await loadSavedQueries();
  toast(`Deleted "${name}"`, "good");
}

// ---------------------------------------------------------------------------
// Bulk add (current filter → current batch)
// ---------------------------------------------------------------------------

async function bulkAddToBatch() {
  const id = state.selectedBatchId;
  if (!id) return;
  const mode = $("#bulk-mode").value;
  const filter = currentFilter();

  const stats = $("#search-stats").textContent;
  const ok = await confirmDialog(
    mode === "replace" ? "Replace batch with current filter?" : "Add all matching to batch?",
    `${stats}\nMode: ${mode === "replace" ? "REPLACE (drops existing)" : "ADD (union)"}`
  );
  if (!ok) return;

  try {
    const res = await api(`/api/batches/${id}/bulk_add`, {
      method: "POST",
      body: JSON.stringify({ filter, mode, limit: 1000 }),
    });
    toast(
      `${mode}: ${res.n_added} added, ${res.n_removed || 0} removed (matched ${res.n_matched})`,
      "good"
    );
    await selectBatch(id);
    await refreshBatches();
  } catch (e) {
    toast("bulk_add failed: " + e.message, "bad");
  }
}

// ---------------------------------------------------------------------------
// Compare panel
// ---------------------------------------------------------------------------

function populateCompareSelect() {
  const sel = $("#compare-select");
  const cur = state.compareWith;
  sel.innerHTML = "";
  sel.appendChild(el("option", { value: "" }, "— pick —"));
  for (const b of state.batches) {
    if (b.id === state.selectedBatchId) continue;
    sel.appendChild(el("option", { value: b.id }, `${b.id} — ${b.title} (${b.n_assigned})`));
  }
  if (cur && state.batches.some(b => b.id === cur)) sel.value = cur;
  $("#btn-clear-compare").hidden = !cur;
}

async function setCompareWith(other) {
  state.compareWith = other || null;
  $("#btn-clear-compare").hidden = !other;
  if (!other) {
    state.compareData = null;
    $("#compare-panel").hidden = true;
    renderBatchList();
    return;
  }
  await refreshCompare();
  renderBatchList();
}

async function refreshCompare() {
  const a = state.selectedBatchId;
  const b = state.compareWith;
  if (!a || !b) return;
  state.compareData = await api(`/api/batches/${a}/compare/${b}`);
  renderComparePanel();
}

function renderComparePanel() {
  const d = state.compareData;
  if (!d) { $("#compare-panel").hidden = true; return; }
  $("#compare-panel").hidden = false;
  $("#cmp-a-id").textContent = d.a;
  $("#cmp-b-id").textContent = d.b;
  for (const e of $$(".cmp-a")) e.textContent = d.a;
  for (const e of $$(".cmp-b")) e.textContent = d.b;
  $("#cmp-stats").textContent = `${d.n_a} vs ${d.n_b} · both ${d.both.length}`;
  $("#cmp-only-a-count").textContent = d.only_a.length;
  $("#cmp-only-b-count").textContent = d.only_b.length;
  $("#cmp-both-count").textContent = d.both.length;

  const fillList = (containerId, items, withCheckbox) => {
    const c = $(containerId);
    c.innerHTML = "";
    if (items.length === 0) {
      c.appendChild(el("div", { class: "muted small" }, "(empty)"));
      return;
    }
    for (const it of items) {
      const row = el("div", { class: "compare-row-item", dataset: { citekey: it.citekey } });
      if (withCheckbox) {
        row.appendChild(el("input", { type: "checkbox", class: "cmp-check" }));
      }
      row.appendChild(el("span", {
        class: "cit",
        onclick: () => showPaperModal(it.citekey),
        title: it.title,
      }, it.citekey));
      const meta = `${it.year || "?"}${it.has_pdf ? "" : " · no PDF"}`;
      row.appendChild(el("span", { class: "muted small" }, meta));
      c.appendChild(row);
    }
  };

  fillList("#cmp-only-a-list", d.only_a, true);
  fillList("#cmp-both-list", d.both, false);
  fillList("#cmp-only-b-list", d.only_b, true);

  for (const cb of $$('[data-cmp-select-all]')) {
    cb.checked = false;
  }
}

function getCheckedFromList(containerId) {
  return $$(`${containerId} .compare-row-item`)
    .filter(row => row.querySelector("input.cmp-check")?.checked)
    .map(row => row.dataset.citekey);
}

async function compareAction(action) {
  const d = state.compareData;
  if (!d) return;
  let target, source, citekeys;
  switch (action) {
    case "move-a-to-b":
      citekeys = getCheckedFromList("#cmp-only-a-list");
      if (!citekeys.length) return toast("Nothing checked in 'only in A'", "warn");
      await api(`/api/batches/${d.b}/papers/move`, {
        method: "POST",
        body: JSON.stringify({ from_batch: d.a, citekeys }),
      });
      toast(`Moved ${citekeys.length} → ${d.b}`, "good");
      break;
    case "remove-a":
      citekeys = getCheckedFromList("#cmp-only-a-list");
      if (!citekeys.length) return toast("Nothing checked", "warn");
      const ok = await confirmDialog(
        "Remove from current batch?",
        `Drop ${citekeys.length} papers from ${d.a}? They stay in your library.`
      );
      if (!ok) return;
      await api(`/api/batches/${d.a}/papers/remove`, {
        method: "POST",
        body: JSON.stringify({ citekeys }),
      });
      toast(`Removed ${citekeys.length} from ${d.a}`, "good");
      break;
    case "copy-b-to-a":
      citekeys = getCheckedFromList("#cmp-only-b-list");
      if (!citekeys.length) return toast("Nothing checked in 'only in B'", "warn");
      await api(`/api/batches/${d.a}/papers/add`, {
        method: "POST",
        body: JSON.stringify({ citekeys }),
      });
      toast(`Copied ${citekeys.length} from ${d.b} → ${d.a}`, "good");
      break;
    case "move-b-to-a":
      citekeys = getCheckedFromList("#cmp-only-b-list");
      if (!citekeys.length) return toast("Nothing checked in 'only in B'", "warn");
      await api(`/api/batches/${d.a}/papers/move`, {
        method: "POST",
        body: JSON.stringify({ from_batch: d.b, citekeys }),
      });
      toast(`Moved ${citekeys.length} ${d.b} → ${d.a}`, "good");
      break;
    default: return;
  }
  await selectBatch(state.selectedBatchId);
  await refreshBatches();
}

// ---------------------------------------------------------------------------
// Copy-target popover (dialog-based)
// ---------------------------------------------------------------------------

let copyTargetCtx = null;

function openCopyTarget(citekeys, opts = {}) {
  copyTargetCtx = { citekeys, source: opts.source || state.selectedBatchId };
  renderCopyTargetList();
  $("#copy-target-filter").value = "";
  $("#copy-target-modal").showModal();
  setTimeout(() => $("#copy-target-filter").focus(), 0);
}

function renderCopyTargetList() {
  const filter = $("#copy-target-filter").value.trim().toLowerCase();
  const list = $("#copy-target-list");
  list.innerHTML = "";
  if (!copyTargetCtx) return;
  const { citekeys, source } = copyTargetCtx;
  const noun = citekeys.length === 1 ? "paper" : `${citekeys.length} papers`;

  for (const b of state.batches) {
    if (filter && !(`${b.id} ${b.title}`.toLowerCase().includes(filter))) continue;
    const isSource = b.id === source;
    const row = el("div", {
      class: "ct-row" + (isSource ? " disabled" : ""),
      title: isSource ? "this is the source batch" : `Click: copy ${noun}. Shift+click: move ${noun}.`,
      onclick: (e) => {
        if (isSource) return;
        copyToBatch(b.id, citekeys, { move: e.shiftKey, source });
      },
    }, [
      el("span", {}, [
        el("span", { class: "ct-id" }, b.id),
        " ",
        el("span", {}, b.title),
      ]),
      el("span", { class: "ct-meta" }, `${b.n_assigned} papers${isSource ? " · current" : ""}`),
    ]);
    list.appendChild(row);
  }
}

async function copyToBatch(targetId, citekeys, { move = false, source = null } = {}) {
  $("#copy-target-modal").close();
  try {
    if (move) {
      const from = source || state.selectedBatchId;
      if (!from) return toast("No source batch — cannot move", "bad");
      if (from === targetId) return toast("Source equals target", "warn");
      await api(`/api/batches/${targetId}/papers/move`, {
        method: "POST",
        body: JSON.stringify({ from_batch: from, citekeys }),
      });
      toast(`Moved ${citekeys.length} → ${targetId}`, "good");
    } else {
      await api(`/api/batches/${targetId}/papers/add`, {
        method: "POST",
        body: JSON.stringify({ citekeys }),
      });
      toast(`Copied ${citekeys.length} → ${targetId}`, "good");
    }
    await selectBatch(state.selectedBatchId);
    await refreshBatches();
  } catch (e) {
    toast("Copy/move failed: " + e.message, "bad");
  }
}

// ---------------------------------------------------------------------------
// Paper modal
// ---------------------------------------------------------------------------

async function showPaperModal(citekey) {
  const p = await api(`/api/papers/${encodeURIComponent(citekey)}`);
  $("#modal-title").textContent = `${p.citekey} — ${p.title}`;
  const body = $("#modal-body");
  body.innerHTML = "";

  const block = (label, value) => {
    if (!value) return null;
    return el("div", { class: "section-block" }, [
      el("h4", {}, label),
      typeof value === "string" ? el("div", {}, value) : value,
    ]);
  };

  body.appendChild(el("p", { class: "muted" },
    `${p.year || "n.d."} · ${p.item_type || ""} · ${(p.authors || []).join("; ") || "no authors"}`));

  if (p.publication) body.appendChild(block("Publication", p.publication));
  if (p.doi) body.appendChild(block("DOI", el("a", { href: `https://doi.org/${p.doi}`, target: "_blank" }, p.doi)));
  if (p.url) body.appendChild(block("URL", el("a", { href: p.url, target: "_blank" }, p.url)));
  if ((p.collections || []).length) body.appendChild(block("Collections", p.collections.join(", ")));
  if ((p.keywords || []).length) body.appendChild(block("ZotSums keywords", el("div", {}, p.keywords.map(k => el("span", { class: "kw" }, k)))));
  if ((p.tags || []).length) body.appendChild(block("Zotero tags", el("div", {}, p.tags.map(k => el("span", { class: "kw" }, k)))));
  if (p.abstract) body.appendChild(block("Abstract", p.abstract));
  for (const k of ["Problem", "Methods", "Key Findings", "Limitations"]) {
    if (p.summary && p.summary[k]) body.appendChild(block(k, p.summary[k]));
  }
  if (p.pdf_path) body.appendChild(block("PDF", el("code", {}, p.pdf_path)));

  $("#paper-modal").showModal();
}

// ---------------------------------------------------------------------------
// Pipeline action buttons
// ---------------------------------------------------------------------------

async function exportPlan() {
  const id = state.selectedBatchId;
  if (!id) return;
  try {
    const res = await api(`/api/batches/${id}/export_plan`, { method: "POST" });
    toast(`Wrote plan JSON: ${res.path}`, "good");
  } catch (e) {
    toast("export_plan failed: " + e.message, "bad");
  }
}

async function stagePdfs() {
  const id = state.selectedBatchId;
  if (!id) return;
  try {
    const res = await api(`/api/batches/${id}/stage_pdfs`, {
      method: "POST",
      body: JSON.stringify({ use_symlink: true }),
    });
    let msg = `${res.message}\n${res.staged.length} staged`;
    if (res.skipped.length) msg += `\n${res.skipped.length} skipped`;
    toast(msg, res.skipped.length ? "warn" : "good");
  } catch (e) {
    toast("stage_pdfs failed: " + e.message, "bad");
  }
}

async function createNotebook() {
  const id = state.selectedBatchId;
  const d = state.selectedDetail;
  if (!id || !d) return;
  const ok = await confirmDialog(
    "Create NLM notebook?",
    `Will run nlm to ${d.assignment.nlm_notebook_id ? "reuse notebook " + d.assignment.nlm_notebook_id : "create a new notebook"} ` +
    `and upload ${d.papers.length} PDFs (--wait off; nlm processes them in background). ` +
    `Continue?`
  );
  if (!ok) return;
  toast("Calling nlm… (may take a minute per PDF)", "good");
  try {
    const res = await api(`/api/batches/${id}/create_notebook`, {
      method: "POST",
      body: JSON.stringify({ upload: true, wait: false }),
    });
    toast(res.message + (res.notebook_id ? `\nnotebook: ${res.notebook_id}` : ""), res.ok ? "good" : "bad");
    await selectBatch(id);
    await refreshBatches();
  } catch (e) {
    toast("create_notebook failed: " + e.message, "bad");
  }
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

async function refreshBatches() {
  state.batches = await api("/api/batches");
  renderBatchList();
  populateCompareSelect();
  if (state.selectedDetail) {
    // Patch n_assigned/n_uploaded counts in the detail header
    const card = state.batches.find(b => b.id === state.selectedDetail.batch.id);
    if (card) {
      $("#bh-meta").textContent =
        `Round ${card.round}: ${card.round_title} · ${state.selectedDetail.batch.nodes.length}/${card.node_count} nodes · slug=${card.pdf_slug || "—"}`;
    }
  }
}

async function loadCollections() {
  state.collections = await api("/api/collections");
  const sel = $("#collection-filter");
  sel.innerHTML = "";
  for (const c of state.collections) {
    const label = c.parent_name ? `${c.parent_name} / ${c.name} (${c.paper_count})` : `${c.name} (${c.paper_count})`;
    sel.appendChild(el("option", { value: c.name }, label));
  }
}

async function loadConfig() {
  const cfg = await api("/api/config");
  $("#config-summary").textContent =
    `plan: ${cfg.plan_md.split("/").pop()} · state: ${cfg.state_file.split("/").pop()}`;
}

async function reloadAll() {
  toast("Reloading data…");
  const r = await api("/api/reload", { method: "POST" });
  toast(`Reloaded: ${r.papers} papers, ${r.collections} collections, ${r.batches} batches, ${r.saved_queries} queries`, "good");
  await Promise.all([loadCollections(), refreshBatches(), loadSavedQueries()]);
  if (state.selectedBatchId) await selectBatch(state.selectedBatchId);
}

function bindEvents() {
  $("#btn-reload").addEventListener("click", reloadAll);
  $("#btn-export-plan").addEventListener("click", exportPlan);
  $("#btn-stage-pdfs").addEventListener("click", stagePdfs);
  $("#btn-create-notebook").addEventListener("click", createNotebook);
  $("#btn-search").addEventListener("click", runPaperSearch);
  $("#paper-search").addEventListener("keydown", (e) => { if (e.key === "Enter") runPaperSearch(); });
  $("#batch-filter").addEventListener("input", renderBatchList);

  // Saved queries
  $("#saved-select").addEventListener("change", updateSavedButtons);
  $("#btn-apply-saved").addEventListener("click", applySavedQuery);
  $("#btn-save-query").addEventListener("click", saveCurrentQuery);
  $("#btn-delete-saved").addEventListener("click", deleteSavedQuery);

  // Bulk add
  $("#btn-bulk-add").addEventListener("click", bulkAddToBatch);

  // Compare
  $("#compare-select").addEventListener("change", (e) => setCompareWith(e.target.value));
  $("#btn-clear-compare").addEventListener("click", () => setCompareWith(""));
  for (const btn of $$('[data-cmp-action]')) {
    btn.addEventListener("click", () => compareAction(btn.dataset.cmpAction));
  }
  for (const cb of $$('[data-cmp-select-all]')) {
    cb.addEventListener("change", (e) => {
      const which = cb.dataset.cmpSelectAll;
      const containerId = which === "only_a" ? "#cmp-only-a-list" : "#cmp-only-b-list";
      for (const inp of $$(`${containerId} input.cmp-check`)) inp.checked = e.target.checked;
    });
  }

  // Copy-target popover
  $("#copy-target-filter").addEventListener("input", renderCopyTargetList);
  for (const dlg of $$("dialog")) {
    for (const closer of $$('[data-close]', dlg)) {
      closer.addEventListener("click", () => dlg.close());
    }
    dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  }

  // Live filter changes auto-search
  for (const id of ["#collection-filter", "#year-from", "#year-to", "#type-filter", "#only-pdf", "#suggest-toggle"]) {
    $(id).addEventListener("change", runPaperSearch);
  }
}

async function boot() {
  bindEvents();
  await loadConfig();
  await Promise.all([loadCollections(), refreshBatches(), loadSavedQueries()]);
}

boot().catch(e => toast("Boot failed: " + e.message, "bad"));
