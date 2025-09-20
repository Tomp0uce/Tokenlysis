const USD_SUFFIXES = [
  { value: 1_000_000_000_000, suffix: 'TUSD' },
  { value: 1_000_000_000, suffix: 'BUSD' },
  { value: 1_000_000, suffix: 'MUSD' },
  { value: 1_000, suffix: 'kUSD' },
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
  return `${new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(numeric)} USD`;
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

function baseAreaOptions({ name, categories, data, colorVar, xAxisType = 'datetime' }) {
  const palette = basePalette(colorVar);
  const theme = document?.documentElement?.dataset?.theme || 'light';
  return {
    chart: {
      type: 'area',
      height: 280,
      toolbar: { show: false },
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
        formatter: formatCompactUsd,
        style: { colors: palette.muted },
      },
    },
    tooltip: {
      theme,
      shared: false,
      intersect: false,
      x: { format: 'dd MMM yy' },
      y: {
        formatter: formatCompactUsd,
      },
    },
    noData: {
      text: 'Aucune donnée',
    },
  };
}

export async function createAreaChart(element, { name, categories, data, colorVar, xAxisType }) {
  if (!element) {
    throw new Error('Chart container is required');
  }
  if (typeof window === 'undefined' || !window.ApexCharts) {
    throw new Error('ApexCharts is unavailable');
  }
  const options = baseAreaOptions({ name, categories, data, colorVar, xAxisType });
  const chart = new window.ApexCharts(element, options);
  trackedCharts.set(chart, colorVar || '--chart-primary');
  await chart.render();
  return chart;
}

export async function refreshChartsTheme(theme) {
  const normalized = theme === 'dark' ? 'dark' : 'light';
  const updates = [];
  trackedCharts.forEach((colorVar, chart) => {
    const palette = basePalette(colorVar);
    updates.push(
      chart.updateOptions(
        {
          theme: { mode: normalized },
          colors: [palette.primary],
          fill: buildGradient(palette.primary),
          xaxis: {
            labels: { style: { colors: palette.muted } },
            axisBorder: { color: palette.border },
            axisTicks: { color: palette.border },
          },
          yaxis: {
            labels: { style: { colors: palette.muted } },
          },
          grid: { borderColor: palette.border },
          tooltip: { theme: normalized },
        },
        false,
        true,
      ),
    );
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
  getTrackedCharts: () => Array.from(trackedCharts.entries()).map(([chart, colorVar]) => ({ chart, colorVar })),
  baseAreaOptions,
  basePalette,
};
