/* Northbeam Support Copilot — local UI.
   Vanilla JS, no build step. Everything renders through helpers that use
   textContent, never innerHTML with model output, so an answer containing
   markup can't inject anything into the page. */

const $ = (id) => document.getElementById(id);

const api = async (path, options) => {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
  if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
  return body;
};

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
};

/* ------------------------------------------------------------------- theme */

const THEME_KEY = 'northbeam-theme';
const setTheme = (theme) => {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem(THEME_KEY, theme); } catch {}
};

setTheme(
  (() => { try { return localStorage.getItem(THEME_KEY); } catch { return null; } })() ||
  (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark')
);

$('themeToggle').onclick = () =>
  setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');

/* -------------------------------------------------------------------- tabs */

document.querySelectorAll('.tab').forEach((tab) => {
  tab.onclick = () => {
    document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('is-active', t === tab));
    document.querySelectorAll('.view').forEach((view) =>
      view.classList.toggle('is-active', view.id === `view-${tab.dataset.view}`));
    if (tab.dataset.view === 'dashboard') loadKpis();
  };
});

/* ---------------------------------------------------------------- composer */

const questionEl = $('question');
const askBtn = $('askBtn');

const autoGrow = () => {
  questionEl.style.height = 'auto';
  questionEl.style.height = `${questionEl.scrollHeight}px`;
};

questionEl.addEventListener('input', autoGrow);
questionEl.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
    event.preventDefault();
    ask();
  }
});
askBtn.onclick = () => ask();

/* ---------------------------------------------------------------- examples */

async function loadExamples() {
  let data;
  try { data = await api('/api/examples'); } catch { return; }

  const wrap = $('examples');
  wrap.replaceChildren();

  data.groups.forEach((group) => {
    const section = el('div');
    const head = el('div', 'ex-head');
    head.append(el('h4', null, group.group), el('span', 'ex-hint', group.hint));

    const chips = el('div', 'chips');
    group.questions.forEach((question) => {
      const chip = el('button', 'chip', question);
      chip.title = question;
      chip.onclick = () => { questionEl.value = question; autoGrow(); ask(); };
      chips.append(chip);
    });

    section.append(head, chips);
    wrap.append(section);
  });
}

async function loadConfig() {
  try {
    const config = await api('/api/config');
    $('configLine').textContent =
      `${config.model} · ${config.n_tools} tools · max ${config.max_steps} steps · ` +
      `clock frozen at ${config.today}`;
  } catch {
    $('configLine').textContent = 'radar service desk';
  }
}

/* --------------------------------------------------------------- ask flow */

// The tool loop takes a few seconds and a frozen spinner reads as hung.
const STAGES = [
  'Choosing tools…',
  'Reading records…',
  'Computing across the fleet…',
  'Checking the policy documents…',
  'Composing the answer…',
];

let inFlight = false;
let stageTimer = null;

function setBusy(busy) {
  inFlight = busy;
  askBtn.disabled = busy;
  askBtn.classList.toggle('is-busy', busy);
  $('loadingState').hidden = !busy;

  if (busy) {
    $('emptyState').hidden = true;
    $('errorState').hidden = true;
    $('result').hidden = true;
    let i = 0;
    $('loadingText').textContent = STAGES[0];
    stageTimer = setInterval(() => {
      i = Math.min(i + 1, STAGES.length - 1);
      $('loadingText').textContent = STAGES[i];
    }, 2200);
  } else {
    clearInterval(stageTimer);
  }
}

async function ask() {
  const question = questionEl.value.trim();
  if (!question || inFlight) return;

  setBusy(true);
  try {
    render(await api('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    }));
  } catch (err) {
    $('errorText').textContent = err.message;
    $('errorState').hidden = false;
  } finally {
    setBusy(false);
  }
}

/* ----------------------------------------------------------------- render */

// Record ids and figures are picked out of the prose so the eye lands on the
// concrete parts of the answer.
const ID_OR_NUMBER =
  /\b((?:OP|RU|CS|TKT|EV)-\d{2,6})\b|(\$[\d,]+(?:\.\d+)?|\b\d+(?:,\d{3})*(?:\.\d+)?%)/g;

function renderProse(container, text) {
  container.replaceChildren();
  (text || '').split(/\n{2,}/).forEach((paragraph) => {
    if (!paragraph.trim()) return;
    const p = el('p');
    let last = 0;
    for (const match of paragraph.matchAll(ID_OR_NUMBER)) {
      if (match.index > last) p.append(document.createTextNode(paragraph.slice(last, match.index)));
      p.append(el('span', match[1] ? 'rid' : 'num', match[0]));
      last = match.index + match[0].length;
    }
    p.append(document.createTextNode(paragraph.slice(last)));
    container.append(p);
  });
}

const RULE_LABEL = {
  protected_value: 'rule: protected value',
  state_change_action: 'rule: state-changing action',
  missing_record_is_an_answer: 'rule: missing record is an answer',
  model_judgment: 'model judgment',
};

function render(data) {
  const result = $('result');
  const meta = data.meta || {};

  result.classList.toggle('is-declined', data.declined);
  $('verdictLabel').textContent = data.declined ? 'Declined' : 'Answered';

  // The headline of this UI: rule or model?
  const decider = $('decider');
  decider.className = 'decider ' + (meta.decision_source === 'code' ? 'by-code' : 'by-model');
  decider.textContent = RULE_LABEL[meta.decision_rule] || meta.decision_rule || 'model judgment';

  const metrics = $('metrics');
  metrics.replaceChildren();
  const addMetric = (label, value) => {
    const metric = el('div', 'metric');
    metric.append(el('b', null, value), document.createTextNode(label));
    metrics.append(metric);
  };
  if (meta.cached) addMetric('cached', '⚡');
  addMetric('ms', String(Math.round(meta.total_ms ?? meta.wall_ms ?? 0)));
  addMetric('steps', String(meta.steps ?? 0));
  addMetric('tools', String(data.tool_calls.length));
  if (meta.prompt_tokens || meta.completion_tokens) {
    addMetric('tokens', String((meta.prompt_tokens || 0) + (meta.completion_tokens || 0)));
  }

  renderProse($('answer'), data.text);

  const showDecline = data.declined && data.decline_reason;
  $('declineNote').hidden = !showDecline;
  if (showDecline) $('declineReason').textContent = data.decline_reason;

  // Sources, typed by shape — the split is derived in Python, not guessed here.
  const sources = $('sources');
  sources.replaceChildren();
  (data.policy_sources || []).forEach((s) => sources.append(el('span', 'src policy', s)));
  (data.record_sources || []).forEach((s) => sources.append(el('span', 'src record', s)));
  (data.unrecognised_sources || []).forEach((s) => sources.append(el('span', 'src unknown', s)));
  $('sourcesPanel').hidden = !(data.sources || []).length;

  const bad = data.unrecognised_sources || [];
  $('badSources').hidden = bad.length === 0;
  if (bad.length) {
    $('badSources').className = 'panel-note warn';
    $('badSources').textContent =
      `${bad.length} citation${bad.length > 1 ? 's' : ''} matched no known document or record id.`;
  }

  // Tool timeline.
  const timeline = $('timeline');
  timeline.replaceChildren();
  $('toolCount').textContent = data.tool_calls.length;
  $('noTools').hidden = data.tool_calls.length > 0;

  data.tool_calls.forEach((call, i) => {
    const item = el('li',
      'step' + (call.computed ? ' is-computed' : '') + (call.ok ? '' : ' is-failed'));

    const head = el('button', 'step-head');
    head.append(el('span', 'step-n', String(i + 1)), el('span', 'step-name', call.name));
    if (call.computed) head.append(el('span', 'tag', 'computed in Python'));
    if (!call.ok) head.append(el('span', 'tag err', 'no result'));
    head.append(el('span', 'step-caret', '›'));
    head.onclick = () => item.classList.toggle('is-open');

    const body = el('div', 'step-body');
    body.append(el('pre', null, JSON.stringify(call.args, null, 2)));

    item.append(head, body);
    timeline.append(item);
  });

  result.hidden = false;
  result.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/* -------------------------------------------------------------- dashboard */

// [label, key, format, thresholds, note]
// thresholds are [greenAtOrBelow, amberAtOrBelow]; null leaves the tile neutral.
const KPI_SPEC = [
  ['Calls traced',        'n_calls',              (v) => String(v),     null,     ''],
  ['Latency p50',         'latency_p50_ms',       (v) => `${v}ms`,      null,     'typical'],
  ['Latency p95',         'latency_p95_ms',       (v) => `${v}ms`,      null,     'the tail'],
  ['Tool calls / answer', 'mean_tool_calls',      (v) => v.toFixed(1),  null,     ''],
  ['Step limit hit',      'step_limit_rate_pct',  (v) => `${v}%`,       [0, 10],  'ran out of steps'],
  ['No tool call',        'no_tool_rate_pct',     (v) => `${v}%`,       [0, 10],  'ungrounded'],
  ['Tool errors',         'tool_error_rate_pct',  (v) => `${v}%`,       [0, 5],   'bad ids or args'],
  ['Uncited answers',     'uncited_rate_pct',     (v) => `${v}%`,       [10, 30], ''],
  ['Bad citations',       'bad_citation_rate_pct',(v) => `${v}%`,       [0, 5],   'no valid id shape'],
  ['Decline rate',        'decline_rate_pct',     (v) => `${v}%`,       null,     ''],
  ['Declines in code',    'declines_in_code_pct', (v) => `${v}%`,       null,     'vs model judgment'],
  ['Errors',              'error_rate_pct',       (v) => `${v}%`,       [0, 2],   ''],
  ['Tokens / answer',     'mean_tokens',          (v) => Math.round(v), null,     'cost proxy'],
];

function kpiClass(value, thresholds) {
  if (!thresholds) return '';
  const [good, warn] = thresholds;
  if (value <= good) return 'good';
  if (value <= warn) return 'warn';
  return 'bad';
}

function renderBars(container, entries, isModel) {
  container.replaceChildren();
  const max = Math.max(1, ...entries.map(([, n]) => n));
  entries.forEach(([name, n]) => {
    const row = el('div', 'bar-row');
    const track = el('div', 'bar-track');
    const fill = el('div', 'bar-fill' + (isModel && isModel(name) ? ' model' : ''));
    fill.style.width = `${(n / max) * 100}%`;
    track.append(fill);
    row.append(el('div', 'bar-name', name), track, el('div', 'bar-value', String(n)));
    container.append(row);
  });
}

async function loadKpis() {
  let data;
  try { data = await api('/api/kpis'); } catch { return; }

  const has = data.kpis && Object.keys(data.kpis).length;
  $('dashEmpty').hidden = !!has;
  $('dashBody').hidden = !has;
  if (!has) return;

  const grid = $('kpiGrid');
  grid.replaceChildren();
  KPI_SPEC.forEach(([label, key, format, thresholds, note]) => {
    const value = data.kpis[key];
    if (value == null) return;
    const card = el('div', `kpi ${kpiClass(value, thresholds)}`);
    card.append(el('div', 'kpi-label', label), el('div', 'kpi-value', String(format(value))));
    if (note) card.append(el('div', 'kpi-note', note));
    grid.append(card);
  });

  renderBars($('toolBars'), Object.entries(data.tools || {}));
  renderBars($('ruleBars'), Object.entries(data.rules || {}),
             (name) => name === 'model_judgment');

  const rows = $('traceRows');
  rows.replaceChildren();
  (data.recent || []).forEach((trace) => {
    const row = el('tr');
    const question = el('td', null, trace.question);
    question.title = trace.question;

    let tone = 'ok';
    let label = 'answered';
    if (trace.error) { tone = 'err'; label = 'error'; }
    else if (trace.declined) { tone = 'declined'; label = `declined · ${trace.decision_source || '?'}`; }
    else if (trace.cached) { tone = 'cached'; label = 'cached'; }

    const outcome = el('td');
    outcome.append(el('span', `pill ${tone}`, label));

    row.append(question,
               el('td', null, `${trace.total_ms}ms`),
               el('td', null, String(trace.steps)),
               el('td', null, String(trace.n_tools)),
               outcome);
    rows.append(row);
  });
}

$('refreshKpis').onclick = loadKpis;

/* ------------------------------------------------------------------- boot */

loadConfig();
loadExamples();
