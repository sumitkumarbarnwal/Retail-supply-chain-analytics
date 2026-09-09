'use strict';

let currentSQL = '';
let isLoading  = false;

const questionInput  = document.getElementById('questionInput');
const askBtn         = document.getElementById('askBtn');
const btnLoader      = document.getElementById('btnLoader');
const inputHint      = document.getElementById('inputHint');
const resultsSection = document.getElementById('resultsSection');
const loadingOverlay = document.getElementById('loadingOverlay');
const errorCard      = document.getElementById('errorCard');
const errorText      = document.getElementById('errorText');
const sqlCode        = document.getElementById('sqlCode');
const tableWrapper   = document.getElementById('tableWrapper');
const insightText    = document.getElementById('insightText');
const rowCountBadge  = document.getElementById('rowCountBadge');

const stepDots = [
  document.querySelector('#step1 .step-dot'),
  document.querySelector('#step2 .step-dot'),
  document.querySelector('#step3 .step-dot'),
];
const stepEls = [
  document.getElementById('step1'),
  document.getElementById('step2'),
  document.getElementById('step3'),
];

questionInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    askQuestion();
  }
});

questionInput.addEventListener('input', () => {
  questionInput.style.height = 'auto';
  questionInput.style.height = Math.min(questionInput.scrollHeight, 160) + 'px';
});

function setQuestion(text) {
  questionInput.value = text;
  questionInput.style.height = 'auto';
  questionInput.style.height = Math.min(questionInput.scrollHeight, 160) + 'px';
  questionInput.focus();
  inputHint.textContent = 'Press Enter or click Analyze to get your answer';
  document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
}

async function askQuestion() {
  const question = questionInput.value.trim();
  if (!question) {
    shakeInput();
    inputHint.textContent = '⚠️ Please enter a question first.';
    inputHint.style.color = 'var(--accent-warn)';
    setTimeout(() => {
      inputHint.textContent = 'Press Enter or click Analyze to get your answer';
      inputHint.style.color = '';
    }, 2500);
    return;
  }
  if (isLoading) return;

  setLoading(true);
  hideResults();
  hideError();
  showLoadingOverlay();
  advanceStep(0);

  try {
    await delay(600);
    advanceStep(1);

    const response = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });

    advanceStep(2);
    await delay(400);

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(err.detail || 'Server error');
    }

    const data = await response.json();
    completeAllSteps();
    await delay(300);

    hideLoadingOverlay();
    setLoading(false);
    renderResults(data);

  } catch (err) {
    hideLoadingOverlay();
    setLoading(false);
    showError(err.message || 'An unexpected error occurred.');
  }
}

function renderResults(data) {
  currentSQL = data.sql;
  sqlCode.textContent = formatSQL(data.sql);
  rowCountBadge.textContent = `${data.row_count.toLocaleString()} row${data.row_count !== 1 ? 's' : ''}`;
  renderTable(data.columns, data.rows);
  insightText.innerHTML = '';
  typewrite(data.insight, insightText);
  showResults();
  setTimeout(() => {
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 100);
}

function renderTable(columns, rows) {
  if (!columns.length) {
    tableWrapper.innerHTML = '<p style="color:var(--text-muted);font-size:0.85rem;padding:12px">No data returned.</p>';
    return;
  }

  const table = document.createElement('table');
  table.className = 'data-table';

  const thead = table.createTHead();
  const hRow  = thead.insertRow();
  columns.forEach(col => {
    const th = document.createElement('th');
    th.textContent = col;
    hRow.appendChild(th);
  });

  const tbody = table.createTBody();
  rows.forEach(row => {
    const tr = tbody.insertRow();
    row.forEach((cell, i) => {
      const td = tr.insertCell();
      const colName  = columns[i].toLowerCase();
      const formatted = formatCell(cell, colName);
      td.innerHTML   = formatted.html;
      td.className   = formatted.cls;
    });
  });

  tableWrapper.innerHTML = '';
  tableWrapper.appendChild(table);
}

function formatCell(value, colName) {
  if (value === null || value === undefined) {
    return { html: '<span style="color:var(--text-muted)">—</span>', cls: '' };
  }

  const isRevenue = /revenue|price|variance|risk|cost/.test(colName);
  const isNumeric = typeof value === 'number';

  if (isRevenue && isNumeric) {
    return {
      html: `₹${value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
      cls: 'currency'
    };
  }
  if (isNumeric && Number.isInteger(value)) {
    return { html: value.toLocaleString('en-IN'), cls: 'num' };
  }
  if (isNumeric) {
    return { html: value.toLocaleString('en-IN', { maximumFractionDigits: 2 }), cls: 'num' };
  }
  if (colName === 'stock_status') {
    const colors = {
      Stockout: '#ef4444', Critical: '#f59e0b',
      Low: '#3b82f6', Healthy: '#10b981'
    };
    const color = colors[value] || '#94a3b8';
    return {
      html: `<span style="color:${color};font-weight:600">${escHtml(String(value))}</span>`,
      cls: ''
    };
  }
  return { html: escHtml(String(value)), cls: '' };
}

function escHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function formatSQL(sql) {
  return sql
    .replace(/\bSELECT\b/gi, '\nSELECT')
    .replace(/\bFROM\b/gi, '\nFROM')
    .replace(/\bLEFT JOIN\b/gi, '\nLEFT JOIN')
    .replace(/\bJOIN\b/gi, '\nJOIN')
    .replace(/\bWHERE\b/gi, '\nWHERE')
    .replace(/\bGROUP BY\b/gi, '\nGROUP BY')
    .replace(/\bORDER BY\b/gi, '\nORDER BY')
    .replace(/\bHAVING\b/gi, '\nHAVING')
    .replace(/\bLIMIT\b/gi, '\nLIMIT')
    .replace(/^\n/, '')
    .trim();
}

function copySQL() {
  if (!currentSQL) return;
  navigator.clipboard.writeText(currentSQL).then(() => {
    const icon = document.getElementById('copyIcon');
    const text = document.getElementById('copyText');
    icon.textContent = '✓';
    text.textContent = 'Copied!';
    setTimeout(() => {
      icon.textContent = '⎘';
      text.textContent = 'Copy';
    }, 2000);
  });
}

function typewrite(text, el, speed = 18) {
  el.innerHTML = '';
  const cursor = document.createElement('span');
  cursor.className = 'cursor';
  el.appendChild(cursor);
  let i = 0;
  function next() {
    if (i < text.length) {
      el.insertBefore(document.createTextNode(text[i++]), cursor);
      setTimeout(next, speed);
    } else {
      cursor.remove();
    }
  }
  next();
}

function setLoading(on) {
  isLoading = on;
  askBtn.disabled = on;
  document.querySelector('.btn-text').style.display = on ? 'none' : '';
  document.querySelector('.btn-icon').style.display = on ? 'none' : '';
  btnLoader.hidden = !on;
}

function showLoadingOverlay() {
  resetSteps();
  loadingOverlay.classList.remove('hidden');
}

function hideLoadingOverlay() {
  loadingOverlay.classList.add('hidden');
}

function advanceStep(idx) {
  stepDots.forEach((dot, i) => {
    if (i < idx) {
      dot.className = 'step-dot done';
      stepEls[i].classList.add('done');
      stepEls[i].classList.remove('active-step');
    } else if (i === idx) {
      dot.className = 'step-dot active';
      stepEls[i].classList.add('active-step');
    }
  });
}

function completeAllSteps() {
  stepDots.forEach((dot, i) => {
    dot.className = 'step-dot done';
    stepEls[i].classList.add('done');
    stepEls[i].classList.remove('active-step');
  });
}

function resetSteps() {
  stepDots.forEach((dot, i) => {
    dot.className = 'step-dot';
    stepEls[i].classList.remove('done', 'active-step');
  });
}

function showResults()  { resultsSection.classList.remove('hidden'); }
function hideResults()  { resultsSection.classList.add('hidden'); }
function showError(msg) { errorText.textContent = msg; errorCard.classList.remove('hidden'); }
function hideError()    { errorCard.classList.add('hidden'); }

function shakeInput() {
  questionInput.style.animation = 'none';
  questionInput.offsetHeight;
  questionInput.style.animation = 'shake 0.4s cubic-bezier(0.36,0.07,0.19,0.97)';
  const style = document.createElement('style');
  style.textContent = `@keyframes shake {
    10%,90%{transform:translateX(-2px)}
    20%,80%{transform:translateX(4px)}
    30%,50%,70%{transform:translateX(-6px)}
    40%,60%{transform:translateX(6px)}
  }`;
  document.head.appendChild(style);
}

const delay = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  try {
    const r = await fetch('/api/health');
    const statusDot = document.querySelector('.status-dot');
    if (r.ok) {
      statusDot.className = 'status-dot status-ok';
      document.getElementById('apiStatus').querySelector('span:last-child').textContent = 'API Ready';
    } else {
      throw new Error();
    }
  } catch {
    const statusDot = document.querySelector('.status-dot');
    statusDot.className = 'status-dot status-err';
    document.getElementById('apiStatus').querySelector('span:last-child').textContent = 'API Offline';
  }
})();
