'use strict';

let currentDateRange = 'sep';
let currentCurrency = 'INR';
let currentModule = 'sales-planning';
let currentResults = null;
let currentSQL = 'SELECT store_id, SUM(revenue)\nFROM sales_table\nGROUP BY 1\nORDER BY 2 DESC\nLIMIT 1;';
let isExecuting = false;

const queryInput = document.getElementById('queryInput');
const analyzeBtn = document.getElementById('analyzeBtn');
const analyzeBtnText = document.getElementById('analyzeBtnText');
const analyzeSpinner = document.getElementById('analyzeSpinner');
const sqlDisplayCode = document.getElementById('sqlDisplayCode');
const lineNumbersCol = document.getElementById('lineNumbersCol');
const tableViewport = document.getElementById('tableViewport');
const insightText = document.getElementById('insightText');
const copyBtnText = document.getElementById('copyBtnText');
const previewBars = document.getElementById('previewBars');
const dateMenu = document.getElementById('dateMenu');
const currentDateLabel = document.getElementById('currentDateLabel');
const navCurrSym = document.getElementById('navCurrSym');
const navCurrCode = document.getElementById('navCurrCode');
const toastMessage = document.getElementById('toastMessage');

// Domain questions per module
const MODULE_QUESTIONS = {
  'sales-planning': [
    { text: 'Which store has the highest total revenue?', type: 'purple' },
    { text: 'Which warehouse is at risk of running out of inventory next week?', type: 'orange' },
    { text: 'Show me top 5 products by revenue', type: 'purple' },
    { text: 'Which products currently show a Stockout status?', type: 'orange' },
    { text: 'Compare festive vs non-festive revenue by store', type: 'purple' },
    { text: 'What is the total revenue by product category?', type: 'purple' }
  ],
  'inventory-stockout': [
    { text: 'Which warehouse is at risk of running out of inventory next week?', type: 'orange' },
    { text: 'Which products currently show a Stockout status?', type: 'orange' },
    { text: 'Show products with days of supply less than 7 days', type: 'orange' },
    { text: 'Which store has the highest number of understocked items?', type: 'orange' },
    { text: 'Calculate total potential revenue at risk from stockouts', type: 'purple' },
    { text: 'List suppliers with highest stockout rate', type: 'purple' }
  ],
  'demand-planning': [
    { text: 'What is the total revenue by product category?', type: 'purple' },
    { text: 'Which category has the highest sales velocity?', type: 'purple' },
    { text: 'Compare sales volume between North and South regions', type: 'purple' },
    { text: 'Show products with buffer days under 10', type: 'orange' },
    { text: 'Which stores had the biggest festive surge in Q4?', type: 'purple' },
    { text: 'What are the lowest selling SKUs across all stores?', type: 'orange' }
  ],
  'forecast-planning': [
    { text: 'Compare festive vs non-festive revenue by store', type: 'purple' },
    { text: 'Which stores had the biggest festive surge in Q4?', type: 'purple' },
    { text: 'What is the projected revenue variance by store?', type: 'purple' },
    { text: 'Which categories spike most during festival weeks?', type: 'purple' },
    { text: 'Which products currently show a Stockout status?', type: 'orange' },
    { text: 'Which store has the highest total revenue?', type: 'purple' }
  ],
  'revenue': [
    { text: 'Which store has the highest total revenue?', type: 'purple' },
    { text: 'What is the total revenue by product category?', type: 'purple' },
    { text: 'Show me top 5 products by revenue', type: 'purple' },
    { text: 'Compare festive vs non-festive revenue by store', type: 'purple' },
    { text: 'Which region generated the highest average order value?', type: 'purple' },
    { text: 'Calculate total potential revenue at risk from stockouts', type: 'orange' }
  ]
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  loadMetrics();
  updateLineNumbers(currentSQL);
  
  // Close date menu on outside click
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.date-dropdown-wrapper')) {
      if (dateMenu && !dateMenu.classList.contains('hidden')) {
        dateMenu.classList.add('hidden');
      }
    }
  });
});

queryInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    runFullAnalysis();
  }
});

function focusSearch() {
  queryInput.focus();
}

function setQuery(text) {
  queryInput.value = text;
  queryInput.focus();
}

function runPromptQuery(text) {
  setQuery(text);
  runFullAnalysis();
}

function toggleDateMenu() {
  if (dateMenu) {
    dateMenu.classList.toggle('hidden');
  }
}

function selectDateRange(range, label) {
  currentDateRange = range;
  if (currentDateLabel) {
    currentDateLabel.textContent = label.replace(' (Benchmark)', '');
  }
  if (dateMenu) {
    dateMenu.classList.add('hidden');
    dateMenu.querySelectorAll('.date-menu-item').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-range') === range);
    });
  }
  loadMetrics();
  showToast(`Date filter applied: ${label}`);
}

function toggleCurrency() {
  currentCurrency = currentCurrency === 'INR' ? 'USD' : 'INR';
  if (navCurrSym) navCurrSym.textContent = currentCurrency === 'INR' ? '₹' : '$';
  if (navCurrCode) navCurrCode.textContent = currentCurrency;
  loadMetrics();
  showToast(`Currency switched to ${currentCurrency}`);
}

function switchSidebarModule(modKey, el) {
  // Update sidebar active item
  document.querySelectorAll('.sidebar-nav .menu-item').forEach(item => {
    item.classList.remove('active');
    const arrow = item.querySelector('.active-arrow');
    if (arrow) arrow.remove();
  });
  
  if (el) {
    el.classList.add('active');
  }
  
  currentModule = modKey;
  
  // Update question chips to match domain
  const questions = MODULE_QUESTIONS[modKey] || MODULE_QUESTIONS['sales-planning'];
  const grid = document.getElementById('promptPillsGrid');
  if (grid) {
    grid.innerHTML = questions.map(q => `
      <button class="pill-chip" onclick="runPromptQuery('${escapeQuotes(q.text)}')">
        <span class="p-dot ${q.type}"></span> ${q.text}
      </button>
    `).join('');
  }
  
  loadMetrics();
  showToast(`Switched view to ${el ? el.textContent.replace('>', '').trim() : modKey}`);
}

async function loadMetrics() {
  try {
    const res = await fetch(`/api/metrics?date_range=${currentDateRange}&currency=${currentCurrency}&module=${currentModule}`);
    if (!res.ok) return;
    const json = await res.json();
    if (json.status === 'success' && json.data) {
      updateKpiCards(json.data, json.currency_symbol);
    }
  } catch (err) {
    console.error('Failed to load metrics:', err);
  }
}

function updateKpiCards(data, sym) {
  // 1. Revenue Card
  const kpiRevVal = document.getElementById('kpiRevVal');
  const kpiRevBadge = document.getElementById('kpiRevBadge');
  const kpiRevYAxis = document.getElementById('kpiRevYAxis');
  const kpiRevXAxis = document.getElementById('kpiRevXAxis');
  const kpiTooltipText = document.getElementById('kpiTooltipText');
  const kpiSplineLine = document.getElementById('kpiSplineLine');
  const kpiSplineArea = document.getElementById('kpiSplineArea');

  if (kpiRevVal) kpiRevVal.textContent = data.rev_fmt;
  if (kpiRevBadge) kpiRevBadge.textContent = data.growth;
  if (kpiRevYAxis && data.spline_y) {
    kpiRevYAxis.innerHTML = data.spline_y.map(y => `<span>${y}</span>`).join('');
  }
  if (kpiRevXAxis && data.spline_x) {
    kpiRevXAxis.innerHTML = data.spline_x.map(x => `<span>${x}</span>`).join('');
  }
  if (kpiTooltipText && data.spline_pts && data.spline_pts.length > 3) {
    kpiTooltipText.textContent = data.spline_pts[3].lbl;
  }

  // 2. Transactions Card
  const kpiTxnPeriod = document.getElementById('kpiTxnPeriod');
  const kpiTxnCount = document.getElementById('kpiTxnCount');
  const kpiAvgBasket = document.getElementById('kpiAvgBasket');
  const kpiTxnBars = document.getElementById('kpiTxnBars');
  const kpiTxnCatLabels = document.getElementById('kpiTxnCatLabels');

  if (kpiTxnPeriod) kpiTxnPeriod.textContent = data.period;
  if (kpiTxnCount) kpiTxnCount.textContent = data.txns;
  if (kpiAvgBasket) kpiAvgBasket.textContent = data.basket;

  if (kpiTxnBars && data.bars) {
    kpiTxnBars.innerHTML = data.bars.map(b => `
      <div class="bar-col" title="${b.name}: ${b.count}"><div class="bar-fill" style="height: ${b.pct}%;"></div></div>
    `).join('');
  }
  if (kpiTxnCatLabels && data.bars) {
    kpiTxnCatLabels.innerHTML = data.bars.map(b => `<span>${b.name}</span>`).join('');
  }

  // 3. Catalog Card
  const kpiCatalogSkus = document.getElementById('kpiCatalogSkus');
  const catTooltipCount = document.getElementById('catTooltipCount');
  const catTooltipVal = document.getElementById('catTooltipVal');
  const catTooltipPromos = document.getElementById('catTooltipPromos');
  const kpiCatalogBars = document.getElementById('kpiCatalogBars');

  if (kpiCatalogSkus && data.catalog) kpiCatalogSkus.textContent = data.catalog.skus;
  if (catTooltipCount && data.catalog) catTooltipCount.textContent = `• Category: ${data.catalog.skus}`;
  if (catTooltipVal && data.catalog) catTooltipVal.textContent = `• Inventory Value: ${data.catalog.val}`;
  if (catTooltipPromos && data.catalog) catTooltipPromos.textContent = `• Active Promos: ${data.catalog.promos}`;

  if (kpiCatalogBars && data.catalog && data.catalog.categories) {
    kpiCatalogBars.innerHTML = data.catalog.categories.map((c, i) => `
      <div class="hbar-item">
        <span class="hbar-label">${c.name}</span>
        <div class="hbar-track">
          <div class="hbar-fill" style="width: ${c.pct}%;">
            ${i === 0 ? `
              <div class="hbar-cursor-tooltip">
                <strong>SKU SKU</strong>
                <div>• Category: ${data.catalog.skus}</div>
                <div>• Inventory Value: ${data.catalog.val}</div>
                <div>• Active Promos: ${data.catalog.promos}</div>
              </div>
            ` : ''}
          </div>
        </div>
      </div>
    `).join('');
  }

  // 4. Stockout Card
  const kpiStockoutSkus = document.getElementById('kpiStockoutSkus');
  const kpiHeatmapMatrix = document.getElementById('kpiHeatmapMatrix');

  if (kpiStockoutSkus && data.stockout) kpiStockoutSkus.textContent = data.stockout.skus;
  if (kpiHeatmapMatrix && data.stockout && data.stockout.heatmap) {
    let rowsHtml = '';
    data.stockout.heatmap.forEach(rowCells => {
      rowsHtml += '<div class="hm-row">';
      rowCells.forEach(cellClass => {
        const cls = cellClass.replace('cell-', 'lvl-');
        rowsHtml += `<div class="hm-cell ${cls}"></div>`;
      });
      rowsHtml += '</div>';
    });
    rowsHtml += '<div class="hm-col-labels"><span>R1</span><span>W2</span><span>W3</span><span>W4</span><span>W5</span></div>';
    kpiHeatmapMatrix.innerHTML = rowsHtml;
  }

  // Card highlight based on module
  document.querySelectorAll('.kpi-card').forEach(c => c.classList.remove('card-highlight', 'card-highlight-amber'));
  if (data.highlight_card === 'stockout') {
    const sc = document.getElementById('cardStockout');
    if (sc) sc.classList.add('card-highlight-amber');
  } else if (data.highlight_card === 'revenue') {
    const rc = document.getElementById('cardRevenue');
    if (rc) rc.classList.add('card-highlight');
  }
}

function updateLineNumbers(sql) {
  const lines = (sql || '').split('\n').length;
  let numbersHtml = '';
  for (let i = 1; i <= Math.max(lines, 6); i++) {
    numbersHtml += `<span>${i}</span>`;
  }
  lineNumbersCol.innerHTML = numbersHtml;
}

function setExecutingState(executing) {
  isExecuting = executing;
  analyzeBtn.disabled = executing;
  if (executing) {
    analyzeSpinner.hidden = false;
    analyzeBtnText.textContent = 'Analyzing...';
  } else {
    analyzeSpinner.hidden = true;
    analyzeBtnText.textContent = 'Run Analysis';
  }
}

async function runFullAnalysis() {
  const question = queryInput.value.trim();
  if (!question || isExecuting) return;

  setExecutingState(true);

  try {
    const res = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Query execution failed.');
    }

    const data = await res.json();
    currentResults = data;
    currentSQL = data.sql || '';

    // Update SQL Inspector
    sqlDisplayCode.textContent = currentSQL;
    updateLineNumbers(currentSQL);

    // Update Insight
    insightText.textContent = data.insight || 'Analysis completed successfully.';

    // Update Table Viewport
    renderTable(data.columns || [], data.rows || []);

    // Update preview chart bars with real dynamically calculated heights
    updatePreviewBars(data.columns || [], data.rows || []);

  } catch (err) {
    insightText.textContent = `Error: ${err.message || 'Execution failed.'}`;
  } finally {
    setExecutingState(false);
  }
}

function renderTable(cols, rows) {
  if (rows.length === 0) {
    tableViewport.innerHTML = `<div style="padding: 16px; font-size: 0.75rem; color: var(--text-dim); text-align: center;">No rows returned.</div>`;
    return;
  }

  let html = '<table class="preview-data-table"><thead><tr>';
  cols.slice(0, 4).forEach(c => {
    html += `<th>${escapeHtml(formatHeader(c))}</th>`;
  });
  html += '</tr></thead><tbody>';

  rows.slice(0, 5).forEach(r => {
    html += '<tr>';
    r.slice(0, 4).forEach((val, idx) => {
      const colName = (cols[idx] || '').toLowerCase();
      html += `<td>${formatCell(val, colName)}</td>`;
    });
    html += '</tr>';
  });
  html += '</tbody></table>';

  tableViewport.innerHTML = html;
}

function formatHeader(col) {
  return col.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function formatCell(val, colName) {
  if (val === null || val === undefined) return '&mdash;';
  if (typeof val === 'number') {
    if (colName.includes('revenue') || colName.includes('price') || colName.includes('risk')) {
      const sym = currentCurrency === 'USD' ? '$' : '₹';
      const num = currentCurrency === 'USD' ? Math.round(val / 83.33) : Math.round(val);
      return `${sym}${num.toLocaleString(currentCurrency === 'USD' ? 'en-US' : 'en-IN')}`;
    }
    return val.toLocaleString();
  }
  return escapeHtml(String(val));
}

function updatePreviewBars(cols, rows) {
  if (!rows || rows.length === 0) return;
  
  // Find a numeric column in the results
  let numColIdx = -1;
  for (let c = 0; c < (cols || []).length; c++) {
    if (typeof rows[0][c] === 'number') {
      numColIdx = c;
      break;
    }
  }

  const numRows = Math.min(rows.length, 6);
  let values = [];
  for (let i = 0; i < numRows; i++) {
    const v = numColIdx >= 0 && typeof rows[i][numColIdx] === 'number' 
      ? rows[i][numColIdx] 
      : (numRows - i) * 500;
    values.push(Math.abs(v));
  }

  const maxVal = Math.max(...values, 1);
  let barsHtml = '';
  for (let i = 0; i < numRows; i++) {
    const pct = Math.max(16, Math.min(94, Math.round((values[i] / maxVal) * 88)));
    barsHtml += `<div class="p-bar" style="height: ${pct}%;" title="${values[i].toLocaleString()}"></div>`;
  }
  previewBars.innerHTML = barsHtml;
}

function copySqlQuery() {
  if (!currentSQL) return;
  navigator.clipboard.writeText(currentSQL).then(() => {
    copyBtnText.textContent = 'Copied!';
    setTimeout(() => {
      copyBtnText.textContent = 'Copy';
    }, 2000);
  });
}

function saveCurrentQuery() {
  const query = {
    sql: currentSQL,
    question: queryInput.value.trim() || 'Custom Analysis',
    timestamp: new Date().toISOString()
  };
  try {
    const list = JSON.parse(localStorage.getItem('retailiq_saved_queries') || '[]');
    list.push(query);
    localStorage.setItem('retailiq_saved_queries', JSON.stringify(list));
  } catch (e) {
    // Ignore storage quota
  }
  showToast('✓ Query saved to workspace templates');
}

function exportTableToCSV() {
  if (!currentResults || !currentResults.rows || currentResults.rows.length === 0) {
    showToast('No data rows available to export.');
    return;
  }
  const cols = currentResults.columns;
  const rows = currentResults.rows;

  let csv = cols.map(c => `"${c.replace(/"/g, '""')}"`).join(',') + '\n';
  rows.forEach(r => {
    csv += r.map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',') + '\n';
  });

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `retailiq_export_${Date.now()}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  showToast('✓ Results exported to CSV');
}

function showToast(msg) {
  if (!toastMessage) return;
  toastMessage.textContent = msg;
  toastMessage.classList.remove('hidden');
  clearTimeout(toastMessage._timer);
  toastMessage._timer = setTimeout(() => {
    toastMessage.classList.add('hidden');
  }, 2600);
}

function toggleSchemaDrawer() {
  const drawer = document.getElementById('schemaDrawer');
  const overlay = document.getElementById('drawerOverlay');
  drawer.classList.toggle('hidden');
  overlay.classList.toggle('hidden');
}

function toggleCols(id) {
  const el = document.getElementById(`cols_${id}`);
  if (el) {
    el.style.display = el.style.display === 'none' ? 'flex' : 'none';
  }
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escapeQuotes(str) {
  return String(str).replace(/'/g, "\\'");
}
