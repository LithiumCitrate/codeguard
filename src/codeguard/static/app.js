'use strict';
/* CodeGuard workbench — 冷库变体。自研实现：主题、分级环、扫描交互。 */

const $ = (id) => document.getElementById(id);
const SVG = 'http://www.w3.org/2000/svg';
const RISK_ORDER = ['S0', 'S1', 'S2', 'S3', 'S4'];
const RISK_ZH = { S0: '通过', S1: '署名', S2: '复核', S3: '高风险', S4: '冲突' };

let token = '', latest = null, busy = false;

/* ------------------------------------------------------------------ utilities */
function toast(message) {
  const status = $('status');
  status.textContent = message;
  status.style.display = 'block';
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { status.style.display = 'none'; }, 6500);
}
function node(tag, text, cls) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (cls) el.className = cls;
  return el;
}
async function api(path, data) {
  const response = await fetch(path, data ? {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CodeGuard-Token': token },
    body: JSON.stringify(data),
  } : {});
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || '服务连接失败');
  return body;
}
const fmt = (value) => Number(value).toLocaleString('zh-CN');
const pct = (value) => `${Math.round(value * 100)}%`;

/* --------------------------------------------------------------------- theme */
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const button = $('themeToggle');
  if (button) button.textContent = theme === 'dark' ? '深色' : '浅色';
}
(function initTheme() {
  const saved = localStorage.getItem('cg-theme');
  const preferred = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  applyTheme(saved || preferred);
})();

/* ---------------------------------------------------------------------- dial */
const DIAL = { cx: 300, cy: 300, r1: 188, r2: 246, start: 120, span: 300, gap: 2 };

function polar(radius, deg) {
  const rad = (deg * Math.PI) / 180;
  return [DIAL.cx + radius * Math.cos(rad), DIAL.cy + radius * Math.sin(rad)];
}
function sectorPath(r1, r2, a0, a1) {
  const [x0, y0] = polar(r2, a0), [x1, y1] = polar(r2, a1);
  const [x2, y2] = polar(r1, a1), [x3, y3] = polar(r1, a0);
  const large = a1 - a0 > 180 ? 1 : 0;
  return `M${x0.toFixed(1)} ${y0.toFixed(1)}A${r2} ${r2} 0 ${large} 1 ${x1.toFixed(1)} ${y1.toFixed(1)}` +
         `L${x2.toFixed(1)} ${y2.toFixed(1)}A${r1} ${r1} 0 ${large} 0 ${x3.toFixed(1)} ${y3.toFixed(1)}Z`;
}
function svgNode(tag, attrs = {}, text) {
  const el = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, String(value));
  if (text !== undefined) el.textContent = text;
  return el;
}

const dialParts = { sectors: {}, big: null, sub: null, gauges: [], svg: null };

function buildDial() {
  const svg = $('dial');
  const step = (DIAL.span - DIAL.gap * 5) / 5;
  svg.replaceChildren();
  for (let i = 0; i < 5; i += 1) {
    const a0 = DIAL.start + i * (step + DIAL.gap) + DIAL.gap / 2;
    const a1 = a0 + step;
    const path = svgNode('path', { class: 'sector', d: sectorPath(DIAL.r1, DIAL.r2, a0, a1) });
    const [lx, ly] = polar((DIAL.r1 + DIAL.r2) / 2, (a0 + a1) / 2);
    const code = svgNode('text', { class: 'sector-label', x: lx.toFixed(1), y: (ly + 4).toFixed(1), 'text-anchor': 'middle' }, RISK_ORDER[i]);
    const [sx, sy] = polar(DIAL.r2 + 18, (a0 + a1) / 2);
    const sub = svgNode('text', { class: 'sector-sub', x: sx.toFixed(1), y: (sy + 4).toFixed(1), 'text-anchor': 'middle' }, RISK_ZH[RISK_ORDER[i]]);
    dialParts.sectors[RISK_ORDER[i]] = { path, code, sub };
    svg.append(path, code, sub);
  }
  svg.append(svgNode('circle', { class: 'hub-disc', cx: DIAL.cx, cy: DIAL.cy, r: 178 }));
  svg.append(svgNode('path', { class: 'core-tag', d: 'M236 244 H364 L372 252 V266 H236 Z' }));
  svg.append(svgNode('text', { class: 'core-tag-label', x: DIAL.cx, y: 259, 'text-anchor': 'middle' }, 'LAST SCAN'));
  dialParts.big = svgNode('text', { class: 'core-big', x: DIAL.cx, y: 330, 'text-anchor': 'middle' }, '—');
  dialParts.sub = svgNode('text', { class: 'core-sub', x: DIAL.cx, y: 358, 'text-anchor': 'middle' }, '等待审查');
  svg.append(dialParts.big, dialParts.sub);
  ['命中片段', '最高覆盖', '最长逐字'].forEach((label, index) => {
    const y = 390 + index * 26;
    const track = svgNode('rect', { class: 'gauge-track', x: 208, y: y - 5, width: 128, height: 5 });
    const arc = svgNode('rect', { class: 'gauge-arc', x: 208, y: y - 5, width: 0, height: 5 });
    const name = svgNode('text', { class: 'gauge-label', x: 196, y: y, 'text-anchor': 'end' }, label);
    const value = svgNode('text', { class: 'gauge-label', x: 348, y: y, 'text-anchor': 'start' }, '—');
    dialParts.gauges.push({ arc, value });
    svg.append(track, arc, name, value);
  });
  dialParts.svg = svg;
}

function setDial({ risk = '', confidence = null, spans = null, coverage = null, verbatim = null, label = '等待审查' } = {}) {
  if (!dialParts.big) return;
  for (const code of RISK_ORDER) {
    const part = dialParts.sectors[code];
    const on = code === risk;
    part.path.classList.toggle('on', on);
    part.code.classList.toggle('on', on);
    part.sub.classList.toggle('on', on);
  }
  dialParts.big.textContent = risk || '—';
  dialParts.sub.textContent = risk ? `${RISK_ZH[risk] || ''} · 置信度 ${pct(confidence)}` : label;
  const apply = (gauge, share, text) => {
    gauge.arc.setAttribute('width', share === null ? 0 : Math.max(2, 128 * Math.min(1, share)).toFixed(1));
    gauge.value.textContent = text;
    gauge.value.classList.toggle('alert', share !== null && share >= 0.85);
  };
  apply(dialParts.gauges[0], spans, spans === null ? '—' : `${spans.hit}/${spans.total}`);
  apply(dialParts.gauges[1], coverage, coverage === null ? '—' : pct(coverage));
  apply(dialParts.gauges[2], verbatim === null ? null : Math.min(1, verbatim / 48), verbatim === null ? '—' : `${verbatim} token`);
  dialParts.svg.setAttribute('aria-label', risk ? `风险分级环：本次最高 ${risk}（${RISK_ZH[risk]}）` : '风险分级环：尚未审查');
}

/* ------------------------------------------------------------------ evidence */
function list(parent, title, items) {
  if (!items || !items.length) return;
  parent.append(node('b', title));
  const ul = node('ul');
  items.forEach((item) => ul.append(node('li', item)));
  parent.append(ul);
}

function render(data) {
  $('empty').hidden = true;
  $('result').hidden = false;
  $('exports').hidden = false;
  $('resultBadge').className = 'state' + (data.blocking ? ' is-alert' : '');
  $('resultBadge').textContent = data.blocking ? '建议阻断 / 待处置'
    : (data.findings.length ? '发现来源，待核查' : '审查完成');
  const root = $('result');
  root.replaceChildren();

  const top = [...data.findings].sort((a, b) => RISK_ORDER.indexOf(b.risk) - RISK_ORDER.indexOf(a.risk))[0];
  const decision = node('div', undefined, 'decision' + (data.blocking ? ' block' : ''));
  decision.append(node('h3', data.blocking ? '检测到需要阻断的许可风险'
    : data.findings.length ? '发现来源，请核查许可义务' : '当前语料内未发现足够的来源证据'));
  decision.append(node('p', `${data.findings.length} 个候选来源 │ ${data.scan.matched_spans}/${data.scan.total_spans} 片段命中 │ 最高 ${top ? top.risk + ' ' + top.risk_label : '无命中'}`));
  root.append(decision);

  data.findings.forEach((finding, index) => {
    const card = node('article', undefined, 'finding');
    const head = node('div', undefined, 'finding-head');
    const name = node('b');
    name.append(node('span', `No.${String(index + 1).padStart(2, '0')} `), document.createTextNode(`${finding.package} @ ${finding.version}`));
    head.append(name, node('span', `${finding.risk} · ${RISK_ZH[finding.risk] || finding.risk_label}`, `risk ${finding.risk}`));
    card.append(head, node('div', finding.path, 'source-path'));
    card.append(node('div', `${finding.license_spdx} │ 证据评分 ${(finding.confidence * 100).toFixed(1)}% │ 覆盖 ${(finding.coverage * 100).toFixed(1)}% │ 最长逐字 ${finding.max_verbatim_run} token`, 'evidence-stats'));
    const explanation = node('details');
    explanation.append(node('summary', '判定说明与处置建议'), node('p', finding.explanation));
    card.append(explanation);
    list(card, '待满足的许可义务', finding.verdict && finding.verdict.obligations);
    list(card, '冲突', finding.verdict && finding.verdict.conflicts);
    if (finding.snippets && finding.snippets.length) {
      const details = node('details');
      details.append(node('summary', '命中行号与原文对照'));
      finding.snippets.forEach((snippet) => {
        const row = node('div', undefined, 'compare');
        [['待审查代码 · 第 ' + snippet.query_start + ' 行起', snippet.query],
         ['来源原文 · 第 ' + snippet.source_start + ' 行起', snippet.source]].forEach(([label, code]) => {
          const col = node('div');
          col.append(node('small', label), node('pre', code));
          row.append(col);
        });
        details.append(row);
      });
      card.append(details);
    }
    root.append(card);
  });

  const scan = data.scan;
  $('scanSpans').textContent = `${scan.matched_spans}/${scan.total_spans}`;
  $('scanProbe').textContent = `${scan.timings.probe_ms !== undefined ? scan.timings.probe_ms : '—'} ms`;
  $('scanVerify').textContent = `${scan.timings.verify_ms !== undefined ? scan.timings.verify_ms : '—'} ms`;
  $('scanRisk').textContent = top ? `${top.risk} · ${RISK_ZH[top.risk]}` : '无命中';
  $('scanRisk').title = top ? top.risk_label : '';
  const issued = data.receipt && data.receipt.metadata && data.receipt.metadata.generated_at;
  const issuedLocal = issued ? new Date(issued).toLocaleString('zh-CN', { hour12: false }) : '';
  $('exportNote').textContent = issued
    ? `签发 ${issuedLocal} │ 导出内容与页面证据一致，不写回语料。`
    : '导出内容与页面证据一致，不写回语料。';
  setDial({
    risk: top ? top.risk : 'S0',
    confidence: top ? top.confidence : 1,
    spans: { hit: scan.matched_spans, total: scan.total_spans },
    coverage: top ? top.coverage : 0,
    verbatim: top ? top.max_verbatim_run : 0,
  });
  $('scan').classList.add('done');
  setTimeout(() => $('scan').classList.remove('done'), 420);
}

function invalidate() {
  latest = null;
  $('exports').hidden = true;
  $('result').hidden = true;
  $('empty').hidden = false;
  $('resultBadge').className = 'state';
  $('resultBadge').textContent = '输入已更新';
  ['scanSpans', 'scanProbe', 'scanVerify', 'scanRisk'].forEach((id) => { $(id).textContent = '—'; });
  $('exportNote').textContent = '审查完成后可导出证书、物料清单与离线报告；导出内容与页面证据一致，不写回语料。';
  setDial();
}

function count() {
  $('codeCount').textContent = $('code').value.length.toLocaleString('zh-CN') + ' 字符';
}

function setBusy(value) {
  busy = value;
  document.querySelectorAll('[data-demo],#scan,#file,#name,#code,#targetLicense,#usage').forEach((el) => { el.disabled = value; });
  $('scan').textContent = value ? '正在检索和验证来源…' : '开始来源审查';
}

/* ---------------------------------------------------------------------- wiring */
function showTab(name, push = true) {
  const target = document.getElementById(name) ? name : 'review';
  document.querySelectorAll('.tab').forEach((el) => { el.hidden = el.id !== target; });
  document.querySelectorAll('.cmdbar nav button').forEach((el) => {
    const here = el.dataset.tab === target;
    el.classList.toggle('here', here);
    if (here) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current');
  });
  if (push && location.hash !== '#' + target) history.pushState(null, '', '#' + target);
}
document.querySelectorAll('[data-tab]').forEach((button) => button.addEventListener('click', () => {
  showTab(button.dataset.tab);
  window.scrollTo({ top: 0 });
}));
window.addEventListener('popstate', () => showTab((location.hash || '#review').slice(1), false));
showTab((location.hash || '#review').slice(1), false);

$('themeToggle').addEventListener('click', () => {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  localStorage.setItem('cg-theme', next);
});

document.querySelectorAll('[data-demo]').forEach((button) => button.addEventListener('click', async () => {
  try {
    const data = await api('/api/demo/' + button.dataset.demo);
    $('code').value = data.code;
    $('name').value = data.name;
    $('demoNote').textContent = data.note;
    count();
    invalidate();
  } catch (error) { toast(error.message); }
}));

$('code').addEventListener('input', () => { count(); invalidate(); });
['name', 'targetLicense', 'usage'].forEach((id) => $(id).addEventListener('change', invalidate));

$('file').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  if (file.size > 200000) { toast('文件超过 200 KB，请拆分后导入'); return; }
  $('code').value = await file.text();
  $('name').value = file.name;
  $('demoNote').textContent = '已导入本地文件：' + file.name;
  count();
  invalidate();
});

$('scan').addEventListener('click', async () => {
  if (busy) return;
  if (!$('code').value.trim()) { toast('请先输入代码或选择体验案例'); return; }
  setBusy(true);
  latest = null;
  $('exports').hidden = true;
  $('result').hidden = true;
  $('empty').hidden = false;
  $('resultBadge').className = 'state';
  $('resultBadge').textContent = '正在分析';
  try {
    const data = await api('/api/scan', { code: $('code').value, name: $('name').value, license: $('targetLicense').value, usage: $('usage').value });
    latest = data;
    render(data);
  } catch (error) {
    $('resultBadge').textContent = '分析未完成';
    toast(error.message);
  } finally {
    setBusy(false);
  }
});

document.querySelectorAll('[data-export]').forEach((button) => button.addEventListener('click', () => {
  if (!latest) return;
  const kind = button.dataset.export;
  const body = kind === 'html' ? latest.html : JSON.stringify(latest[kind], null, 2);
  const blob = new Blob([body], { type: kind === 'html' ? 'text/html;charset=utf-8' : 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = node('a');
  link.href = url;
  link.download = 'codeguard-' + kind + (kind === 'html' ? '.html' : '.json');
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}));

$('reason').addEventListener('click', async () => {
  const button = $('reason');
  button.disabled = true;
  try {
    const data = await api('/api/licenses', { source: $('sourceLicense').value, target: $('destinationLicense').value, usage: $('licenseUsage').value });
    const root = $('licenseResult');
    root.replaceChildren(node('h3', ({ compatible: '兼容', conditional: '有条件兼容', incompatible: '存在冲突', unknown: '授权未知' })[data.status] || data.status));
    list(root, '许可义务', data.obligations);
    list(root, '冲突', data.conflicts);
    list(root, '说明', data.notes);
  } catch (error) { toast(error.message); } finally { button.disabled = false; }
});

buildDial();
setDial();

api('/api/health').then((data) => {
  token = data.token;
  const stats = data.stats;
  $('docs').textContent = fmt(stats.documents);
  $('chunks').textContent = fmt(stats.chunks);
  $('packages').textContent = fmt(stats.packages);
  $('model').textContent = data.model;
  $('corpusFiles').textContent = fmt(stats.documents);
  $('corpusChunks').textContent = fmt(stats.chunks);
  $('corpusPackages').textContent = fmt(stats.packages);
  $('corpusReadable').textContent = `${fmt(data.corpus.readable)}/${fmt(data.corpus.total)}`;
  $('engineModel').textContent = data.model.replace('（未加载模型）', '');
  $('engineLayers').textContent = (stats.params.active_layers || []).join(' · ');
  $('engineIndex').textContent = 'v' + stats.index_version;
  $('engineLicences').textContent = (stats.licenses || []).length + ' 种';
  const ready = data.ready;
  $('connection').textContent = ready ? '● 本机引擎就绪' : '● 语料缺失';
  $('connection').style.color = ready ? 'var(--signal)' : 'var(--cmd-text)';
  if (!ready) { $('scan').disabled = true; toast('语料不完整，扫描已禁用；请重新建立语料。'); }
}).catch((error) => {
  $('connection').textContent = '● 本机引擎未连接';
  $('connection').style.color = 'var(--cmd-text)';
  $('scan').disabled = true;
  toast(error.message);
});
