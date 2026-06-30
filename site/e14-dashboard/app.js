const state = {
  data: null,
  filters: {
    round: "segunda",
    validationMode: "fallback5",
    zone: "all",
    stand: "all",
    bucket: "all",
    minRows: 1,
    search: "",
  },
  sort: { key: "rows", direction: "desc" },
  charts: {},
};

const bucketOrder = [
  "Mesa unica",
  "0-10% mesas mas adultas",
  "10-25% mesas adultas",
  "25-50% intermedio adulto",
  "50-75% intermedio joven",
  "75-90% mesas jovenes",
  "90-100% mesas mas jovenes",
];

const fmt = new Intl.NumberFormat("es-CO");
const pctFmt = new Intl.NumberFormat("es-CO", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function $(id) {
  return document.getElementById(id);
}

function currentRound() {
  return state.data.rounds[state.filters.round];
}

function pct(value) {
  return value == null || Number.isNaN(value) ? "-" : `${pctFmt.format(value)}%`;
}

function share(numerator, denominator) {
  return denominator ? (numerator / denominator) * 100 : null;
}

function summarize(rows) {
  const total = rows.reduce((acc, row) => {
    acc.ic += row.ic;
    acc.ad += row.ad;
    acc.candidateVotes += row.candidateVotes;
    if (row.adPct != null && row.adPct > 35) acc.adOver35Rows += 1;
    return acc;
  }, { rows: rows.length, ic: 0, ad: 0, candidateVotes: 0, adOver35Rows: 0 });
  total.icPct = share(total.ic, total.candidateVotes);
  total.adPct = share(total.ad, total.candidateVotes);
  total.marginIc = share(total.ic - total.ad, total.candidateVotes);
  return total;
}

function validRows() {
  return currentRound().rows.filter((row) => row[state.filters.validationMode]);
}

function filteredRows() {
  return validRows().filter((row) => {
    if (state.filters.zone !== "all" && row.zoneCode !== state.filters.zone) return false;
    if (state.filters.stand !== "all" && `${row.zoneCode}|${row.standCode}|${row.standName}` !== state.filters.stand) return false;
    if (state.filters.bucket !== "all" && row.relativeBucket !== state.filters.bucket) return false;
    return true;
  });
}

function groupBy(rows, keyFn) {
  const groups = new Map();
  rows.forEach((row) => {
    const key = keyFn(row);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  });
  return groups;
}

function aggregate(rows, keyFn, shapeFn) {
  return Array.from(groupBy(rows, keyFn), ([key, group]) => ({ ...shapeFn(key, group), ...summarize(group) }));
}

function colorForIc(icPct) {
  const clamped = Math.max(20, Math.min(80, icPct || 50));
  const hue = clamped >= 50 ? 198 : 22;
  const sat = Math.round(45 + Math.abs(clamped - 50) * 1.1);
  const light = Math.round(45 - Math.abs(clamped - 50) * 0.35);
  return `hsl(${hue} ${sat}% ${light}%)`;
}

function roundLabel() {
  return currentRound().title;
}

function updateRoundCopy() {
  $("roundEyebrow").textContent = `${roundLabel()} presidencial · Bogota`;
  $("roundScope").textContent = `Alcance actual: solo Bogota D.C. · ${fmt.format(currentRound().allRows)} formularios descargados para ${roundLabel().toLowerCase()}.`;
  $("downloadRecommended").href = `./downloads/${currentRound().downloads.recommended}`;
  $("downloadFull").href = `./downloads/${currentRound().downloads.all}`;
}

function populateRoundFilter() {
  const order = state.data.metadata.roundOrder || Object.keys(state.data.rounds);
  $("roundFilter").innerHTML = order
    .map((key) => `<option value="${key}">${state.data.rounds[key].title}</option>`)
    .join("");
  $("roundFilter").value = state.filters.round;
}

function populateValidationFilter() {
  const round = currentRound();
  $("validationMode").innerHTML = Object.entries(round.validationModes)
    .map(([key, label]) => `<option value="${key}">${label}</option>`)
    .join("");
  if (!round.validationModes[state.filters.validationMode]) {
    state.filters.validationMode = round.recommendedMode;
  }
  $("validationMode").value = state.filters.validationMode;
}

function populateFilters() {
  const rows = currentRound().rows;
  const zones = aggregate(rows, (row) => row.zoneCode, (key, group) => ({
    zoneCode: key,
    zoneName: group[0].zoneName,
  })).sort((a, b) => a.zoneCode.localeCompare(b.zoneCode, "es", { numeric: true }));

  $("zoneFilter").innerHTML = `<option value="all">Todas</option>` + zones
    .map((zone) => `<option value="${zone.zoneCode}">Zona ${zone.zoneCode}</option>`)
    .join("");
  $("zoneFilter").value = state.filters.zone;

  $("bucketFilter").innerHTML = `<option value="all">Todas</option>` + bucketOrder
    .map((bucket) => `<option value="${bucket}">${bucket}</option>`)
    .join("");
  $("bucketFilter").value = state.filters.bucket;

  updateStandFilter();
}

function updateStandFilter() {
  const rows = currentRound().rows;
  const stands = aggregate(
    rows.filter((row) => state.filters.zone === "all" || row.zoneCode === state.filters.zone),
    (row) => `${row.zoneCode}|${row.standCode}|${row.standName}`,
    (key, group) => ({
      key,
      zoneCode: group[0].zoneCode,
      standCode: group[0].standCode,
      standName: group[0].standName,
    }),
  ).sort((a, b) => {
    const zoneCompare = a.zoneCode.localeCompare(b.zoneCode, "es", { numeric: true });
    if (zoneCompare !== 0) return zoneCompare;
    return a.standCode.localeCompare(b.standCode, "es", { numeric: true });
  });

  $("standFilter").innerHTML = `<option value="all">Todos</option>` + stands
    .map((stand) => `<option value="${stand.key}">${stand.zoneCode}-${stand.standCode} · ${stand.standName}</option>`)
    .join("");
  $("standFilter").value = state.filters.stand;
}

function updateMetrics(rows) {
  const summary = summarize(rows);
  $("metricRows").textContent = fmt.format(summary.rows);
  $("metricCoverage").textContent = pct(share(summary.rows, currentRound().allRows));
  $("metricIc").textContent = pct(summary.icPct);
  $("metricAd").textContent = pct(summary.adPct);
  $("metricMargin").textContent = pct(summary.marginIc);
  $("metricAdOver35").textContent = fmt.format(summary.adOver35Rows);
}

function renderChart(id, labels, icData, adData) {
  if (state.charts[id]) state.charts[id].destroy();
  state.charts[id] = new Chart($(id), {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "IC",
          data: icData,
          borderColor: "#1c6b84",
          backgroundColor: "rgba(28, 107, 132, 0.12)",
          tension: 0.25,
        },
        {
          label: "AD",
          data: adData,
          borderColor: "#df6f2d",
          backgroundColor: "rgba(223, 111, 45, 0.12)",
          tension: 0.25,
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { intersect: false, mode: "index" },
      scales: {
        y: {
          min: 0,
          max: 100,
          ticks: { callback: (value) => `${value}%` },
        },
      },
      plugins: {
        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${pct(ctx.raw)}` } },
      },
    },
  });
}

function updateCharts(rows) {
  const byBucket = aggregate(rows, (row) => row.relativeBucket, (key) => ({ bucket: key }))
    .sort((a, b) => bucketOrder.indexOf(a.bucket) - bucketOrder.indexOf(b.bucket));
  renderChart(
    "relativeChart",
    byBucket.map((row) => row.bucket.replace(" intermedio ", " int. ")),
    byBucket.map((row) => row.icPct),
    byBucket.map((row) => row.adPct),
  );

  const byMesa = aggregate(rows, (row) => row.mesa, (key) => ({ mesa: Number(key) }))
    .filter((row) => row.rows >= 10)
    .sort((a, b) => a.mesa - b.mesa)
    .slice(0, 60);
  renderChart(
    "mesaChart",
    byMesa.map((row) => String(row.mesa)),
    byMesa.map((row) => row.icPct),
    byMesa.map((row) => row.adPct),
  );
}

function renderCartogram(rows) {
  const byZone = aggregate(rows, (row) => row.zoneCode, (key, group) => ({
    zoneCode: key,
    zoneName: group[0].zoneName,
  })).sort((a, b) => a.zoneCode.localeCompare(b.zoneCode, "es", { numeric: true }));

  $("zoneCartogram").innerHTML = byZone.map((zone) => `
    <button class="zone-tile" style="background:${colorForIc(zone.icPct)}" data-zone="${zone.zoneCode}" title="Zona ${zone.zoneCode}: IC ${pct(zone.icPct)}, AD ${pct(zone.adPct)}">
      <span class="zone-code">Zona ${zone.zoneCode}</span>
      <span class="zone-share">IC ${pct(zone.icPct)}</span>
      <span class="zone-rows">${fmt.format(zone.rows)} formularios</span>
    </button>
  `).join("");

  document.querySelectorAll(".zone-tile").forEach((tile) => {
    tile.addEventListener("click", () => {
      state.filters.zone = tile.dataset.zone;
      state.filters.stand = "all";
      $("zoneFilter").value = state.filters.zone;
      updateStandFilter();
      render();
    });
  });
}

function updateZoneDetails(rows) {
  const summary = summarize(rows);
  const label = state.filters.zone === "all" ? "Todas las zonas" : `Zona ${state.filters.zone}`;
  $("selectedZoneLabel").textContent = `${label} · ${currentRound().validationModes[state.filters.validationMode]}`;
  $("zoneDetails").innerHTML = [
    ["Formularios", fmt.format(summary.rows)],
    ["Votos IC", fmt.format(summary.ic)],
    ["Votos AD", fmt.format(summary.ad)],
    ["IC", pct(summary.icPct)],
    ["AD", pct(summary.adPct)],
    ["Mesas AD > 35% del par", fmt.format(summary.adOver35Rows)],
    ["Margen IC", pct(summary.marginIc)],
  ].map(([labelText, value]) => `<div class="detail-row"><span>${labelText}</span><strong>${value}</strong></div>`).join("");
}

function standRows(rows) {
  const grouped = aggregate(rows, (row) => `${row.zoneCode}|${row.standCode}|${row.standName}`, (key, group) => ({
    zoneCode: group[0].zoneCode,
    standCode: group[0].standCode,
    standName: group[0].standName,
    maxMesa: Math.max(...group.map((row) => row.maxMesa)),
  }));

  const searched = grouped.filter((row) => {
    if (row.rows < state.filters.minRows) return false;
    if (!state.filters.search) return true;
    const haystack = `${row.zoneCode} ${row.standCode} ${row.standName}`.toLocaleLowerCase("es");
    return haystack.includes(state.filters.search.toLocaleLowerCase("es"));
  });

  searched.sort((a, b) => {
    const av = a[state.sort.key];
    const bv = b[state.sort.key];
    const direction = state.sort.direction === "asc" ? 1 : -1;
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * direction;
    return String(av).localeCompare(String(bv), "es", { numeric: true }) * direction;
  });

  return searched;
}

function updateTable(rows) {
  const tableRows = standRows(rows).slice(0, 300);
  $("standTable").innerHTML = tableRows.map((row) => `
    <tr>
      <td>${row.zoneCode}-${row.standCode}</td>
      <td>${row.standName}</td>
      <td>${fmt.format(row.rows)}</td>
      <td>${pct(row.icPct)}</td>
      <td>${pct(row.adPct)}</td>
      <td>${fmt.format(row.adOver35Rows)}</td>
      <td>${pct(row.marginIc)}</td>
      <td>${fmt.format(row.maxMesa)}</td>
    </tr>
  `).join("");
}

function render() {
  updateRoundCopy();
  const rows = filteredRows();
  updateMetrics(rows);
  updateCharts(rows);
  renderCartogram(validRows());
  updateZoneDetails(rows);
  updateTable(rows);
}

function changeRound(round) {
  state.filters.round = round;
  state.filters.validationMode = currentRound().recommendedMode;
  state.filters.zone = "all";
  state.filters.stand = "all";
  state.filters.bucket = "all";
  populateValidationFilter();
  populateFilters();
  render();
}

function bindEvents() {
  $("roundFilter").addEventListener("change", (event) => {
    changeRound(event.target.value);
  });
  $("validationMode").addEventListener("change", (event) => {
    state.filters.validationMode = event.target.value;
    render();
  });
  $("zoneFilter").addEventListener("change", (event) => {
    state.filters.zone = event.target.value;
    state.filters.stand = "all";
    updateStandFilter();
    render();
  });
  $("standFilter").addEventListener("change", (event) => {
    state.filters.stand = event.target.value;
    render();
  });
  $("bucketFilter").addEventListener("change", (event) => {
    state.filters.bucket = event.target.value;
    render();
  });
  $("minRows").addEventListener("input", (event) => {
    state.filters.minRows = Number(event.target.value || 1);
    render();
  });
  $("tableSearch").addEventListener("input", (event) => {
    state.filters.search = event.target.value;
    render();
  });
  document.querySelectorAll("th[data-sort]").forEach((header) => {
    header.addEventListener("click", () => {
      const key = header.dataset.sort;
      if (state.sort.key === key) {
        state.sort.direction = state.sort.direction === "asc" ? "desc" : "asc";
      } else {
        state.sort = { key, direction: "desc" };
      }
      render();
    });
  });
}

async function init() {
  document.body.classList.add("loading");
  const response = await fetch("./data/dashboard-data.json");
  state.data = await response.json();
  state.filters.round = state.data.metadata.defaultRound || "segunda";
  state.filters.validationMode = currentRound().recommendedMode;
  populateRoundFilter();
  populateValidationFilter();
  populateFilters();
  bindEvents();
  render();
  document.body.classList.remove("loading");
}

init().catch((error) => {
  console.error(error);
  document.querySelector("main").innerHTML = `<section class="panel"><h2>No se pudo cargar el tablero</h2><p>${error.message}</p></section>`;
});
