'use strict';

let currentResults = null;
let currentSQL = '';
let isExecuting = false;

const queryInput = document.getElementById('queryInput');
const analyzeBtn = document.getElementById('analyzeBtn');
const analyzeBtnText = document.getElementById('analyzeBtnText');
const analyzeSpinner = document.getElementById('analyzeSpinner');
const resultsWorkspace = document.getElementById('resultsWorkspace');
const errorBanner = document.getElementById('errorBanner');
const errorDesc = document.getElementById('errorDesc');
const insightBody = document.getElementById('insightBody');
const tableViewport = document.getElementById('tableViewport');
const sqlDisplayCode = document.getElementById('sqlDisplayCode');
const tabRowCounter = document.getElementById('tabRowCounter');
const metaDuration = document.getElementById('metaDuration');

queryInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    runFullAnalysis();
  }
});

function setQuery(text) {
  queryInput.value = text;
  queryInput.focus();
}

function filterCategory(cat, btn) {
  document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');

  const chips = document.querySelectorAll('.prompt-chip');
  chips.forEach(chip => {
    if (cat === 'all' || chip.getAttribute('data-category') === cat) {
      chip.style.display = 'flex';
    } else {
      chip.style.display = 'none';
    }
  });
}

function switchTab(tabId) {
  const tabs = ['insight', 'table', 'sql'];
  tabs.forEach(t => {
    const btn = document.getElementById(`tabBtn${t.charAt(0).toUpperCase() + t.slice(1)}`);
    const pane = document.getElementById(`pane${t.charAt(0).toUpperCase() + t.slice(1)}`);
    if (btn) btn.classList.remove('active');
    if (pane) pane.classList.remove('active');
  });

  const activeBtn = document.getElementById(`tabBtn${tabId.charAt(0).toUpperCase() + tabId.slice(1)}`);
  const activePane = document.getElementById(`pane${tabId.charAt(0).toUpperCase() + tabId.slice(1)}`);
  if (activeBtn) activeBtn.classList.add('active');
  if (activePane) activePane.classList.add('active');
}

function setExecutingState(executing) {
  isExecuting = executing;
  analyzeBtn.disabled = executing;
  if (executing) {
    analyzeSpinner.hidden = false;
    analyzeBtnText.textContent = 'Processing...';
  } else {
    analyzeSpinner.hidden = true;
    analyzeBtnText.textContent = 'Run Analysis';
  }
}

async function runFullAnalysis() {
  const question = queryInput.value.trim();
  if (!question || isExecuting) return;

  setExecutingState(true);
  errorBanner.classList.add('hidden');
  resultsWorkspace.classList.add('hidden');

  const startTime = performance.now();

  try {
    const res = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question })
    });

    const elapsed = ((performance.now() - startTime) / 1000).toFixed(2);

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Query execution failed.');
    }

    const data = await res.json();
    currentResults = data;
    currentSQL = data.sql || '';

    metaDuration.textContent = `Latency: ${elapsed}s`;
    renderResults(data);
    switchTab('insight');
    resultsWorkspace.classList.remove('hidden');

  } catch (err) {
    showError(err.message || 'An unexpected error occurred during execution.');
  } finally {
    setExecutingState(false);
  }
}

async function runSqlOnly() {
  const question = queryInput.value.trim();
  if (!question || isExecuting) return;

  setExecutingState(true);
  errorBanner.classList.add('hidden');
  resultsWorkspace.classList.add('hidden');

  const startTime = performance.now();

  try {
    const res = await fetch('/api/sql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question })
    });

    const elapsed = ((performance.now() - startTime) / 1000).toFixed(2);

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'SQL generation failed.');
    }

    const data = await res.json();
    currentSQL = data.sql || '';

    sqlDisplayCode.textContent = currentSQL;
    metaDuration.textContent = `Generated in ${elapsed}s`;

    switchTab('sql');
    resultsWorkspace.classList.remove('hidden');

  } catch (err) {
    showError(err.message || 'Failed to generate SQL.');
  } finally {
    setExecutingState(false);
  }
}

function renderResults(data) {
  // 1. Render Insight
  const rawInsight = data.insight || 'No insight summary returned.';
  const formattedInsight = rawInsight.replace(/(₹[\d,]+(\.\d+)?)/g, '<strong class="currency-val">$1</strong>');
  insightBody.innerHTML = formattedInsight;

  // 2. Render SQL
  sqlDisplayCode.textContent = data.sql || '-- No SQL generated';

  // 3. Render Data Table
  const cols = data.columns || [];
  const rows = data.rows || [];
  tabRowCounter.textContent = rows.length;

  if (rows.length === 0) {
    tableViewport.innerHTML = `<div style="padding: 28px; text-align: center; color: var(--text-dim);">No rows returned for this query.</div>`;
    return;
  }

  let tableHtml = '<table class="data-table" id="dataTable"><thead><tr>';
  cols.forEach(c => {
    tableHtml += `<th>${escapeHtml(formatColumnHeader(c))}</th>`;
  });
  tableHtml += '</tr></thead><tbody>';

  rows.forEach(r => {
    tableHtml += '<tr>';
    r.forEach((val, idx) => {
      const colName = cols[idx] ? cols[idx].toLowerCase() : '';
      const formatted = formatTableCell(val, colName);
      tableHtml += formatted;
    });
    tableHtml += '</tr>';
  });
  tableHtml += '</tbody></table>';

  tableViewport.innerHTML = tableHtml;
}

function formatColumnHeader(col) {
  return col.replace(/_/g, ' ');
}

function formatTableCell(val, colName) {
  if (val === null || val === undefined) {
    return '<td class="num-cell" style="color: var(--text-dim);">&mdash;</td>';
  }

  const strVal = String(val);

  // Status badges
  if (colName.includes('status')) {
    const s = strVal.toLowerCase();
    return `<td><span class="status-badge ${s}">${escapeHtml(strVal)}</span></td>`;
  }

  // Currency columns
  if (colName.includes('revenue') || colName.includes('price') || colName.includes('cost') || colName.includes('variance') || colName.includes('at_risk')) {
    if (typeof val === 'number') {
      const formatted = val.toLocaleString('en-IN', { maximumFractionDigits: 2, minimumFractionDigits: 2 });
      return `<td class="num-cell currency-val">₹${formatted}</td>`;
    }
  }

  // Numbers
  if (typeof val === 'number') {
    return `<td class="num-cell">${val.toLocaleString('en-IN')}</td>`;
  }

  return `<td>${escapeHtml(strVal)}</td>`;
}

function filterTableRows() {
  const query = document.getElementById('tableFilterInput').value.toLowerCase();
  const rows = document.querySelectorAll('#dataTable tbody tr');
  rows.forEach(row => {
    const text = row.textContent.toLowerCase();
    row.style.display = text.includes(query) ? '' : 'none';
  });
}

function exportTableToCSV() {
  if (!currentResults || !currentResults.rows || currentResults.rows.length === 0) return;
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
}

function copySqlQuery() {
  if (!currentSQL) return;
  navigator.clipboard.writeText(currentSQL).then(() => {
    const btnText = document.getElementById('copySqlBtnText');
    btnText.textContent = 'Copied!';
    setTimeout(() => {
      btnText.textContent = 'Copy Query';
    }, 2000);
  });
}

function toggleSchemaDrawer() {
  const drawer = document.getElementById('schemaDrawer');
  const overlay = document.getElementById('drawerOverlay');
  drawer.classList.toggle('hidden');
  overlay.classList.toggle('hidden');
}

function toggleTableFields(id) {
  const el = document.getElementById(`fields_${id}`);
  if (el) {
    el.style.display = el.style.display === 'none' ? 'flex' : 'none';
  }
}

function showError(msg) {
  errorDesc.textContent = msg;
  errorBanner.classList.remove('hidden');
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
