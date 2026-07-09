let priceChart = null;
let volumeChart = null;
let candleSeries = null;
let volumeSeries = null;

const els = {
  symbolSelect: document.getElementById('symbolSelect'),
  frequency: document.getElementById('frequency'),
  adjust: document.getElementById('adjust'),
  startDate: document.getElementById('startDate'),
  endDate: document.getElementById('endDate'),
  includeExcluded: document.getElementById('includeExcluded'),
  loadBtn: document.getElementById('loadBtn'),
  backfillBtn: document.getElementById('backfillBtn'),
  stockInfo: document.getElementById('stockInfo'),
  chartStatus: document.getElementById('chartStatus'),
  priceChart: document.getElementById('priceChart'),
  volumeChart: document.getElementById('volumeChart'),
  jobStatus: document.getElementById('jobStatus'),
};

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function buildChartTheme() {
  return {
    layout: { background: { color: 'transparent' }, textColor: cssVar('--chart-text', '#94a3b8') },
    grid: {
      vertLines: { color: cssVar('--chart-grid', 'rgba(148,163,184,0.06)') },
      horzLines: { color: cssVar('--chart-grid', 'rgba(148,163,184,0.06)') },
    },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    timeScale: { borderColor: cssVar('--chart-border', 'rgba(148,163,184,0.12)') },
    rightPriceScale: { borderColor: cssVar('--chart-border', 'rgba(148,163,184,0.12)') },
  };
}

function applyChartTheme() {
  const theme = buildChartTheme();
  priceChart?.applyOptions(theme);
  volumeChart?.applyOptions(theme);
}

function setStatus(msg, type = '') {
  els.chartStatus.textContent = msg;
  els.chartStatus.className = 'chart-status ' + type;
}

function updateStockInfo() {
  const opt = els.symbolSelect.selectedOptions[0];
  if (!opt) return;
  const status = opt.dataset.status;
  const statusLabel = opt.dataset.statusLabel || status;
  const boardLabel = opt.dataset.boardLabel || opt.dataset.board;
  const industry = opt.dataset.industry;
  els.stockInfo.innerHTML = `
    <div><span class="label">代码</span><span class="value">${opt.value}</span></div>
    <div><span class="label">板块</span><span class="value">${boardLabel}</span></div>
    <div><span class="label">状态</span><span class="value">${statusLabel}</span></div>
    <div><span class="label">行业</span><span class="value">${industry || '-'}</span></div>
  `;
  els.backfillBtn.style.display = status === 'active' ? 'inline-flex' : 'none';
}

function initCharts() {
  const chartTheme = buildChartTheme();
  priceChart = LightweightCharts.createChart(els.priceChart, { ...chartTheme, height: 420 });
  candleSeries = priceChart.addCandlestickSeries({
    upColor: '#34d399', downColor: '#f87171',
    borderUpColor: '#34d399', borderDownColor: '#f87171',
    wickUpColor: '#34d399', wickDownColor: '#f87171',
  });
  volumeChart = LightweightCharts.createChart(els.volumeChart, { ...chartTheme, height: 140 });
  volumeSeries = volumeChart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: '' });
  volumeChart.priceScale('').applyOptions({ scaleMargins: { top: 0.1, bottom: 0 } });
}

async function loadKlines() {
  const symbol = els.symbolSelect.value;
  if (!symbol) { setStatus('请选择股票', 'empty'); return; }

  const freq = els.frequency.value;
  const adjust = els.adjust.value;
  const start = els.startDate.value;
  const end = els.endDate.value;

  setStatus('加载中...', 'loading');
  try {
    const url = `/api/klines/${freq}?symbol=${encodeURIComponent(symbol)}&start=${start}&end=${end}&adjust=${adjust}`;
    const resp = await fetch(url);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(typeof err.detail === 'string' ? err.detail : resp.statusText);
    }
    const data = await resp.json();

    if (!data.items.length) {
      setStatus('该日期范围内无数据', 'empty');
      candleSeries.setData([]);
      volumeSeries.setData([]);
      return;
    }

    candleSeries.setData(data.items.map(d => ({
      time: d.time, open: d.open, high: d.high, low: d.low, close: d.close,
    })));
    volumeSeries.setData(data.items.map(d => ({
      time: d.time,
      value: d.volume || 0,
      color: d.close >= d.open ? 'rgba(52,211,153,0.4)' : 'rgba(248,113,113,0.4)',
    })));
    priceChart.timeScale().fitContent();
    volumeChart.timeScale().fitContent();

    let suspMsg = '';
    if (data.suspensions?.length) {
      const u = data.suspensions.filter(s => !s.resolved);
      if (u.length) suspMsg = ` · 停牌 ${u.map(s => s.date).join(', ')}`;
    }
    setStatus(`已加载 ${data.items.length} 条 K 线${suspMsg}`);
  } catch (e) {
    setStatus('加载失败: ' + e.message, 'error');
  }
}

async function backfill() {
  const opt = els.symbolSelect.selectedOptions[0];
  if (!opt || opt.dataset.status !== 'active') {
    setStatus('只能对 active 股票补采', 'error');
    return;
  }
  setStatus('创建补采任务...', 'loading');
  try {
    const resp = await fetch('/api/klines/backfill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol: els.symbolSelect.value,
        frequency: els.frequency.value,
        start: els.startDate.value,
        end: els.endDate.value,
      }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(typeof err.detail === 'string' ? err.detail : resp.statusText);
    }
    const data = await resp.json();
    els.jobStatus.textContent = `补采任务 #${data.job_id} 已创建 (${data.status})`;
    window.location.href = `/jobs/${data.job_id}?message=补采任务已创建`;
  } catch (e) {
    setStatus('补采失败: ' + e.message, 'error');
  }
}

function toISODate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function defaultRangeForFrequency(freq) {
  const end = new Date();
  const start = new Date(end);
  if (freq === 'week') start.setDate(start.getDate() - 180);
  else if (freq === 'month') start.setDate(start.getDate() - 730);
  else start.setDate(start.getDate() - 30);
  return { start: toISODate(start), end: toISODate(end) };
}

function openDatePicker(input) {
  if (!input) return;
  if (typeof input.showPicker === 'function') {
    try { input.showPicker(); } catch (_) { /* ignore unsupported */ }
  }
}

els.loadBtn?.addEventListener('click', loadKlines);
els.backfillBtn?.addEventListener('click', backfill);
els.symbolSelect?.addEventListener('change', updateStockInfo);
els.frequency?.addEventListener('change', () => {
  const range = defaultRangeForFrequency(els.frequency.value);
  els.startDate.value = range.start;
  els.endDate.value = range.end;
});
els.startDate?.addEventListener('click', () => openDatePicker(els.startDate));
els.endDate?.addEventListener('click', () => openDatePicker(els.endDate));
els.includeExcluded?.addEventListener('change', () => {
  const checked = els.includeExcluded.checked;
  window.location.href = `/charts?include_excluded=${checked}`;
});

window.addEventListener('themechange', applyChartTheme);

if (typeof LightweightCharts !== 'undefined') {
  initCharts();
  updateStockInfo();
  if (window.CHART_CONFIG?.defaultSymbol) loadKlines();
}
