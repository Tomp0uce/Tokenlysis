const USD_SUFFIXES = [
  { value: 1_000_000_000_000, suffix: 'T$' },
  { value: 1_000_000_000, suffix: 'B$' },
  { value: 1_000_000, suffix: 'M$' },
  { value: 1_000, suffix: 'k$' },
];

const FEAR_GREED_BANDS = [
  { min: 0, max: 25, cssVar: '--fg-extreme-fear', fallback: '#dc2626' },
  { min: 26, max: 44, cssVar: '--fg-fear', fallback: '#f97316' },
  { min: 45, max: 54, cssVar: '--fg-neutral', fallback: '#facc15' },
  { min: 55, max: 74, cssVar: '--fg-greed', fallback: '#22c55e' },
  { min: 75, max: 100, cssVar: '--fg-extreme-greed', fallback: '#0ea5e9' },
];

const trackedCharts = new Map();

function readCssVariable(name) {
  if (typeof document === 'undefined' || typeof window === 'undefined') {
    return '';
  }
  if (typeof window.getComputedStyle !== 'function') {
    return '';
  }
  const value = window.getComputedStyle(document.documentElement).getPropertyValue(name);
  return value ? value.trim() : '';
}

function clampPercent(value) {
  if (value === null || value === undefined) {
    return 0;
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 0;
  }
  return Math.min(100, Math.max(0, numeric));
}

function gaugePalette(value) {
  const percent = clampPercent(value);
  const band = FEAR_GREED_BANDS.find((entry) => percent <= entry.max) || FEAR_GREED_BANDS[FEAR_GREED_BANDS.length - 1];
  const color = readCssVariable(band.cssVar) || band.fallback;
  return { color, cssVar: band.cssVar, value: percent };
}

function clampBandValue(value, fallback) {
  if (value === null || value === undefined) {
    return fallback;
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return fallback;
  }
  const clamped = Math.min(100, Math.max(0, numeric));
  if (!Number.isFinite(clamped)) {
    return fallback;
  }
  return clamped;
}

function buildFearGreedAnnotations() {
  let previousMax = 0;
  return FEAR_GREED_BANDS.map((band, index) => {
    const rawMin = band.min ?? (index === 0 ? 0 : previousMax);
    const min = clampBandValue(rawMin, index === 0 ? 0 : previousMax);
    const rawMax = band.max ?? previousMax;
    const max = Math.max(min, clampBandValue(rawMax, min));
    previousMax = max;
    const color = readCssVariable(band.cssVar) || band.fallback;
    return {
      y: min,
      y2: max,
      fillColor: color,
      opacity: 0.18,
      borderColor: 'transparent',
    };
  });
}

function trackChart(chart, metadata) {
  trackedCharts.set(chart, metadata);
}

function updateTrackedChart(chart, updates) {
  if (!trackedCharts.has(chart)) {
    return;
  }
  const current = trackedCharts.get(chart) || {};
  trackedCharts.set(chart, { ...current, ...updates });
}

export function formatCompactUsd(value) {
  if (value === null || value === undefined) {
    return '';
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return '';
  }
  const abs = Math.abs(numeric);
  for (const { value: threshold, suffix } of USD_SUFFIXES) {
    if (abs >= threshold) {
      const scaled = numeric / threshold;
      const precision = scaled >= 100 ? 0 : scaled >= 10 ? 1 : 2;
      const formatted = new Intl.NumberFormat('en-US', {
        minimumFractionDigits: 0,
        maximumFractionDigits: precision,
      }).format(scaled);
      return `${formatted} ${suffix}`;
    }
  }
  const digits = abs >= 1 ? 2 : 4;
  return `${new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(numeric)} $`;
}

function buildGradient(primary) {
  return {
    type: 'gradient',
    gradient: {
      shadeIntensity: 1,
      opacityFrom: 0.45,
      opacityTo: 0.05,
      stops: [0, 90, 100],
      colorStops: [
        {
          offset: 0,
          color: primary,
          opacity: 0.45,
        },
        {
          offset: 100,
          color: primary,
          opacity: 0.05,
        },
      ],
    },
  };
}

function basePalette(colorVar) {
  return {
    primary: readCssVariable(colorVar || '--chart-primary') || '#2563eb',
    muted: readCssVariable('--text-muted') || '#64748b',
    border: readCssVariable('--border-subtle') || '#e2e8f0',
  };
}

function baseAreaOptions({
  name,
  categories,
  data,
  colorVar,
  xAxisType = 'datetime',
  yFormatter,
  tooltipFormatter,
  banding,
} = {}) {
  const palette = basePalette(colorVar);
  const theme = document?.documentElement?.dataset?.theme || 'light';
  const defaultFormatter = (value) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return formatCompactUsd(0);
    }
    return formatCompactUsd(numeric);
  };
  const wrapFormatter = (formatter, fallback) => {
    if (typeof formatter === 'function') {
      return (value) => {
        const numeric = Number(value);
        const safeValue = Number.isFinite(numeric) ? numeric : 0;
        return formatter(safeValue);
      };
    }
    return fallback;
  };
  const resolvedYFormatter = wrapFormatter(yFormatter, defaultFormatter);
  const resolvedTooltipFormatter = wrapFormatter(tooltipFormatter, resolvedYFormatter);
  const options = {
    chart: {
      type: 'area',
      height: 280,
      toolbar: { show: false },
      zoom: { enabled: false },
      selection: { enabled: false },
      animations: { easing: 'easeinout', speed: 600 },
      fontFamily: 'Inter, "Segoe UI", sans-serif',
      foreColor: palette.muted,
    },
    series: [
      {
        name,
        data,
      },
    ],
    dataLabels: { enabled: false },
    stroke: { curve: 'smooth', width: 3 },
    colors: [palette.primary],
    fill: buildGradient(palette.primary),
    grid: {
      borderColor: palette.border,
      strokeDashArray: 4,
      padding: { left: 12, right: 12 },
    },
    markers: {
      size: 0,
      hover: { sizeOffset: 3 },
    },
    xaxis: {
      type: xAxisType,
      categories,
      labels: {
        style: { colors: palette.muted },
      },
      axisBorder: { color: palette.border },
      axisTicks: { color: palette.border },
    },
    yaxis: {
      labels: {
        formatter: resolvedYFormatter,
        style: { colors: palette.muted },
      },
    },
    tooltip: {
      theme,
      shared: false,
      intersect: false,
      x: { format: 'dd MMM yy' },
      y: {
        formatter: resolvedTooltipFormatter,
      },
    },
    noData: {
      text: 'Aucune donnée',
    },
  };
  if (banding === 'fear-greed') {
    options.yaxis = {
      ...options.yaxis,
      min: 0,
      max: 100,
      tickAmount: 5,
    };
    options.annotations = { yaxis: buildFearGreedAnnotations() };
  }
  return options;
}

export async function createAreaChart(element, config = {}) {
  if (!element) {
    throw new Error('Chart container is required');
  }
  if (typeof window === 'undefined' || !window.ApexCharts) {
    throw new Error('ApexCharts is unavailable');
  }
  const options = baseAreaOptions(config);
  const colorToken = config?.colorVar || '--chart-primary';
  const banding = config?.banding;
  const chart = new window.ApexCharts(element, options);
  trackChart(chart, { type: 'area', colorVar: colorToken, banding });
  await chart.render();
  return chart;
}

function gaugeOptions(value, classification) {
  const palette = gaugePalette(value);
  const theme = document?.documentElement?.dataset?.theme || 'light';
  return {
    chart: {
      type: 'radialBar',
      height: 260,
      background: 'transparent',
      animations: { easing: 'easeinout', speed: 500 },
      fontFamily: 'Inter, "Segoe UI", sans-serif',
    },
    series: [clampPercent(value)],
    labels: [classification],
    colors: [palette.color],
    fill: buildGradient(palette.color),
    stroke: { lineCap: 'round' },
    plotOptions: {
      radialBar: {
        startAngle: -120,
        endAngle: 120,
        hollow: {
          size: '58%',
          background: 'transparent',
        },
        track: {
          background: 'rgba(148, 163, 184, 0.15)',
          strokeWidth: '80%',
        },
        dataLabels: {
          name: {
            fontSize: '0.9rem',
            offsetY: 70,
            color: readCssVariable('--text-muted') || '#64748b',
          },
          value: {
            formatter: (val) => `${Math.round(val)}`,
            fontSize: '2.4rem',
            fontWeight: 700,
            offsetY: -10,
            color: readCssVariable('--text-primary') || '#0f172a',
          },
        },
      },
    },
    tooltip: {
      enabled: false,
    },
    theme: { mode: theme === 'dark' ? 'dark' : 'light' },
  };
}

export async function createRadialGauge(element, { value = 0, classification = '' } = {}) {
  if (!element) {
    throw new Error('Chart container is required');
  }
  if (typeof window === 'undefined' || !window.ApexCharts) {
    throw new Error('ApexCharts is unavailable');
  }
  const label = String(classification || '').trim() || 'Indéterminé';
  const chart = new window.ApexCharts(element, gaugeOptions(value, label));
  trackChart(chart, { type: 'gauge', value: clampPercent(value), classification: label });
  await chart.render();
  return chart;
}

export async function updateRadialGauge(chart, { value = 0, classification = '' } = {}) {
  if (!chart) {
    return;
  }
  const label = String(classification || '').trim() || 'Indéterminé';
  const palette = gaugePalette(value);
  updateTrackedChart(chart, { type: 'gauge', value: clampPercent(value), classification: label });
  await chart.updateOptions(
    {
      labels: [label],
      colors: [palette.color],
      fill: buildGradient(palette.color),
      series: [clampPercent(value)],
    },
    false,
    true,
  );
}

export async function refreshChartsTheme(theme) {
  const normalized = theme === 'dark' ? 'dark' : 'light';
  const updates = [];
  trackedCharts.forEach((metadata, chart) => {
    if (metadata?.type === 'area') {
      const palette = basePalette(metadata.colorVar);
      const yaxisUpdate = {
        labels: { style: { colors: palette.muted } },
      };
      if (metadata.banding === 'fear-greed') {
        yaxisUpdate.min = 0;
        yaxisUpdate.max = 100;
        yaxisUpdate.tickAmount = 5;
      }
      const options = {
        theme: { mode: normalized },
        colors: [palette.primary],
        fill: buildGradient(palette.primary),
        xaxis: {
          labels: { style: { colors: palette.muted } },
          axisBorder: { color: palette.border },
          axisTicks: { color: palette.border },
        },
        yaxis: yaxisUpdate,
        grid: { borderColor: palette.border },
        tooltip: { theme: normalized },
      };
      if (metadata.banding === 'fear-greed') {
        options.annotations = { yaxis: buildFearGreedAnnotations() };
      }
      updates.push(
        chart.updateOptions(
          options,
          false,
          true,
        ),
      );
    } else if (metadata?.type === 'gauge') {
      const palette = gaugePalette(metadata.value ?? 0);
      updates.push(
        chart.updateOptions(
          {
            chart: { background: 'transparent' },
            labels: [metadata.classification || ''],
            colors: [palette.color],
            fill: buildGradient(palette.color),
          },
          false,
          true,
        ),
      );
    }
  });
  await Promise.allSettled(updates);
}

export function destroyTrackedCharts() {
  const destructions = [];
  trackedCharts.forEach((_, chart) => {
    if (typeof chart.destroy === 'function') {
      destructions.push(chart.destroy());
    }
  });
  trackedCharts.clear();
  return Promise.allSettled(destructions);
}

export const __test__ = {
  getTrackedCharts: () =>
    Array.from(trackedCharts.entries()).map(([chart, metadata]) => ({ chart, metadata })),
  baseAreaOptions,
  basePalette,
};
