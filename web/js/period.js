const STORAGE_GRANULARITY = "phoneLocator.granularity";
const STORAGE_ANCHOR = "phoneLocator.anchorDate";

const state = {
  granularity: localStorage.getItem(STORAGE_GRANULARITY) || "day",
  anchor: loadAnchor(),
};

let onChange = () => {};

function loadAnchor() {
  const stored = localStorage.getItem(STORAGE_ANCHOR);
  if (stored && /^\d{4}-\d{2}-\d{2}$/.test(stored)) {
    return parseAnchor(stored);
  }
  return startOfDay(new Date());
}

function parseAnchor(value) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function formatAnchorDate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function startOfDay(date) {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  return d;
}

function isSameDay(a, b) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function isToday(date) {
  return isSameDay(date, new Date());
}

function isYesterday(date) {
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  return isSameDay(date, yesterday);
}

function weekStartSunday(date) {
  const d = startOfDay(date);
  d.setDate(d.getDate() - d.getDay());
  return d;
}

function monthStart(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function formatMonthDay(date, includeYear = false) {
  const opts = { month: "short", day: "numeric" };
  if (includeYear) opts.year = "numeric";
  return date.toLocaleDateString("en-US", opts);
}

function formatDayLabel(date) {
  const currentYear = new Date().getFullYear();
  const weekday = date.toLocaleDateString("en-US", { weekday: "long" });
  const datePart = formatMonthDay(date, date.getFullYear() !== currentYear);
  return `${weekday}, ${datePart}`;
}

function formatWeekRange(start, end) {
  const currentYear = new Date().getFullYear();
  const showYear =
    start.getFullYear() !== currentYear || end.getFullYear() !== currentYear;

  if (start.getMonth() === end.getMonth() && start.getFullYear() === end.getFullYear()) {
    const month = start.toLocaleDateString("en-US", { month: "short" });
    const label = `${month} ${start.getDate()} – ${end.getDate()}`;
    return showYear ? `${label}, ${start.getFullYear()}` : label;
  }

  const left = formatMonthDay(start, start.getFullYear() !== currentYear);
  const right = formatMonthDay(end, end.getFullYear() !== currentYear);
  return `${left} – ${right}`;
}

export function formatPeriodLabel(granularity, anchor) {
  const currentYear = new Date().getFullYear();

  if (granularity === "day") {
    if (isToday(anchor)) return "Today";
    if (isYesterday(anchor)) return "Yesterday";
    return formatDayLabel(anchor);
  }

  if (granularity === "week") {
    const start = weekStartSunday(anchor);
    const end = new Date(start);
    end.setDate(end.getDate() + 6);
    return formatWeekRange(start, end);
  }

  if (anchor.getFullYear() === currentYear) {
    return anchor.toLocaleDateString("en-US", { month: "long" });
  }
  return anchor.toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

export function localDateKey(iso) {
  return formatAnchorDate(new Date(iso));
}

function computeRange(granularity, anchor) {
  const now = new Date();
  const today = startOfDay(now);

  if (granularity === "day") {
    const start = startOfDay(anchor);
    const end = isToday(anchor)
      ? now
      : new Date(start.getFullYear(), start.getMonth(), start.getDate(), 23, 59, 59, 999);
    return { from: start.toISOString(), to: end.toISOString() };
  }

  if (granularity === "week") {
    const start = weekStartSunday(anchor);
    const weekEnd = new Date(start);
    weekEnd.setDate(weekEnd.getDate() + 6);
    weekEnd.setHours(23, 59, 59, 999);
    const end =
      start.getTime() === weekStartSunday(today).getTime() ? now : weekEnd;
    return { from: start.toISOString(), to: end.toISOString() };
  }

  const start = monthStart(anchor);
  const monthEnd = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0, 23, 59, 59, 999);
  const end = start.getTime() === monthStart(today).getTime() ? now : monthEnd;
  return { from: start.toISOString(), to: end.toISOString() };
}

function canGoForward(granularity, anchor) {
  const today = startOfDay(new Date());

  if (granularity === "day") {
    return startOfDay(anchor) < today;
  }
  if (granularity === "week") {
    return weekStartSunday(anchor) < weekStartSunday(today);
  }
  return monthStart(anchor) < monthStart(today);
}

function stepAnchor(granularity, anchor, direction) {
  const d = new Date(anchor);
  if (granularity === "day") {
    d.setDate(d.getDate() + direction);
  } else if (granularity === "week") {
    d.setDate(d.getDate() + direction * 7);
  } else {
    d.setMonth(d.getMonth() + direction);
  }
  return startOfDay(d);
}

function persist() {
  localStorage.setItem(STORAGE_GRANULARITY, state.granularity);
  localStorage.setItem(STORAGE_ANCHOR, formatAnchorDate(state.anchor));
  localStorage.removeItem("phoneLocator.period");
}

function visitsLimit() {
  if (state.granularity === "month") return 500;
  if (state.granularity === "week") return 300;
  return 200;
}

export function getRange() {
  const range = computeRange(state.granularity, state.anchor);
  return {
    ...range,
    granularity: state.granularity,
    anchor: state.anchor,
    label: formatPeriodLabel(state.granularity, state.anchor),
    isToday: state.granularity === "day" && isToday(state.anchor),
    visitsLimit: visitsLimit(),
  };
}

export function getDashboardParams() {
  const range = getRange();
  const params = { from: range.from, to: range.to };
  if (range.isToday) {
    params.include_week_teaser = true;
  }
  return params;
}

function updateBarUi() {
  const labelEl = document.getElementById("period-label-text");
  const dateInput = document.getElementById("period-date");
  const nextBtn = document.getElementById("period-next");

  if (labelEl) labelEl.textContent = formatPeriodLabel(state.granularity, state.anchor);
  if (dateInput) dateInput.value = formatAnchorDate(state.anchor);
  if (nextBtn) nextBtn.disabled = !canGoForward(state.granularity, state.anchor);

  document.querySelectorAll(".period-granularity button").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.granularity === state.granularity);
  });
}

function applyChange() {
  persist();
  updateBarUi();
  onChange();
}

export function initPeriodBar(callback) {
  onChange = callback;

  const prevBtn = document.getElementById("period-prev");
  const nextBtn = document.getElementById("period-next");
  const todayBtn = document.getElementById("period-today");
  const dateInput = document.getElementById("period-date");
  const labelEl = document.getElementById("period-label");

  prevBtn?.addEventListener("click", () => {
    state.anchor = stepAnchor(state.granularity, state.anchor, -1);
    applyChange();
  });

  nextBtn?.addEventListener("click", () => {
    if (!canGoForward(state.granularity, state.anchor)) return;
    state.anchor = stepAnchor(state.granularity, state.anchor, 1);
    applyChange();
  });

  todayBtn?.addEventListener("click", () => {
    state.anchor = startOfDay(new Date());
    applyChange();
  });

  dateInput?.addEventListener("change", () => {
    if (!dateInput.value) return;
    state.anchor = parseAnchor(dateInput.value);
    applyChange();
  });

  labelEl?.addEventListener("click", () => {
    dateInput?.showPicker?.();
  });

  document.querySelectorAll(".period-granularity button").forEach((btn) => {
    btn.addEventListener("click", () => {
      const next = btn.dataset.granularity;
      if (!next || next === state.granularity) return;
      state.granularity = next;
      applyChange();
    });
  });

  updateBarUi();
}
