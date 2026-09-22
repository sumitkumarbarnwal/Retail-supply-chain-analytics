'use strict';

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

function updateLineNumbers(sql) {
  const lines = sql.split('\n').length;
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
    insightText.textContent = data.insight || 'Query executed successfully.';

    // Update Table Viewport
    renderTable(data.columns || [], data.rows || []);

    // Update preview chart bars
    updatePreviewBars(data.rows || []);

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
      return `₹${val.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
    }
    return val.toLocaleString('en-IN');
  }
  return escapeHtml(String(val));
}

function updatePreviewBars(rows) {
  if (!rows || rows.length === 0) return;
  const numRows = Math.min(rows.length, 6);
  let barsHtml = '';
  
  // Find a numeric column to gauge
  const heights = [85, 72, 58, 44, 32, 18];
  for (let i = 0; i < numRows; i++) {
    const h = heights[i] || 30;
    barsHtml += `<div class="p-bar" style="height: ${h}%;"></div>`;
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

function exportTableToCSV() {
  if (!currentResults || !currentResults.rows || currentResults.rows.length === 0) {
    alert('No data rows to export.');
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
  a.download = `retailiq_results_${Date.now()}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
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
