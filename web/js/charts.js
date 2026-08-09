/** Lightweight SVG bar charts for Reports trends. */

function chartWidth(container) {
  return Math.max(container.clientWidth || 640, 320);
}

function formatHours(seconds) {
  const hours = seconds / 3600;
  if (hours >= 10) return `${Math.round(hours)}h`;
  if (hours >= 1) return `${hours.toFixed(1)}h`;
  return `${Math.round(seconds / 60)}m`;
}

function formatMiles(meters) {
  const miles = meters / 1609.344;
  if (miles >= 10) return `${Math.round(miles)} mi`;
  if (miles >= 1) return `${miles.toFixed(1)} mi`;
  return `${Math.round(meters)} m`;
}

function escapeTooltipText(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function bindChartTooltip(container, svg, buckets, buildLines) {
  const tooltip = document.createElement("div");
  tooltip.className = "chart-tooltip hidden";
  tooltip.setAttribute("role", "tooltip");
  container.appendChild(tooltip);

  const hide = () => tooltip.classList.add("hidden");

  const show = (event, index) => {
    const bucket = buckets[index];
    if (!bucket) return;
    const lines = buildLines(bucket);
    tooltip.innerHTML = lines.map((line) => `<div>${escapeTooltipText(line)}</div>`).join("");
    tooltip.classList.remove("hidden");

    const hostRect = container.getBoundingClientRect();
    const x = event.clientX - hostRect.left;
    const y = event.clientY - hostRect.top;
    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y}px`;
  };

  svg.querySelectorAll("[data-bucket-index]").forEach((hitArea) => {
    hitArea.addEventListener("mouseenter", (event) => show(event, Number(hitArea.dataset.bucketIndex)));
    hitArea.addEventListener("mousemove", (event) => show(event, Number(hitArea.dataset.bucketIndex)));
    hitArea.addEventListener("mouseleave", hide);
  });

  svg.addEventListener("mouseleave", hide);
}

export function renderStackedBarChart(container, { buckets, series, emptyLabel = "No data" }) {
  if (!container) return;
  if (!buckets?.length) {
    container.innerHTML = `<div class="chart-empty">${emptyLabel}</div>`;
    return;
  }

  const width = chartWidth(container);
  const height = 220;
  const margin = { top: 12, right: 12, bottom: 48, left: 44 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;
  const barGap = 4;
  const barWidth = Math.max(4, (innerW - barGap * (buckets.length - 1)) / buckets.length);

  const totals = buckets.map((bucket) =>
    series.reduce((sum, item) => sum + (bucket[item.key] || 0), 0)
  );
  const maxTotal = Math.max(...totals, 1);

  const bars = buckets
    .map((bucket, index) => {
      const x = margin.left + index * (barWidth + barGap);
      let yCursor = margin.top + innerH;
      const segments = series
        .map((item) => {
          const value = bucket[item.key] || 0;
          if (value <= 0) return "";
          const segH = (value / maxTotal) * innerH;
          yCursor -= segH;
          return `<rect x="${x}" y="${yCursor}" width="${barWidth}" height="${segH}" fill="${item.color}" rx="2" pointer-events="none"></rect>`;
        })
        .join("");
      const hitArea = `<rect class="chart-bar-hit" data-bucket-index="${index}" x="${x}" y="${margin.top}" width="${barWidth}" height="${innerH}" fill="transparent"></rect>`;
      const label =
        buckets.length <= 14 || index % Math.ceil(buckets.length / 12) === 0
          ? `<text x="${x + barWidth / 2}" y="${height - 8}" text-anchor="middle" class="chart-axis-label" pointer-events="none">${bucket.label}</text>`
          : "";
      return `${segments}${hitArea}${label}`;
    })
    .join("");

  const yTicks = [0, 0.5, 1]
    .map((pct) => {
      const y = margin.top + innerH * (1 - pct);
      const value = maxTotal * pct;
      return `
        <line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" class="chart-grid-line" />
        <text x="${margin.left - 8}" y="${y + 4}" text-anchor="end" class="chart-axis-label">${formatHours(value)}</text>`;
    })
    .join("");

  const legend = series
    .map(
      (item) => `
      <span class="chart-legend-item">
        <span class="chart-legend-swatch" style="background:${item.color}"></span>
        ${item.label}
      </span>`
    )
    .join("");

  container.innerHTML = `
    <div class="chart-legend">${legend}</div>
    <svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Stacked bar chart">
      ${yTicks}
      ${bars}
    </svg>`;

  const svg = container.querySelector(".chart-svg");
  bindChartTooltip(container, svg, buckets, (bucket) => {
    const lines = [bucket.label];
    for (const item of series) {
      lines.push(`${item.label}: ${formatHours(bucket[item.key] || 0)}`);
    }
    return lines;
  });
}

export function renderBarChart(container, { buckets, valueKey, formatValue, color, emptyLabel = "No data", label = "Value" }) {
  if (!container) return;
  if (!buckets?.length) {
    container.innerHTML = `<div class="chart-empty">${emptyLabel}</div>`;
    return;
  }

  const width = chartWidth(container);
  const height = 200;
  const margin = { top: 12, right: 12, bottom: 48, left: 52 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;
  const barGap = 4;
  const barWidth = Math.max(4, (innerW - barGap * (buckets.length - 1)) / buckets.length);
  const values = buckets.map((bucket) => bucket[valueKey] || 0);
  const maxValue = Math.max(...values, 1);
  const fmt = formatValue || ((v) => String(v));

  const bars = buckets
    .map((bucket, index) => {
      const value = bucket[valueKey] || 0;
      const barH = (value / maxValue) * innerH;
      const x = margin.left + index * (barWidth + barGap);
      const y = margin.top + innerH - barH;
      const showLabel =
        buckets.length <= 14 || index % Math.ceil(buckets.length / 12) === 0;
      return `
        <rect x="${x}" y="${y}" width="${barWidth}" height="${barH}" fill="${color}" rx="2">
          <title>${bucket.label}: ${fmt(value)}</title>
        </rect>
        ${
          showLabel
            ? `<text x="${x + barWidth / 2}" y="${height - 8}" text-anchor="middle" class="chart-axis-label">${bucket.label}</text>`
            : ""
        }`;
    })
    .join("");

  const yTicks = [0, 0.5, 1]
    .map((pct) => {
      const y = margin.top + innerH * (1 - pct);
      const value = maxValue * pct;
      return `
        <line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" class="chart-grid-line" />
        <text x="${margin.left - 8}" y="${y + 4}" text-anchor="end" class="chart-axis-label">${fmt(value)}</text>`;
    })
    .join("");

  container.innerHTML = `
    <div class="chart-legend"><span class="chart-legend-item"><span class="chart-legend-swatch" style="background:${color}"></span>${label}</span></div>
    <svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Bar chart">
      ${yTicks}
      ${bars}
    </svg>`;
}

export { formatMiles as formatTrendDistance };
