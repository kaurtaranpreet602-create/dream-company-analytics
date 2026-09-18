/* =========================================================================
   Dream Company Analytics - app.js
   Handles: theme toggle, toasts, CSV upload (drag/drop + picker),
   Screener URL analysis, dashboard navigation, statistics, visualizations,
   data explorer with pagination/search.
   ========================================================================= */

// ---------------------------------------------------------------------
// THEME (Light / Dark) - persisted via localStorage
// ---------------------------------------------------------------------
(function initTheme() {
  const saved = localStorage.getItem("dca-theme") || "light";
  document.documentElement.setAttribute("data-theme", saved);
  document.addEventListener("DOMContentLoaded", () => {
    updateThemeIcon(saved);
  });
})();

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const next = current === "light" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("dca-theme", next);
  updateThemeIcon(next);
}

function updateThemeIcon(theme) {
  document.querySelectorAll("#theme-toggle").forEach(btn => {
    btn.textContent = theme === "dark" ? "☀️" : "🌙";
  });
}

// ---------------------------------------------------------------------
// TOASTS
// ---------------------------------------------------------------------
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 3800);
}

// ---------------------------------------------------------------------
// GENERIC FETCH HELPER
// ---------------------------------------------------------------------
async function apiRequest(url, options = {}) {
  try {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok || data.success === false) {
      throw new Error(data.error || "Something went wrong. Please try again.");
    }
    return data;
  } catch (err) {
    if (err instanceof TypeError) {
      throw new Error("Network error. Please check your connection and try again.");
    }
    throw err;
  }
}

// =========================================================================
// LANDING PAGE LOGIC
// =========================================================================
let selectedFile = null;
let detectedCompanyName = null;

function initLandingPage() {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  const chooseBtn = document.getElementById("choose-file-btn");
  const analyzeBtn = document.getElementById("analyze-dataset-btn");
  const editCompanyBtn = document.getElementById("edit-company-btn");
  const analyzeUrlBtn = document.getElementById("analyze-url-btn");

  if (!dropzone) return; // not on landing page

  chooseBtn.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length) handleFileSelected(e.target.files[0]);
  });

  ["dragenter", "dragover"].forEach(evt => {
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach(evt => {
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    });
  });
  dropzone.addEventListener("drop", (e) => {
    const files = e.dataTransfer.files;
    if (files.length) handleFileSelected(files[0]);
  });

  function handleFileSelected(file) {
    if (!file.name.toLowerCase().endsWith(".csv")) {
      showToast("Only CSV files are supported. Please choose a .csv file.", "error");
      return;
    }
    if (file.size === 0) {
      showToast("This file is empty. Please choose a valid CSV file.", "error");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      showToast("File is too large. Maximum size is 10 MB.", "error");
      return;
    }

    selectedFile = file;
    document.getElementById("file-name-display").textContent = file.name;
    document.getElementById("company-name-display").textContent = guessCompanyNameClientSide(file.name);
    document.getElementById("file-info").classList.remove("hidden");
    document.getElementById("dropzone").classList.add("hidden");
  }

  function guessCompanyNameClientSide(filename) {
    // Lightweight client-side preview only; the server does the real detection.
    let name = filename.replace(/\.csv$/i, "").replace(/[_\-.]+/g, " ").trim();
    return name.replace(/\w\S*/g, t => t.charAt(0).toUpperCase() + t.substr(1).toLowerCase());
  }

  editCompanyBtn.addEventListener("click", () => {
    const current = document.getElementById("company-name-display").textContent;
    const updated = prompt("Edit company name:", current);
    if (updated && updated.trim()) {
      document.getElementById("company-name-display").textContent = updated.trim();
    }
  });

  analyzeBtn.addEventListener("click", async () => {
    if (!selectedFile) return;

    document.getElementById("file-info").classList.add("hidden");
    document.getElementById("csv-loading").classList.remove("hidden");

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const data = await apiRequest("/upload", { method: "POST", body: formData });

      const editedName = document.getElementById("company-name-display").textContent;
      if (editedName && editedName !== data.profile.company_name) {
        await apiRequest("/update-company-name", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ company_name: editedName }),
        });
      }

      showToast("Dataset loaded successfully!", "success");
      window.location.href = "/dashboard";
    } catch (err) {
      document.getElementById("csv-loading").classList.add("hidden");
      document.getElementById("file-info").classList.remove("hidden");
      showToast(err.message, "error");
    }
  });

  // ----------------- Screener URL -----------------
  let screenerCacheKey = null;
  let screenerCompanyName = null;

  analyzeUrlBtn.addEventListener("click", async () => {
    const url = document.getElementById("screener-url-input").value.trim();
    if (!url) {
      showToast("Please enter a Screener company URL.", "error");
      return;
    }

    document.getElementById("url-sections").classList.add("hidden");
    document.getElementById("url-loading").classList.remove("hidden");

    try {
      const data = await apiRequest("/analyze-url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });

      screenerCacheKey = data.cache_key;
      screenerCompanyName = data.company_name;

      const listEl = document.getElementById("section-list");
      listEl.innerHTML = "";
      data.sections.forEach(section => {
        const item = document.createElement("div");
        item.className = "section-item";
        item.innerHTML = `<strong>${section.label}</strong> &middot; ${section.row_count} rows &middot; ${section.columns.length} columns`;
        item.addEventListener("click", () => selectScreenerTable(section.key));
        listEl.appendChild(item);
      });

      document.getElementById("url-sections").classList.remove("hidden");
      showToast(`Found ${data.sections.length} table(s) for ${data.company_name}.`, "success");
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      document.getElementById("url-loading").classList.add("hidden");
    }
  });

  async function selectScreenerTable(tableKey) {
    try {
      showToast("Loading selected table...", "info");
      await apiRequest("/select-screener-table", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cache_key: screenerCacheKey,
          table_key: tableKey,
          company_name: screenerCompanyName,
        }),
      });
      showToast("Screener data loaded successfully!", "success");
      window.location.href = "/dashboard";
    } catch (err) {
      showToast(err.message, "error");
    }
  }
}

// =========================================================================
// DASHBOARD LOGIC
// =========================================================================
let datasetProfile = null;
let currentPage = 1;
const PAGE_SIZE = 10;
let currentSearch = "";

function initDashboard() {
  const sidebar = document.getElementById("sidebar");
  if (!sidebar) return; // not on dashboard page

  // Sidebar nav
  document.querySelectorAll(".nav-item").forEach(item => {
    item.addEventListener("click", (e) => {
      e.preventDefault();
      activateSection(item.dataset.section);
    });
  });
  document.querySelectorAll(".quick-link-card").forEach(card => {
    card.addEventListener("click", () => activateSection(card.dataset.jump));
  });

  document.getElementById("sidebar-toggle").addEventListener("click", () => {
    sidebar.classList.toggle("collapsed");
  });
  document.getElementById("mobile-menu-btn").addEventListener("click", () => {
    sidebar.classList.toggle("mobile-open");
  });

  document.getElementById("settings-theme-toggle").addEventListener("click", toggleTheme);

  loadDatasetProfile();
  setupStatistics();
  setupVisualizations();
  setupDataExplorer();
}

function activateSection(sectionId) {
  document.querySelectorAll(".content-section").forEach(s => s.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));

  document.getElementById(sectionId).classList.add("active");
  const navItem = document.querySelector(`.nav-item[data-section="${sectionId}"]`);
  if (navItem) navItem.classList.add("active");

  document.getElementById("sidebar").classList.remove("mobile-open");

  if (sectionId === "dataset-section") loadDatasetPage();
}

async function loadDatasetProfile() {
  try {
    const data = await apiRequest("/dataset-profile");
    datasetProfile = data.profile;

    document.getElementById("dash-company-name").textContent = datasetProfile.company_name.toUpperCase();
    document.getElementById("dash-subtitle-line").textContent =
      datasetProfile.company_name.toLowerCase().includes("bank")
        ? "Financial Analytics Dashboard"
        : "Company Analytics Dashboard";

    document.getElementById("card-rows").textContent = datasetProfile.rows;
    document.getElementById("card-columns").textContent = datasetProfile.columns;
    document.getElementById("card-numeric").textContent = datasetProfile.numeric_column_count;
    document.getElementById("card-missing").textContent = datasetProfile.missing_values;

    document.getElementById("settings-source-name").textContent =
      `${datasetProfile.company_name} (${datasetProfile.source_name})`;

    populateColumnSelectors();
  } catch (err) {
    showToast(err.message, "error");
    setTimeout(() => { window.location.href = "/"; }, 1500);
  }
}

function populateColumnSelectors() {
  const numericCols = datasetProfile.numeric_columns;
  const allCols = datasetProfile.all_columns;

  const statSelect = document.getElementById("stat-column-select");
  statSelect.innerHTML = "";
  numericCols.forEach(col => {
    const opt = document.createElement("option");
    opt.value = col; opt.textContent = col;
    statSelect.appendChild(opt);
  });

  const vizColSelect = document.getElementById("viz-column-select");
  vizColSelect.innerHTML = "";
  numericCols.forEach(col => {
    const opt = document.createElement("option");
    opt.value = col; opt.textContent = col;
    vizColSelect.appendChild(opt);
  });

  const xSelect = document.getElementById("viz-x-select");
  const ySelect = document.getElementById("viz-y-select");
  xSelect.innerHTML = ""; ySelect.innerHTML = "";
  allCols.forEach(col => {
    const opt1 = document.createElement("option");
    opt1.value = col; opt1.textContent = col;
    xSelect.appendChild(opt1);
  });
  numericCols.forEach(col => {
    const opt2 = document.createElement("option");
    opt2.value = col; opt2.textContent = col;
    ySelect.appendChild(opt2);
  });
}

// ----------------- STATISTICS -----------------
function setupStatistics() {
  document.querySelectorAll(".stat-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      document.querySelectorAll(".stat-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      const fn = btn.dataset.fn;
      const selectEl = document.getElementById("stat-column-select");
      const selectedColumns = Array.from(selectEl.selectedOptions).map(o => o.value);

      try {
        const data = await apiRequest("/statistics", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ function: fn, columns: selectedColumns.length ? selectedColumns : null }),
        });
        renderStatResult(data.result);
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  });

  document.getElementById("explain-stat-btn").addEventListener("click", async () => {
    const title = document.getElementById("stat-result-title").textContent;
    try {
      const data = await apiRequest("/explain-result", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ context: title }),
      });
      const box = document.getElementById("stat-explain-box");
      box.textContent = data.explanation;
      box.classList.remove("hidden");
    } catch (err) {
      showToast(err.message, "error");
    }
  });
}

function renderStatResult(result) {
  document.getElementById("stat-empty").classList.add("hidden");
  document.getElementById("stat-result").classList.remove("hidden");
  document.getElementById("stat-explain-box").classList.add("hidden");

  document.getElementById("stat-result-title").textContent = result.label;
  document.getElementById("stat-explanation").textContent = result.explanation;

  const head = document.getElementById("stat-table-head");
  const body = document.getElementById("stat-table-body");
  head.innerHTML = ""; body.innerHTML = "";

  if (result.table_type === "simple") {
    head.innerHTML = "<tr><th>Column</th><th>Value</th></tr>";
    result.rows.forEach(row => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${row.column}</td><td>${row.value === null ? "-" : row.value}</td>`;
      body.appendChild(tr);
    });
  } else {
    const cols = result.table.columns;
    head.innerHTML = "<tr>" + cols.map(c => `<th>${c}</th>`).join("") + "</tr>";
    result.table.rows.forEach(row => {
      const tr = document.createElement("tr");
      tr.innerHTML = cols.map(c => `<td>${row[c] === null ? "-" : row[c]}</td>`).join("");
      body.appendChild(tr);
    });
  }
}

// ----------------- VISUALIZATIONS -----------------
function setupVisualizations() {
  const chartTypeSelect = document.getElementById("chart-type-select");
  const columnsGroup = document.getElementById("viz-columns-group");
  const xyGroup = document.getElementById("viz-xy-group");

  function updateVizControls() {
    const type = chartTypeSelect.value;
    if (type === "bar" || type === "point") {
      columnsGroup.classList.add("hidden");
      xyGroup.classList.remove("hidden");
    } else {
      columnsGroup.classList.remove("hidden");
      xyGroup.classList.add("hidden");
    }
  }
  chartTypeSelect.addEventListener("change", updateVizControls);
  updateVizControls();

  document.getElementById("generate-chart-btn").addEventListener("click", async () => {
    const type = chartTypeSelect.value;
    const payload = { chart_type: type };

    if (type === "bar" || type === "point") {
      payload.x_column = document.getElementById("viz-x-select").value;
      payload.y_column = document.getElementById("viz-y-select").value;
    } else {
      const selectEl = document.getElementById("viz-column-select");
      const selected = Array.from(selectEl.selectedOptions).map(o => o.value);
      payload.columns = selected.length ? selected : null;
    }

    document.getElementById("chart-empty").classList.add("hidden");
    document.getElementById("chart-result").classList.add("hidden");
    document.getElementById("chart-loading").classList.remove("hidden");

    try {
      const data = await apiRequest("/visualization", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      document.getElementById("chart-title").textContent = data.chart.title;
      document.getElementById("chart-image").src = data.chart.image;
      document.getElementById("chart-result").classList.remove("hidden");
    } catch (err) {
      document.getElementById("chart-empty").classList.remove("hidden");
      showToast(err.message, "error");
    } finally {
      document.getElementById("chart-loading").classList.add("hidden");
    }
  });
}

// ----------------- DATA EXPLORER -----------------
function setupDataExplorer() {
  const searchInput = document.getElementById("dataset-search");
  let debounceTimer = null;

  searchInput.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      currentSearch = searchInput.value.trim();
      currentPage = 1;
      loadDatasetPage();
    }, 350);
  });

  document.getElementById("prev-page-btn").addEventListener("click", () => {
    if (currentPage > 1) { currentPage--; loadDatasetPage(); }
  });
  document.getElementById("next-page-btn").addEventListener("click", () => {
    currentPage++; loadDatasetPage();
  });
}

async function loadDatasetPage() {
  try {
    const params = new URLSearchParams({
      page: currentPage, page_size: PAGE_SIZE, search: currentSearch,
    });
    const data = await apiRequest(`/dataset?${params.toString()}`);
    renderDatasetTable(data.preview);
  } catch (err) {
    showToast(err.message, "error");
  }
}

function renderDatasetTable(preview) {
  const head = document.getElementById("data-table-head");
  const body = document.getElementById("data-table-body");

  head.innerHTML = "<tr>" + preview.columns.map(c => `<th>${c}</th>`).join("") + "</tr>";
  body.innerHTML = "";

  if (preview.rows.length === 0) {
    body.innerHTML = `<tr><td colspan="${preview.columns.length}" style="text-align:center; color: var(--color-text-muted); padding: 30px;">No matching rows found.</td></tr>`;
  } else {
    preview.rows.forEach(row => {
      const tr = document.createElement("tr");
      tr.innerHTML = preview.columns.map(c => `<td>${row[c] === null || row[c] === undefined ? "-" : row[c]}</td>`).join("");
      body.appendChild(tr);
    });
  }

  document.getElementById("explorer-meta").textContent = `${preview.total_rows} rows · ${preview.columns.length} columns`;
  document.getElementById("page-indicator").textContent = `Page ${preview.page} of ${preview.total_pages}`;

  document.getElementById("prev-page-btn").disabled = preview.page <= 1;
  document.getElementById("next-page-btn").disabled = preview.page >= preview.total_pages;
}

// =========================================================================
// INIT
// =========================================================================
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("#theme-toggle").forEach(btn => {
    btn.addEventListener("click", toggleTheme);
  });
  updateThemeIcon(document.documentElement.getAttribute("data-theme") || "light");

  initLandingPage();
  initDashboard();
});
