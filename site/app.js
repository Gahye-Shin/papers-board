(() => {
  const $ = (s) => document.querySelector(s);
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => n.toLocaleString("en-US");
  const PAGE = 60;

  let META = {}, PAPERS = [], NEW_CUTOFF = 0;
  const saved = new Set(store.get("pb.saved", []));
  const S = { cat: null, tier: null, flag: null, year: null, q: "", sort: "score", expanded: false, limit: PAGE };

  // theme
  const theme = store.get("pb.theme", null);
  if (theme) document.documentElement.dataset.theme = theme;
  $("#theme").onclick = () => {
    const dark = document.documentElement.dataset.theme !== "dark";
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    store.set("pb.theme", dark ? "dark" : "light");
  };

  fetch("data/board.json", { cache: "no-store" })
    .then((r) => r.json())
    .then((d) => { META = d.meta; PAPERS = d.papers; init(); })
    .catch(() => { $("#list").innerHTML = '<p class="empty">data/board.json을 불러오지 못했습니다. 먼저 파이프라인을 실행하세요.</p>'; });

  const isNew = (p) => p.added_by !== "backfill" && p.first_seen && Date.parse(p.first_seen) >= NEW_CUTOFF;
  const catLabel = (id) => (META.categories.find((c) => c.id === id) || {}).label || id;
  const tierLabel = (id) => (META.tiers.find((t) => t.id === id) || {}).label || "Other";

  function init() {
    document.title = `${META.title} · Briefing Board`;
    $("#topic").textContent = META.title;
    $("#subtitle").textContent = META.subtitle || "";
    const up = new Date(META.updated);
    $("#updated").textContent = "Updated " + up.toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" });
    const years = PAPERS.map((p) => p.year).filter(Boolean);
    $("#range").textContent = `${META.start_year || Math.min(...years)}–${Math.max(...years, up.getFullYear())}`;
    $("#journals").textContent = `${META.journal_count} journals`;
    $("#s-relevant").textContent = fmt(META.relevant_found);
    NEW_CUTOFF = up.getTime() - 7 * 864e5;
    $("#s-new").textContent = fmt(PAPERS.filter(isNew).length);

    $("#q").oninput = (e) => { S.q = e.target.value.trim().toLowerCase(); S.limit = PAGE; render(); };
    $("#sort").onchange = (e) => { S.sort = e.target.value; render(); };
    $("#collapse").onclick = () => {
      S.expanded = !S.expanded;
      $("#collapse").textContent = S.expanded ? "Collapse all" : "Expand all";
      document.querySelectorAll("details.abs").forEach((d) => (d.open = S.expanded));
    };
    $("#more").onclick = () => { S.limit += PAGE; render(); };
    render();
  }

  function matches(p, skip) {
    if (skip !== "cat" && S.cat && !p.categories.includes(S.cat)) return false;
    if (skip !== "tier" && S.tier) {
      if (S.tier === "__other" ? p.tier : p.tier !== S.tier) return false;
    }
    if (skip !== "flag" && S.flag) {
      if (S.flag === "review" && p.type !== "review") return false;
      if (S.flag === "saved" && !saved.has(p.id)) return false;
      if (S.flag === "new" && !isNew(p)) return false;
    }
    if (skip !== "year" && S.year && p.year !== S.year) return false;
    if (S.q) {
      const hay = (p._hay ||= [p.title, p.abstract, p.tldr, p.journal, p.authors.join(" "), p.doi].join(" ").toLowerCase());
      if (!S.q.split(/\s+/).every((t) => hay.includes(t))) return false;
    }
    return true;
  }

  function chip(label, count, on, onclick, dot) {
    const b = document.createElement("button");
    b.className = "chip" + (on ? " on" : "");
    b.innerHTML = (dot ? '<span class="dot"></span>' : "") + `${esc(label)} <span class="n">${count}</span>`;
    b.onclick = onclick;
    return b;
  }

  function renderChips(all) {
    const box = $("#chips"); box.innerHTML = "";
    const count = (fn, skip) => PAPERS.filter((p) => matches(p, skip) && fn(p)).length;
    const none = !S.cat && !S.tier && !S.flag && !S.year;
    box.append(chip("All", PAPERS.length, none, () => { Object.assign(S, { cat: null, tier: null, flag: null, year: null, limit: PAGE }); render(); }));
    for (const c of META.categories) {
      box.append(chip(c.label, count((p) => p.categories.includes(c.id), "cat"), S.cat === c.id,
        () => { S.cat = S.cat === c.id ? null : c.id; S.limit = PAGE; render(); }, true));
    }
    const br = document.createElement("span"); br.className = "chip-break"; box.append(br);
    for (const t of META.tiers) {
      box.append(chip(t.label, count((p) => p.tier === t.id, "tier"), S.tier === t.id,
        () => { S.tier = S.tier === t.id ? null : t.id; S.limit = PAGE; render(); }));
    }
    box.append(chip("Other journals", count((p) => !p.tier, "tier"), S.tier === "__other",
      () => { S.tier = S.tier === "__other" ? null : "__other"; S.limit = PAGE; render(); }));
    const flags = [["new", "New this week", isNew], ["review", "Reviews", (p) => p.type === "review"], ["saved", "★ Saved", (p) => saved.has(p.id)]];
    for (const [id, label, fn] of flags) {
      box.append(chip(label, count(fn, "flag"), S.flag === id, () => { S.flag = S.flag === id ? null : id; S.limit = PAGE; render(); }));
    }
  }

  function renderBars() {
    const rows = PAPERS.filter((p) => matches(p, "year"));
    const years = PAPERS.map((p) => p.year).filter(Boolean);
    if (!years.length) return;
    const y0 = META.start_year || Math.min(...years), y1 = Math.max(...years);
    const counts = {}; rows.forEach((p) => (counts[p.year] = (counts[p.year] || 0) + 1));
    const max = Math.max(1, ...Object.values(counts));
    const box = $("#bars"); box.innerHTML = "";
    box.classList.toggle("filtered", !!S.year);
    for (let y = y0; y <= y1; y++) {
      const n = counts[y] || 0;
      const b = document.createElement("button");
      b.className = "bar" + (S.year === y ? " on" : "");
      b.title = `${y}: ${n}`;
      b.innerHTML = `<small>${n}</small><i style="height:${(n / max) * 78}%"></i><em>${String(y).slice(2)}</em>`;
      b.onclick = () => { S.year = S.year === y ? null : y; S.limit = PAGE; render(); };
      box.append(b);
    }
  }

  function card(p) {
    const hi = p.lab_score >= (META.highlight_score ?? 70);
    const tier = p.tier ? `<span class="tier ${p.tier === "tier1" ? "t1" : ""}">${esc(tierLabel(p.tier).split("·")[0].trim())}</span>` : "";
    const authors = p.authors.length > 6 ? p.authors.slice(0, 6).join(", ") + " et al." : p.authors.join(", ");
    return `<article class="paper">
      <div class="meta">
        ${isNew(p) ? '<span class="badge-new">NEW</span>' : ""}
        <span class="j">${esc(p.journal || "—")}</span>${tier}
        <span>${esc(p.date || p.year || "")}</span>
        ${p.type === "review" ? "<span>Review</span>" : ""}
        <span>${fmt(p.citations)} cites</span>
        <span class="score${hi ? " hi" : ""}" title="Lab score">Lab <i style="--w:${p.lab_score}%"></i>${p.lab_score}</span>
      </div>
      <h3><button class="star${saved.has(p.id) ? " on" : ""}" data-id="${p.id}" aria-label="Save">★</button>
        <a href="${esc(p.doi ? "https://doi.org/" + p.doi : p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a></h3>
      <p class="authors">${esc(authors)}</p>
      ${p.tldr ? `<p class="tldr">${esc(p.tldr)}</p>` : ""}
      <div class="tags">${p.categories.map((c) => `<button class="tag" data-cat="${c}">${esc(catLabel(c))}</button>`).join("")}</div>
      ${p.abstract ? `<details class="abs"${S.expanded ? " open" : ""}><summary>Abstract</summary><p>${esc(p.abstract)}</p></details>` : ""}
    </article>`;
  }

  function render() {
    const rows = PAPERS.filter((p) => matches(p));
    const key = { score: (p) => [p.lab_score, p.citations], cites: (p) => [p.citations, p.lab_score], date: (p) => [p.date || "", p.lab_score] }[S.sort];
    rows.sort((a, b) => { const A = key(a), B = key(b); return A[0] < B[0] ? 1 : A[0] > B[0] ? -1 : B[1] - A[1]; });

    $("#s-shown").textContent = fmt(rows.length);
    $("#s-cites").textContent = fmt(rows.reduce((s, p) => s + p.citations, 0));
    $("#q").placeholder = `Search ${fmt(PAPERS.length)} papers…`;
    renderChips(); renderBars();

    const list = $("#list");
    list.innerHTML = rows.length ? rows.slice(0, S.limit).map(card).join("") : '<p class="empty">조건에 맞는 논문이 없습니다.</p>';
    $("#more").hidden = rows.length <= S.limit;
    $("#more").textContent = `Show more (${fmt(rows.length - S.limit)})`;

    list.querySelectorAll(".star").forEach((b) => (b.onclick = () => {
      const id = b.dataset.id;
      saved.has(id) ? saved.delete(id) : saved.add(id);
      store.set("pb.saved", [...saved]);
      b.classList.toggle("on");
      renderChips();
    }));
    list.querySelectorAll(".tag").forEach((b) => (b.onclick = () => { S.cat = b.dataset.cat; S.limit = PAGE; render(); window.scrollTo({ top: $("#chips").offsetTop - 10, behavior: "smooth" }); }));
  }
})();
