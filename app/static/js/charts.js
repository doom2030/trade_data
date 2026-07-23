let priceChart = null;
let volumeChart = null;
let candleSeries = null;
let volumeSeries = null;
let klineByTime = new Map();
let syncingCrosshair = false;
let syncingTimeScale = false;

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
  chartHover: document.getElementById('chartHover'),
};

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function formatChartDate(time) {
  if (time == null) return '-';
  if (typeof time === 'string') {
    // API returns YYYY-MM-DD
    return time.replace(/-/g, '/');
  }
  if (typeof time === 'object' && time.year != null) {
    const m = String(time.month).padStart(2, '0');
    const d = String(time.day).padStart(2, '0');
    return `${time.year}/${m}/${d}`;
  }
  if (typeof time === 'number') {
    const dt = new Date(time * 1000);
    const y = dt.getUTCFullYear();
    const m = String(dt.getUTCMonth() + 1).padStart(2, '0');
    const d = String(dt.getUTCDate()).padStart(2, '0');
    return `${y}/${m}/${d}`;
  }
  return String(time);
}

function formatPrice(v) {
  if (v == null || Number.isNaN(Number(v))) return '-';
  return Number(v).toFixed(2);
}

function formatVolume(v) {
  if (v == null || Number.isNaN(Number(v))) return '-';
  const n = Number(v);
  if (n >= 1e8) return (n / 1e8).toFixed(2) + '亿';
  if (n >= 1e4) return (n / 1e4).toFixed(2) + '万';
  return String(Math.round(n));
}

function buildChartTheme() {
  return {
    layout: {
      background: { color: 'transparent' },
      textColor: cssVar('--chart-text', '#94a3b8'),
      attributionLogo: false,
    },
    grid: {
      vertLines: { color: cssVar('--chart-grid', 'rgba(148,163,184,0.06)') },
      horzLines: { color: cssVar('--chart-grid', 'rgba(148,163,184,0.06)') },
    },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    timeScale: {
      borderColor: cssVar('--chart-border', 'rgba(148,163,184,0.12)'),
    },
    rightPriceScale: { borderColor: cssVar('--chart-border', 'rgba(148,163,184,0.12)') },
    localization: {
      locale: 'zh-CN',
      dateFormat: 'yyyy/MM/dd',
      timeFormatter: (time) => formatChartDate(time),
    },
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

function timeKey(time) {
  if (time == null) return '';
  if (typeof time === 'string') return time;
  if (typeof time === 'object' && time.year != null) {
    return `${time.year}-${String(time.month).padStart(2, '0')}-${String(time.day).padStart(2, '0')}`;
  }
  return String(time);
}

function hideHoverInfo() {
  if (!els.chartHover) return;
  els.chartHover.hidden = true;
  els.chartHover.innerHTML = '';
}

function showHoverInfo(time) {
  if (!els.chartHover) return;
  const row = klineByTime.get(timeKey(time));
  if (!row) {
    hideHoverInfo();
    return;
  }
  const up = row.close >= row.open;
  const cls = up ? 'up' : 'down';
  els.chartHover.hidden = false;
  els.chartHover.innerHTML = `
    <span class="hover-date">${formatChartDate(row.time)}</span>
    <span><em>开</em>${formatPrice(row.open)}</span>
    <span><em>高</em>${formatPrice(row.high)}</span>
    <span><em>低</em>${formatPrice(row.low)}</span>
    <span class="${cls}"><em>收</em>${formatPrice(row.close)}</span>
    <span><em>量</em>${formatVolume(row.volume)}</span>
  `;
}

function rangesEqual(a, b) {
  if (!a || !b) return a === b;
  return a.from === b.from && a.to === b.to;
}

function syncVisibleRange(source, target) {
  if (!source || !target || syncingTimeScale) return;
  const range = source.timeScale().getVisibleLogicalRange();
  if (!range) return;
  const current = target.timeScale().getVisibleLogicalRange();
  if (rangesEqual(range, current)) return;
  syncingTimeScale = true;
  try {
    target.timeScale().setVisibleLogicalRange(range);
  } catch (_) { /* ignore */ }
  syncingTimeScale = false;
}

function bindTimeScaleSync() {
  priceChart.timeScale().subscribeVisibleLogicalRangeChange(() => {
    syncVisibleRange(priceChart, volumeChart);
  });
  volumeChart.timeScale().subscribeVisibleLogicalRangeChange(() => {
    syncVisibleRange(volumeChart, priceChart);
  });
}

function bindCrosshairSync() {
  priceChart.subscribeCrosshairMove((param) => {
    if (syncingCrosshair) return;
    if (!param || param.time == null || !param.point) {
      hideHoverInfo();
      syncingCrosshair = true;
      try { volumeChart?.clearCrosshairPosition?.(); } catch (_) { /* ignore */ }
      syncingCrosshair = false;
      return;
    }
    showHoverInfo(param.time);
    syncingCrosshair = true;
    try {
      if (typeof volumeChart.setCrosshairPosition === 'function' && volumeSeries) {
        const bar = klineByTime.get(timeKey(param.time));
        volumeChart.setCrosshairPosition(bar?.volume ?? 0, param.time, volumeSeries);
      }
    } catch (_) { /* ignore */ }
    syncingCrosshair = false;
  });

  volumeChart.subscribeCrosshairMove((param) => {
    if (syncingCrosshair) return;
    if (!param || param.time == null || !param.point) {
      hideHoverInfo();
      syncingCrosshair = true;
      try { priceChart?.clearCrosshairPosition?.(); } catch (_) { /* ignore */ }
      syncingCrosshair = false;
      return;
    }
    showHoverInfo(param.time);
    syncingCrosshair = true;
    try {
      if (typeof priceChart.setCrosshairPosition === 'function' && candleSeries) {
        const bar = klineByTime.get(timeKey(param.time));
        priceChart.setCrosshairPosition(bar?.close ?? 0, param.time, candleSeries);
      }
    } catch (_) { /* ignore */ }
    syncingCrosshair = false;
  });
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
  // Keep volume x-axis labels; sync range with price chart for pan/zoom.
  volumeChart.timeScale().applyOptions({ visible: true });
  bindTimeScaleSync();
  bindCrosshairSync();
}

async function loadKlines() {
  const symbol = els.symbolSelect.value;
  if (!symbol) { setStatus('请选择股票', 'empty'); return; }

  const freq = els.frequency.value;
  const adjust = els.adjust.value;
  const start = els.startDate.value;
  const end = els.endDate.value;

  setStatus('加载中...', 'loading');
  hideHoverInfo();
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
      klineByTime = new Map();
      candleSeries.setData([]);
      volumeSeries.setData([]);
      return;
    }

    klineByTime = new Map(
      data.items.map((d) => [timeKey(d.time), {
        time: d.time,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
        volume: d.volume || 0,
      }]),
    );

    candleSeries.setData(data.items.map(d => ({
      time: d.time, open: d.open, high: d.high, low: d.low, close: d.close,
    })));
    volumeSeries.setData(data.items.map(d => ({
      time: d.time,
      value: d.volume || 0,
      color: d.close >= d.open ? 'rgba(52,211,153,0.4)' : 'rgba(248,113,113,0.4)',
    })));
    syncingTimeScale = true;
    try {
      priceChart.timeScale().fitContent();
      const range = priceChart.timeScale().getVisibleLogicalRange();
      if (range) volumeChart.timeScale().setVisibleLogicalRange(range);
      else volumeChart.timeScale().fitContent();
    } finally {
      syncingTimeScale = false;
    }

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

function defaultRangeForFrequency(_freq) {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - 30);
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
