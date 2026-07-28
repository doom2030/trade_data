let priceChart = null;
let volumeChart = null;
let turnChart = null;
let closeChart = null;
let candleSeries = null;
let volumeSeries = null;
let turnSeries = null;
let closeSeries = null;
let klineByTime = new Map();
let spikeDays = [];
let lastVisibleRange = null;
let activeTab = 'kline';
let syncingCrosshair = false;
let syncingTimeScale = false;
let chartsReady = false;
let flowChartsReady = false;
/** @type {null | { closeData: any[], turnData: any[], volumeData: any[], items: any[], turnFlags: boolean[], volumeFlags: boolean[] }} */
let pendingFlowData = null;

/** Spike = value ≥ lookback median × ratio (robust to earlier spikes in the window). */
const SPIKE_LOOKBACK = 10;
const SPIKE_RATIO = 2;

const els = {
  symbolSelect: document.getElementById('symbolSelect'),
  frequency: document.getElementById('frequency'),
  adjust: document.getElementById('adjust'),
  startDate: document.getElementById('startDate'),
  endDate: document.getElementById('endDate'),
  includeExcluded: document.getElementById('includeExcluded'),
  loadBtn: document.getElementById('loadBtn'),
  stockInfo: document.getElementById('stockInfo'),
  chartStatus: document.getElementById('chartStatus'),
  priceChart: document.getElementById('priceChart'),
  volumeChart: document.getElementById('volumeChart'),
  turnChart: document.getElementById('turnChart'),
  closeChart: document.getElementById('closeChart'),
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

function formatTurn(v) {
  if (v == null || Number.isNaN(Number(v))) return '-';
  return Number(v).toFixed(2) + '%';
}

function formatPctChg(v) {
  if (v == null || Number.isNaN(Number(v))) return '-';
  const n = Number(v);
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(2)}%`;
}

function medianOf(values) {
  if (!values.length) return 0;
  const sorted = values.slice().sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 0) {
    return (sorted[mid - 1] + sorted[mid]) / 2;
  }
  return sorted[mid];
}

/**
 * Detect sudden-increase days vs prior lookback median (not mean).
 * Median resists earlier spikes in the window, so a later spike day is less likely
 * to be masked (e.g. day-4 spike won't inflate day-9's baseline as mean would).
 * Only flags increases (value ≥ baseline × ratio); ignores drops.
 */
function detectSpikeFlags(values, { lookback = SPIKE_LOOKBACK, ratio = SPIKE_RATIO } = {}) {
  const flags = values.map(() => false);
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v == null || Number.isNaN(v) || v <= 0) continue;
    const from = Math.max(0, i - lookback);
    const window = [];
    for (let j = from; j < i; j++) {
      const w = values[j];
      if (w != null && !Number.isNaN(w) && w > 0) window.push(w);
    }
    if (window.length < Math.min(3, lookback)) continue;
    const baseline = medianOf(window);
    if (baseline <= 0) continue;
    if (v >= baseline * ratio) flags[i] = true;
  }
  return flags;
}

function spikeLabel(row) {
  if (!row) return '';
  if (row.spikeTurn && row.spikeVolume) return '换手·量突增';
  if (row.spikeTurn) return '换手突增';
  if (row.spikeVolume) return '量突增';
  return '';
}

function clearSpikeMarkers() {
  try { turnSeries?.setMarkers([]); } catch (_) { /* ignore */ }
  try { volumeSeries?.setMarkers([]); } catch (_) { /* ignore */ }
}

function applySpikeMarkers(items, turnFlags, volumeFlags) {
  const turnMarkers = [];
  const volumeMarkers = [];
  for (let i = 0; i < items.length; i++) {
    if (turnFlags[i]) {
      turnMarkers.push({
        time: items[i].time,
        position: 'aboveBar',
        color: '#f59e0b',
        shape: 'circle',
        text: '突',
      });
    }
    if (volumeFlags[i]) {
      volumeMarkers.push({
        time: items[i].time,
        position: 'aboveBar',
        color: '#f59e0b',
        shape: 'arrowUp',
        text: '突',
      });
    }
  }
  try { turnSeries.setMarkers(turnMarkers); } catch (_) { /* ignore */ }
  try { volumeSeries.setMarkers(volumeMarkers); } catch (_) { /* ignore */ }
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

function klineCharts() {
  return [priceChart].filter(Boolean);
}

function flowCharts() {
  return [closeChart, turnChart, volumeChart].filter(Boolean);
}

function visibleCharts() {
  return activeTab === 'flow' ? flowCharts() : klineCharts();
}

function allCharts() {
  return [...klineCharts(), ...flowCharts()];
}

function applyChartTheme() {
  const theme = buildChartTheme();
  for (const chart of allCharts()) chart.applyOptions(theme);
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
  const pct = row.pct_chg;
  const pctCls = pct == null || Number.isNaN(Number(pct))
    ? ''
    : (Number(pct) > 0 ? 'up' : (Number(pct) < 0 ? 'down' : ''));

  if (activeTab === 'flow') {
    const spike = spikeLabel(row);
    els.chartHover.hidden = false;
    els.chartHover.innerHTML = `
      <span class="hover-date">${formatChartDate(row.time)}</span>
      ${spike ? `<span class="hover-spike">${spike}</span>` : ''}
      <span class="${cls}"><em>收</em>${formatPrice(row.close)}</span>
      <span class="${pctCls}"><em>涨跌</em>${formatPctChg(row.pct_chg)}</span>
      <span><em>换手</em>${formatTurn(row.turn)}</span>
      <span><em>量</em>${formatVolume(row.volume)}</span>
    `;
    return;
  }

  els.chartHover.hidden = false;
  els.chartHover.innerHTML = `
    <span class="hover-date">${formatChartDate(row.time)}</span>
    <span><em>开</em>${formatPrice(row.open)}</span>
    <span><em>高</em>${formatPrice(row.high)}</span>
    <span><em>低</em>${formatPrice(row.low)}</span>
    <span class="${cls}"><em>收</em>${formatPrice(row.close)}</span>
    <span class="${pctCls}"><em>涨跌</em>${formatPctChg(row.pct_chg)}</span>
    <span><em>量</em>${formatVolume(row.volume)}</span>
    <span><em>换手</em>${formatTurn(row.turn)}</span>
  `;
}

function rangesEqual(a, b) {
  if (!a || !b) return a === b;
  return a.from === b.from && a.to === b.to;
}

function syncVisibleRange(source, targets) {
  if (!source || syncingTimeScale) return;
  const range = source.timeScale().getVisibleLogicalRange();
  if (!range) return;
  lastVisibleRange = range;
  syncingTimeScale = true;
  try {
    for (const target of targets) {
      if (!target || target === source) continue;
      const current = target.timeScale().getVisibleLogicalRange();
      if (rangesEqual(range, current)) continue;
      target.timeScale().setVisibleLogicalRange(range);
    }
  } catch (_) { /* ignore */ }
  syncingTimeScale = false;
}

function applyVisibleRange(charts) {
  if (!charts.length) return;
  syncingTimeScale = true;
  try {
    if (lastVisibleRange) {
      for (const chart of charts) {
        try { chart.timeScale().setVisibleLogicalRange(lastVisibleRange); } catch (_) { /* ignore */ }
      }
    } else {
      fitChartsToWidth(charts);
    }
  } finally {
    syncingTimeScale = false;
  }
}

function fitChartsToWidth(charts) {
  if (!charts.length) return;
  const wasSyncing = syncingTimeScale;
  syncingTimeScale = true;
  try {
    for (const chart of charts) {
      try {
        chart.timeScale().applyOptions({
          rightOffset: 0,
          fixLeftEdge: true,
          fixRightEdge: true,
        });
        chart.timeScale().fitContent();
      } catch (_) { /* ignore */ }
    }
    const range = charts[0].timeScale().getVisibleLogicalRange();
    lastVisibleRange = range;
    if (range) {
      for (const chart of charts.slice(1)) {
        try { chart.timeScale().setVisibleLogicalRange(range); } catch (_) { /* ignore */ }
      }
    }
  } finally {
    syncingTimeScale = wasSyncing;
  }
}

function sizeChartToContainer(chart) {
  const el = chartElement(chart);
  if (!el || !chart) return;
  const width = el.clientWidth;
  const height = el.clientHeight || chartFallbackHeight(chart);
  if (width > 0) {
    chart.applyOptions({ width, height });
  }
}

function clearOtherCrosshairs(except, charts) {
  for (const chart of charts) {
    if (chart === except) continue;
    try { chart.clearCrosshairPosition?.(); } catch (_) { /* ignore */ }
  }
}

function setCrosshairsForTime(time, except) {
  const bar = klineByTime.get(timeKey(time));
  if (!bar) return;
  try {
    if (activeTab === 'kline') {
      if (except !== priceChart && candleSeries) {
        priceChart.setCrosshairPosition(bar.close ?? 0, time, candleSeries);
      }
      return;
    }
    if (except !== closeChart && closeSeries) {
      closeChart.setCrosshairPosition(bar.close ?? 0, time, closeSeries);
    }
    if (except !== turnChart && turnSeries) {
      turnChart.setCrosshairPosition(bar.turn ?? 0, time, turnSeries);
    }
    if (except !== volumeChart && volumeSeries) {
      volumeChart.setCrosshairPosition(bar.volume ?? 0, time, volumeSeries);
    }
  } catch (_) { /* ignore */ }
}

function bindChartInteractions(chart, groupFn) {
  chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
    syncVisibleRange(chart, groupFn());
  });
  chart.subscribeCrosshairMove((param) => {
    if (syncingCrosshair) return;
    const group = groupFn();
    if (!param || param.time == null || !param.point) {
      hideHoverInfo();
      syncingCrosshair = true;
      clearOtherCrosshairs(chart, group);
      syncingCrosshair = false;
      return;
    }
    showHoverInfo(param.time);
    syncingCrosshair = true;
    setCrosshairsForTime(param.time, chart);
    syncingCrosshair = false;
  });
}

function initPriceChart() {
  const chartTheme = buildChartTheme();
  priceChart = LightweightCharts.createChart(els.priceChart, { ...chartTheme, height: 480 });
  candleSeries = priceChart.addCandlestickSeries({
    upColor: '#34d399', downColor: '#f87171',
    borderUpColor: '#34d399', borderDownColor: '#f87171',
    wickUpColor: '#34d399', wickDownColor: '#f87171',
  });
  bindChartInteractions(priceChart, klineCharts);
  chartsReady = true;
}

function ensureFlowCharts() {
  if (flowChartsReady || typeof LightweightCharts === 'undefined') return;
  const chartTheme = buildChartTheme();

  closeChart = LightweightCharts.createChart(els.closeChart, { ...chartTheme, height: 180 });
  closeSeries = closeChart.addLineSeries({
    color: '#d4a853',
    lineWidth: 2,
    priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
  });
  closeChart.timeScale().applyOptions({ visible: false });
  bindChartInteractions(closeChart, flowCharts);

  turnChart = LightweightCharts.createChart(els.turnChart, { ...chartTheme, height: 180 });
  turnSeries = turnChart.addLineSeries({
    color: '#60a5fa',
    lineWidth: 2,
    priceFormat: { type: 'custom', formatter: (v) => `${Number(v).toFixed(2)}%` },
  });
  turnChart.timeScale().applyOptions({ visible: false });
  bindChartInteractions(turnChart, flowCharts);

  volumeChart = LightweightCharts.createChart(els.volumeChart, { ...chartTheme, height: 180 });
  volumeSeries = volumeChart.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: '',
  });
  volumeChart.priceScale('').applyOptions({ scaleMargins: { top: 0.1, bottom: 0 } });
  volumeChart.timeScale().applyOptions({ visible: true });
  bindChartInteractions(volumeChart, flowCharts);

  flowChartsReady = true;
  for (const chart of flowCharts()) sizeChartToContainer(chart);
  if (pendingFlowData) {
    applyFlowSeriesData(pendingFlowData);
    pendingFlowData = null;
  }
  fitChartsToWidth(flowCharts());
}

function applyFlowSeriesData({ closeData, turnData, volumeData, items, turnFlags, volumeFlags }) {
  if (!flowChartsReady) {
    pendingFlowData = { closeData, turnData, volumeData, items, turnFlags, volumeFlags };
    return;
  }
  closeSeries.setData(closeData);
  turnSeries.setData(turnData);
  volumeSeries.setData(volumeData);
  applySpikeMarkers(items, turnFlags, volumeFlags);
}

function chartElement(chart) {
  if (chart === priceChart) return els.priceChart;
  if (chart === closeChart) return els.closeChart;
  if (chart === turnChart) return els.turnChart;
  if (chart === volumeChart) return els.volumeChart;
  return null;
}

function chartFallbackHeight(chart) {
  if (chart === priceChart) return 480;
  return 180;
}

function resizeVisibleCharts({ fit = false } = {}) {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const charts = visibleCharts();
      for (const chart of charts) sizeChartToContainer(chart);
      if (fit || !lastVisibleRange) {
        fitChartsToWidth(charts);
      } else {
        applyVisibleRange(charts);
      }
    });
  });
}

function switchTab(tab) {
  if (tab !== 'kline' && tab !== 'flow') return;

  activeTab = tab;

  document.querySelectorAll('.chart-tab').forEach((btn) => {
    const on = btn.dataset.tab === tab;
    btn.classList.toggle('active', on);
    btn.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  document.querySelectorAll('.chart-panel').forEach((panel) => {
    const on = panel.dataset.panel === tab;
    panel.classList.toggle('is-active', on);
    if (on) panel.removeAttribute('hidden');
    else panel.setAttribute('hidden', '');
  });

  hideHoverInfo();
  if (tab === 'flow') ensureFlowCharts();
  // Tab panels were hidden; force fit so series fill the full width.
  resizeVisibleCharts({ fit: true });
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
      spikeDays = [];
      pendingFlowData = null;
      lastVisibleRange = null;
      candleSeries.setData([]);
      if (flowChartsReady) {
        closeSeries.setData([]);
        volumeSeries.setData([]);
        turnSeries.setData([]);
        clearSpikeMarkers();
      }
      return;
    }

    const turnValues = data.items.map((d) => (d.turn == null ? null : Number(d.turn)));
    const volumeValues = data.items.map((d) => (d.volume == null ? 0 : Number(d.volume)));
    const turnFlags = detectSpikeFlags(turnValues);
    const volumeFlags = detectSpikeFlags(volumeValues);

    spikeDays = [];
    klineByTime = new Map(
      data.items.map((d, i) => {
        const spikeTurn = !!turnFlags[i];
        const spikeVolume = !!volumeFlags[i];
        if (spikeTurn || spikeVolume) {
          spikeDays.push({
            time: d.time,
            spikeTurn,
            spikeVolume,
            label: spikeLabel({ spikeTurn, spikeVolume }),
          });
        }
        return [timeKey(d.time), {
          time: d.time,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
          volume: d.volume || 0,
          turn: d.turn,
          pct_chg: d.pct_chg,
          spikeTurn,
          spikeVolume,
        }];
      }),
    );

    candleSeries.setData(data.items.map(d => ({
      time: d.time, open: d.open, high: d.high, low: d.low, close: d.close,
    })));

    const closeData = data.items.map(d => ({
      time: d.time,
      value: d.close == null ? 0 : Number(d.close),
    }));
    const turnData = data.items.map(d => ({
      time: d.time,
      value: d.turn == null ? 0 : Number(d.turn),
    }));
    const volumeData = data.items.map((d, i) => {
      const up = d.close >= d.open;
      if (volumeFlags[i]) {
        return {
          time: d.time,
          value: d.volume || 0,
          color: up ? 'rgba(245,158,11,0.85)' : 'rgba(217,119,6,0.85)',
        };
      }
      return {
        time: d.time,
        value: d.volume || 0,
        color: up ? 'rgba(52,211,153,0.4)' : 'rgba(248,113,113,0.4)',
      };
    });
    applyFlowSeriesData({
      closeData,
      turnData,
      volumeData,
      items: data.items,
      turnFlags,
      volumeFlags,
    });

    lastVisibleRange = null;
    resizeVisibleCharts({ fit: true });
    if (flowChartsReady && activeTab === 'kline') {
      // Keep the hidden flow group in sync for the next tab switch.
      for (const chart of flowCharts()) sizeChartToContainer(chart);
      fitChartsToWidth(flowCharts());
    }

    let suspMsg = '';
    if (data.suspensions?.length) {
      const u = data.suspensions.filter(s => !s.resolved);
      if (u.length) suspMsg = ` · 停牌 ${u.map(s => s.date).join(', ')}`;
    }
    let spikeMsg = '';
    if (spikeDays.length) {
      const dates = spikeDays.map((s) => formatChartDate(s.time)).join('、');
      spikeMsg = ` · 突增异常 ${spikeDays.length} 天：${dates}`;
    }
    setStatus(`已加载 ${data.items.length} 条 K 线${spikeMsg}${suspMsg}`);
  } catch (e) {
    setStatus('加载失败: ' + e.message, 'error');
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
  start.setDate(start.getDate() - 90);
  return { start: toISODate(start), end: toISODate(end) };
}

function openDatePicker(input) {
  if (!input) return;
  if (typeof input.showPicker === 'function') {
    try { input.showPicker(); } catch (_) { /* ignore unsupported */ }
  }
}

document.getElementById('chartTabs')?.addEventListener('click', (event) => {
  const btn = event.target.closest('.chart-tab');
  if (!btn) return;
  event.preventDefault();
  switchTab(btn.dataset.tab);
});

els.loadBtn?.addEventListener('click', loadKlines);
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
window.addEventListener('resize', () => {
  if (chartsReady) resizeVisibleCharts();
});

if (typeof LightweightCharts !== 'undefined') {
  initPriceChart();
  updateStockInfo();
  if (window.CHART_CONFIG?.defaultSymbol) loadKlines();
}
