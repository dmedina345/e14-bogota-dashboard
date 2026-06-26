const state = {
  data: null,
  filters: {
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
  "Mesa única",
  "0-10% mesas más adultas",
  "10-25% mesas adultas",
  "25-50% intermedio adulto",
  "50-75% intermedio joven",
  "75-90% mesas jóvenes",
  "90-100% mesas más jóvenes",
];

const validationFields = {
  strict: "strictValid",
  candidate: "candidateValid",
  fallbackExact: "fallbackExact",
  fallback5: "fallback5",
  fallback10: "fallback10",
};

const validationLabels = {
  strict: "Validación estricta",
  candidate: "Distribución candidatos",
  fallbackExact: "Fallback exacto",
  fallback5: "Fallback 5%",
  fallback10: "Fallback 10%",
};

const fmt = new Intl.NumberFormat("es-CO");
const pctFmt = new Intl.NumberFormat("es-CO", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function $(id) {
  return document.getElementById(id);
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
    return acc;
  }, { rows: rows.length, ic: 0, ad: 0, candidateVotes: 0 });
  total.icPct = share(total.ic, total.candidateVotes);
  total.adPct = share(total.ad, total.candidateVotes);
  total.marginIc = share(total.ic - total.ad, total.candidateVotes);
  return total;
}

function validRows() {
  const field = validationFields[state.filters.validationMode];
  return state.data.rows.filter((row) => row[field]);
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

function populateFilters() {
  const zones = aggregate(state.data.rows, (row) => row.zoneCode, (key, group) => ({
    zoneCode: key,
    zoneName: group[0].zoneName,
  })).sort((a, b) => a.zoneCode.localeCompare(b.zoneCode, "es", { numeric: true }));

  $("zoneFilter").innerHTML = `<option value="all">Todas</option>` + zones
    .map((zone) => `<option value="${zone.zoneCode}">Zona ${zone.zoneCode}</option>`)
    .join("");

  $("bucketFilter").innerHTML = `<option value="all">Todas</option>` + bucketOrder
    .map((bucket) => `<option value="${bucket}">${bucket}</option>`)
    .join("");

  updateStandFilter();
}

function updateStandFilter() {
  const stands = aggregate(
    state.data.rows.filter((row) => state.filters.zone === "all" || row.zoneCode === state.filters.zone),
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
}

function updateMetrics(rows) {
  const summary = summarize(rows);
  $("metricRows").textContent = fmt.format(summary.rows);
  $("metricCoverage").textContent = pct(share(summary.rows, state.data.metadata.allRows));
  $("metricIc").textContent = pct(summary.icPct);
  $("metricAd").textContent = pct(summary.adPct);
  $("metricMargin").textContent = pct(summary.marginIc);
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
      <span class="zone-rows">${fmt.format(zone.rows)} forms</span>
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
  $("selectedZoneLabel").textContent = `${label} · ${validationLabels[state.filters.validationMode]}`;
  $("zoneDetails").innerHTML = [
    ["Formularios", fmt.format(summary.rows)],
    ["Votos IC", fmt.format(summary.ic)],
    ["Votos AD", fmt.format(summary.ad)],
    ["IC", pct(summary.icPct)],
    ["AD", pct(summary.adPct)],
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
      <td>${pct(row.marginIc)}</td>
      <td>${fmt.format(row.maxMesa)}</td>
    </tr>
  `).join("");
}

function render() {
  const rows = filteredRows();
  updateMetrics(rows);
  updateCharts(rows);
  renderCartogram(validRows());
  updateZoneDetails(rows);
  updateTable(rows);
}

function bindEvents() {
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
  populateFilters();
  bindEvents();
  render();
  document.body.classList.remove("loading");
}

init().catch((error) => {
  console.error(error);
  document.querySelector("main").innerHTML = `<section class="panel"><h2>No se pudo cargar el tablero</h2><p>${error.message}</p></section>`;
});
