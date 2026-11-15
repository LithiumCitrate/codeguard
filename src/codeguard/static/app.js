'use strict';
/* CodeGuard workbench — flat tactical console. Theme, risk dial and scan wiring. */

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
  if (button) {
    button.textContent = theme === 'dark' ? 'DAY' : 'NIGHT';
    button.setAttribute('aria-label', theme === 'dark' ? '切换到浅色主题' : '切换到深色主题');
  }
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

const dialParts = { sectors: {}, eyebrow: null, big: null, sub: null, idle: null, marker: null, svg: null };

function buildDial() {
  const svg = $('dial');
  const step = (DIAL.span - DIAL.gap * 5) / 5;
  svg.replaceChildren();
  for (let i = 0; i < 5; i += 1) {
    const a0 = DIAL.start + i * (step + DIAL.gap) + DIAL.gap / 2;
    const a1 = a0 + step;
    const mid = (a0 + a1) / 2;
    const path = svgNode('path', { class: `sector sec-${RISK_ORDER[i]}`, d: sectorPath(DIAL.r1, DIAL.r2, a0, a1) });
    const [lx, ly] = polar((DIAL.r1 + DIAL.r2) / 2 + 10, mid);
    const code = svgNode('text', { class: 'sector-label', x: lx.toFixed(1), y: (ly + 4).toFixed(1), 'text-anchor': 'middle' }, RISK_ORDER[i]);
    const [sx, sy] = polar((DIAL.r1 + DIAL.r2) / 2 - 10, mid);
    const sub = svgNode('text', { class: 'sector-sub', x: sx.toFixed(1), y: (sy + 3).toFixed(1), 'text-anchor': 'middle' }, RISK_ZH[RISK_ORDER[i]]);
    dialParts.sectors[RISK_ORDER[i]] = { path, code, sub };
    svg.append(path, code, sub);
  }
  svg.append(svgNode('circle', { class: 'ring outer', cx: DIAL.cx, cy: DIAL.cy, r: 282 }));
  const ticks = svgNode('g', { class: 'ticks' });
  for (let i = 0; i < 60; i += 1) {
    const angle = i * 6;
    const major = i % 5 === 0;
    const [x1, y1] = polar(256, angle);
    const [x2, y2] = polar(major ? 276 : 266, angle);
    ticks.append(svgNode('line', {
      class: `tick${major ? ' major' : ''}`,
      x1: x1.toFixed(1), y1: y1.toFixed(1), x2: x2.toFixed(1), y2: y2.toFixed(1),
    }));
  }
  svg.append(ticks);
  dialParts.marker = svgNode('path', { class: 'marker', d: 'M300 4l8 13h-16z', display: 'none' });
  svg.append(dialParts.marker);
  svg.append(svgNode('circle', { class: 'hub-disc', cx: DIAL.cx, cy: DIAL.cy, r: 178 }));
  svg.append(svgNode('line', { class: 'core-tick', x1: 218, y1: 242, x2: 246, y2: 242 }),
             svgNode('line', { class: 'core-tick', x1: 354, y1: 242, x2: 382, y2: 242 }));
  dialParts.eyebrow = svgNode('text', { class: 'core-eyebrow', x: DIAL.cx, y: 246, 'text-anchor': 'middle' }, 'LAST SCAN');
  dialParts.big = svgNode('text', { class: 'core-big', x: DIAL.cx, y: 348, 'text-anchor': 'middle' }, '');
  dialParts.sub = svgNode('text', { class: 'core-sub', x: DIAL.cx, y: 384, 'text-anchor': 'middle' }, '');
  const idleCode = svgNode('text', { class: 'core-idle', x: DIAL.cx, y: 292, 'text-anchor': 'middle' }, 'CODE');
  const idleGuard = svgNode('text', { class: 'core-idle', x: DIAL.cx, y: 356, 'text-anchor': 'middle' }, 'GUARD');
  dialParts.idle = svgNode('g', { class: 'core-idle-group' });
  dialParts.idle.append(idleCode, idleGuard);
  svg.append(dialParts.eyebrow, dialParts.big, dialParts.sub, dialParts.idle);
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
  const active = Boolean(risk);
  dialParts.idle.setAttribute('display', active ? 'none' : 'inline');
  if (dialParts.marker) {
    if (active) {
      const step = (DIAL.span - DIAL.gap * 5) / 5;
      const index = RISK_ORDER.indexOf(risk);
      const start = DIAL.start + index * (step + DIAL.gap) + DIAL.gap / 2;
      dialParts.marker.setAttribute('transform', `rotate(${start + step / 2 + 90} ${DIAL.cx} ${DIAL.cy})`);
      dialParts.marker.setAttribute('display', 'inline');
    } else {
      dialParts.marker.setAttribute('display', 'none');
    }
  }
  dialParts.big.textContent = active ? risk : '';
  dialParts.sub.textContent = active
    ? (confidence === null ? (RISK_ZH[risk] || '') : `${RISK_ZH[risk] || ''} · 置信度 ${pct(confidence)}`)
    : label;
  RISK_ORDER.forEach((code) => dialParts.big.classList.toggle(`r-${code}`, active && code === risk));
  dialParts.svg.setAttribute('aria-label', active ? `风险分级环：本次最高 ${risk}（${RISK_ZH[risk]}）` : '风险分级环：尚未审查');
  const cells = { spans: $('statSpans'), coverage: $('statCoverage'), verbatim: $('statVerbatim') };
  cells.spans.textContent = spans === null ? '—' : `${spans.hit}/${spans.total}`;
  cells.coverage.textContent = coverage === null ? '—' : pct(coverage);
  cells.verbatim.textContent = verbatim === null ? '—' : `${verbatim} token`;
  cells.spans.classList.toggle('hot', spans !== null && spans.total > 0 && spans.hit === spans.total);
  cells.coverage.classList.toggle('hot', coverage !== null && coverage >= 0.85);
  cells.verbatim.classList.toggle('hot', verbatim !== null && verbatim >= 40);
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
    if (llm.configured && llm.tavily) {
      const deep = node('button', '联网深挖', 'btn small cyan deep-btn');
      deep.type = 'button';
      deep.title = '调用大模型联网检索公开资料，佐证该命中的来源与许可证背景（不改变风险结论）';
      deep.addEventListener('click', async () => {
        if (busy) return;
        deep.disabled = true;
        deep.textContent = '深挖中…';
        try {
          const data = await api('/api/assist', { action: 'deep', index });
          renderAiCard('deep', Object.assign({ note: '对象：' + finding.package + '@' + finding.version + ' · ' + finding.path }, data));
        } catch (error) { toast(error.message); } finally {
          deep.disabled = false;
          deep.textContent = '联网深挖';
        }
      });
      card.append(deep);
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
  $('assistSummary').disabled = false;
  $('askForm').hidden = false;
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
  $('aiCards').hidden = true;
  $('aiCards').replaceChildren();
  $('askForm').hidden = true;
  $('assistSummary').disabled = true;
  setDial();
}

function count() {
  $('codeCount').textContent = $('code').value.length.toLocaleString('zh-CN') + ' 字符';
}

function setBusy(value) {
  busy = value;
  document.querySelectorAll('#scan,#file,#folder,#treeRoot,#name,#code,#targetLicense,#usage,#assistScan,#aiInterpret,#webProbe,#assistSummary,#askInput').forEach((el) => { el.disabled = value || (el.id === 'assistSummary' && !latest); });
  const scan = $('scan');
  const label = scan.querySelector('span');
  const ai = $('aiInterpret').checked || $('webProbe').checked || $('assistScan').checked;
  if (label) label.textContent = value ? (ai ? '正在检索验证＋AI 增强…' : '正在检索和验证来源…') : '开始来源审查';
  scan.classList.toggle('is-busy', value);
}

/* ---------------------------------------------------------------------- wiring */
function showTab(name, push = true) {
  const target = document.getElementById(name) ? name : 'home';
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
document.querySelectorAll('.feat[data-tab]').forEach((card) => card.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  event.preventDefault();
  showTab(card.dataset.tab);
  window.scrollTo({ top: 0 });
}));
document.querySelectorAll('[data-scroll]').forEach((button) => button.addEventListener('click', () => {
  const target = document.getElementById(button.dataset.scroll);
  if (target) target.scrollIntoView({ block: 'start' });
}));
window.addEventListener('popstate', () => showTab((location.hash || '#home').slice(1), false));
showTab((location.hash || '#home').slice(1), false);

$('themeToggle').addEventListener('click', () => {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  localStorage.setItem('cg-theme', next);
});

/* 合并入口菜单：选中即收起；点击外部或 Escape 收起 */
document.querySelectorAll('.btn-menu').forEach((menu) => {
  menu.addEventListener('click', (event) => {
    if (event.target.closest('.menu')) menu.open = false;
  });
});
document.addEventListener('click', (event) => {
  document.querySelectorAll('.btn-menu[open]').forEach((menu) => {
    if (!menu.contains(event.target)) menu.open = false;
  });
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    document.querySelectorAll('.btn-menu[open]').forEach((menu) => { menu.open = false; });
  }
});

$('code').addEventListener('input', () => { count(); invalidate(); });
['name', 'targetLicense', 'usage'].forEach((id) => $(id).addEventListener('change', invalidate));

/* ------------------------------------------------------- 文件夹目录树 */
const tree = { files: new Map(), root: '', selected: '', selectedIsFile: false };

const TREE_EXTS = ['.py', '.js', '.ts', '.java', '.c', '.cpp', '.h', '.go', '.rs', '.txt',
  '.mjs', '.jsx', '.tsx', '.cc', '.hpp', '.rb', '.php', '.md'];

$('folder').addEventListener('change', async (event) => {
  const list = [...event.target.files];
  if (!list.length) return;
  tree.files.clear();
  tree.root = list[0].webkitRelativePath.split('/')[0] || 'uploaded';
  let skipped = 0;
  for (const f of list) {
    const rel = (f.webkitRelativePath || f.name).split('/').slice(1).join('/') || f.name;
    const ext = '.' + (f.name.split('.').pop() || '').toLowerCase();
    if (!TREE_EXTS.includes(ext)) { skipped += 1; continue; }
    if (f.size > 200000) { skipped += 1; continue; }
    tree.files.set(rel, f);
  }
  tree.selected = '';
  tree.selectedIsFile = false;
  $('treeBox').hidden = false;
  buildTree();
  $('treeSel').textContent = '整个文件夹 · ' + tree.root;
  $('treeNote').textContent = `已载入 ${tree.files.size} 个可分析文件` +
    (skipped ? `（跳过 ${skipped} 个：类型不支持或超过 200KB）` : '') +
    '。默认分析整个文件夹的风险；点击文件或子文件夹可缩小范围。';
  $('name').value = tree.root;
  count();
  invalidate();
});

function buildTree() {
  const rootEl = $('tree');
  rootEl.replaceChildren();
  const dirSet = new Set();
  const fileByParent = new Map();
  for (const path of tree.files.keys()) {
    const parent = path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '';
    if (!fileByParent.has(parent)) fileByParent.set(parent, []);
    fileByParent.get(parent).push(path);
    const parts = path.split('/');
    for (let i = 1; i < parts.length; i++) dirSet.add(parts.slice(0, i).join('/'));
  }
  const dirByParent = new Map();
  for (const dir of dirSet) {
    const parent = dir.includes('/') ? dir.slice(0, dir.lastIndexOf('/')) : '';
    if (!dirByParent.has(parent)) dirByParent.set(parent, []);
    dirByParent.get(parent).push(dir);
  }
  const build = (parent, container) => {
    for (const dir of (dirByParent.get(parent) || []).sort()) {
      const details = node('details', undefined, 'tree-dir');
      details.dataset.dir = dir;
      const summary = node('summary');
      const label = node('span', dir.split('/').pop(), 't-dir');
      const count = node('span', String((fileByParent.get(dir) || []).length), 't-count');
      summary.append(label, count);
      details.append(summary);
      build(dir, details);
      label.addEventListener('click', () => selectNode(dir, false));
      container.append(details);
    }
    for (const path of (fileByParent.get(parent) || []).sort()) {
      const btn = node('button', path.split('/').pop(), 't-file');
      btn.type = 'button';
      btn.dataset.path = path;
      btn.addEventListener('click', () => selectNode(path, true));
      container.append(btn);
    }
  };
  build('', rootEl);
}

function selectNode(path, isFile) {
  tree.selected = path;
  tree.selectedIsFile = isFile;
  $('treeSel').textContent = isFile ? '文件 · ' + path : '子文件夹 · ' + path;
  document.querySelectorAll('.t-file').forEach((b) => b.classList.toggle('here', isFile && b.dataset.path === path));
  count();
  invalidate();
}

$('treeRoot').addEventListener('click', () => {
  tree.selected = '';
  tree.selectedIsFile = false;
  $('treeSel').textContent = '整个文件夹 · ' + tree.root;
  document.querySelectorAll('.t-file').forEach((b) => b.classList.remove('here'));
  count();
  invalidate();
});

async function filesUnderSelection() {
  const picked = [];
  let skipped = 0;
  for (const [path, f] of tree.files) {
    const inScope = !tree.selected ||
      (tree.selectedIsFile ? path === tree.selected : path.startsWith(tree.selected + '/'));
    if (!inScope) continue;
    if (picked.length >= 400) { skipped += 1; continue; }
    try {
      picked.push({ path, content: await f.text() });
    } catch (error) { skipped += 1; }
  }
  return { picked, skipped };
}

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
  const useTree = tree.files.size > 0;
  const singleFile = useTree && tree.selectedIsFile;
  if (!useTree && !$('code').value.trim()) { toast('请先输入或导入代码'); return; }
  setBusy(true);
  latest = null;
  $('exports').hidden = true;
  $('result').hidden = true;
  $('empty').hidden = false;
  $('resultBadge').className = 'state';
  $('resultBadge').textContent = useTree && !singleFile ? '正在分析文件夹…' : '正在分析';
  try {
    let data;
    if (useTree && !singleFile) {
      const { picked, skipped } = await filesUnderSelection();
      if (!picked.length) { toast('所选范围内没有可分析的文本文件'); return; }
      data = await api('/api/scan_tree', { files: picked,
        license: $('targetLicense').value, usage: $('usage').value });
      renderTree(data, skipped);
    } else {
      if (singleFile) {
        $('code').value = await tree.files.get(tree.selected).text();
        $('name').value = tree.selected;
        count();
      }
      data = await api('/api/scan', { code: $('code').value, name: $('name').value,
        license: $('targetLicense').value, usage: $('usage').value,
        assist: $('assistScan').checked && llm.configured });
      render(data);
      // 勾选的 AI 增强随本次审查一并执行；各自失败只提示，不影响已出的离线结论
      const code = $('code').value, name = $('name').value;
      if ($('aiInterpret').checked) {
        try { await runInterpret(code, name); } catch (error) { toast(error.message); }
      }
      if ($('webProbe').checked) {
        try { await runWebprobe(code, name, $('targetLicense').value, $('usage').value); }
        catch (error) { toast(error.message); }
      }
    }
    latest = data;
  } catch (error) {
    $('resultBadge').textContent = '分析未完成';
    toast(error.message);
  } finally {
    setBusy(false);
  }
});

function riskTag(risk, label) {
  return node('span', `${risk} · ${label || RISK_ZH[risk] || risk}`, `risk ${risk}`);
}

function renderTree(data, skipped) {
  $('empty').hidden = true;
  $('result').hidden = false;
  $('exports').hidden = true;
  const s = data.summary;
  $('resultBadge').className = 'state' + (s.blocked ? ' is-alert' : '');
  $('resultBadge').textContent = s.blocked ? '文件夹内有阻断级风险' : '文件夹分析完成';
  const root = $('result');
  root.replaceChildren();

  const head = node('div', undefined, 'decision' + (s.blocked ? ' block' : ''));
  head.append(node('h3', `整夹分析：${s.files} 个文件，${s.blocked} 个建议阻断`));
  const chips = node('p');
  RISK_ORDER.forEach((code) => {
    const n = s.risk_counts[code] || 0;
    if (n) chips.append(node('span', `${code} ${n}`, `risk ${code}`), document.createTextNode(' '));
  });
  head.append(chips, node('p', `最高风险 ${s.overall_risk}（${s.overall_label}） · ${s.findings_files} 个文件存在命中` +
    (skipped ? ` · ${skipped} 个文件被跳过（超限或读取失败）` : '')));
  root.append(head);

  const table = node('div', undefined, 'tree-table');
  for (const r of data.results) {
    const row = node('details', undefined, 'tree-row');
    const summary = node('summary');
    summary.append(node('span', r.path, 't-path'),
      node('span', `${r.matched_spans}/${r.total_spans} 片段`, 't-spans'),
      riskTag(r.risk, r.risk_label));
    row.append(summary);
    if (r.findings.length) {
      for (const f of r.findings) {
        const line = node('p', `${f.package}@${f.version} · ${f.license_spdx} · 评分 ${(f.confidence * 100).toFixed(1)}% · 覆盖 ${(f.coverage * 100).toFixed(1)}% · 来源 ${f.path}`, 'tree-finding');
        row.append(line);
      }
    } else {
      row.append(node('p', '当前语料内未发现足够的来源证据。', 'tree-finding'));
    }
    table.append(row);
  }
  root.append(table);

  setDial({ risk: s.overall_risk, confidence: null });
  $('scanSpans').textContent = `${s.findings_files}/${s.files}`;
  $('scanProbe').textContent = '—';
  $('scanVerify').textContent = '—';
  $('scanRisk').textContent = `${s.overall_risk} · ${s.overall_label}`;
  $('scanRisk').title = s.overall_label;
  $('scan').classList.add('done');
  setTimeout(() => $('scan').classList.remove('done'), 420);
}

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

/* ------------------------------------------------------------------ AI layer */
const llm = { configured: false, model: '', baseUrl: '', tavily: false, fetched: [] };

function aiCardTitle(kind) {
  return ({ interpret: 'AI 文件解读', summary: 'AI 审查摘要', ask: '追问', deep: '联网深挖', webprobe: '联网溯源', licence: 'AI 许可通俗解释' })[kind] || 'AI 输出';
}

function renderSearchTrace(card, searches) {
  if (!searches || !searches.length) return;
  const trace = node('details', undefined, 'search-trace');
  trace.append(node('summary', `联网检索轨迹 · ${searches.length} 次`));
  searches.forEach((s) => {
    trace.append(node('p', '检索词：' + s.query + (s.error ? '（失败：' + s.error + '）' : ''), 'note'));
    const ul = node('ul');
    (s.results || []).forEach((r) => {
      if (!/^https?:\/\//.test(r.url || '')) return;
      const li = node('li');
      const a = node('a', r.title || r.url);
      a.href = r.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      li.append(a);
      ul.append(li);
    });
    if (ul.childNodes.length) trace.append(ul);
  });
  card.append(trace);
}

function renderAiCard(kind, { model = '', text = '', offline = false, note = '', searches = null }) {
  const wrap = $('aiCards');
  wrap.hidden = false;
  const card = node('article', undefined, 'ai-card k-' + kind);
  const head = node('div', undefined, 'ai-head');
  head.append(node('b', aiCardTitle(kind)),
    node('span', offline ? '确定性输出 · 本机' : 'AI 生成 · ' + (model || '外部模型'), offline ? 'tag' : 'tag ai'));
  card.append(head);
  const body = node('p', text, 'ai-text');
  card.append(body);
  renderSearchTrace(card, searches);
  if (note) card.append(node('p', note, 'note'));
  card.append(node('p', '内容为解读参考，不构成法律意见；风险结论以确定性引擎为准。', 'note'));
  wrap.append(card);
  card.scrollIntoView({ block: 'nearest' });
}

function renderWebprobe(data) {
  const wrap = $('aiCards');
  wrap.hidden = false;
  const card = node('article', undefined, 'ai-card k-webprobe');
  const head = node('div', undefined, 'ai-head');
  head.append(node('b', '联网溯源 · 语料外验证'),
    node('span', 'AI 候选 + 确定性验证 · ' + (data.model || '外部模型'), 'tag ai'));
  card.append(head);
  const findings = data.findings || [];
  const top = [...findings].sort((a, b) => RISK_ORDER.indexOf(b.risk) - RISK_ORDER.indexOf(a.risk))[0];
  const fetchedOk = (data.fetched || []).filter((f) => !f.error).length;
  card.append(node('p', findings.length
    ? `在本地语料之外核验 ${fetchedOk} 个上游原文，命中 ${findings.length} 个来源（最高 ${top.risk}）；片段 ${data.matched_spans}/${data.total_spans}。以下为补充提示，不改变离线审查结论。`
    : `已联网核验 ${fetchedOk} 个候选上游原文，未发现足够来源证据；未命中不代表没有来源。`, 'ai-text'));
  findings.forEach((f) => {
    const block = node('details', undefined, 'webprobe-finding');
    const summary = node('summary');
    summary.append(node('span', `${f.package} @ ${f.version} · ${f.license_spdx} `), riskTag(f.risk));
    block.append(summary);
    block.append(node('div', f.path, 'source-path'));
    block.append(node('div', `证据评分 ${(f.confidence * 100).toFixed(1)}% │ 覆盖 ${(f.coverage * 100).toFixed(1)}% │ 最长逐字 ${f.max_verbatim_run} token`, 'evidence-stats'));
    const prov = f.provenance || {};
    if (prov.url) {
      const line = node('p', undefined, 'webprobe-prov');
      const a = node('a', prov.url);
      a.href = prov.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      line.append(document.createTextNode('上游原文：'), a);
      if (prov.sha256) line.append(document.createTextNode(' │ sha256 ' + prov.sha256.slice(0, 16) + '…'));
      block.append(line);
    }
    if (prov.reason) block.append(node('p', '候选依据：' + prov.reason, 'note'));
    if (prov.license_source === 'web:license-text-verified') {
      const lic = node('p', undefined, 'webprobe-prov');
      lic.append(document.createTextNode('许可证已文本核验：' + (prov.license_spdx_verified || f.license_spdx) + ' '));
      if (prov.license_url) {
        const la = node('a', 'LICENSE 原文');
        la.href = prov.license_url;
        la.target = '_blank';
        la.rel = 'noopener noreferrer';
        lic.append(la);
      }
      block.append(lic);
    } else {
      block.append(node('p', '许可证为模型推断，未经文本核验，请人工确认上游授权。', 'note'));
    }
    list(block, '待满足的许可义务', f.verdict && f.verdict.obligations);
    list(block, '冲突', f.verdict && f.verdict.conflicts);
    card.append(block);
  });
  const failed = (data.fetched || []).filter((f) => f.error);
  if (failed.length) {
    const trace = node('details', undefined, 'search-trace');
    trace.append(node('summary', `拉取失败 · ${failed.length} 个`));
    const ul = node('ul');
    failed.forEach((f) => ul.append(node('li', `${f.url}（${f.error}）`)));
    trace.append(ul);
    card.append(trace);
  }
  renderSearchTrace(card, data.searches);
  (data.notes || []).forEach((n) => card.append(node('p', n, 'note')));
  card.append(node('p', '内容为解读参考，不构成法律意见；风险结论以确定性引擎为准。', 'note'));
  wrap.append(card);
  card.scrollIntoView({ block: 'nearest' });
}

function refreshAiButton() {
  $('aiBtn').textContent = llm.configured ? 'AI · ' + llm.model + (llm.tavily ? ' · WEB' : '') : 'AI 未配置';
  $('aiBtn').title = llm.configured ? '已配置大模型：' + llm.model + (llm.tavily ? '（已启用联网检索）' : '') + '（点击修改）' : '配置大模型（可选）';
  $('aiBtn').classList.toggle('armed', llm.configured);
  $('askWebWrap').hidden = !llm.tavily;
  $('webProbe').disabled = !llm.tavily;
  $('webProbe').title = llm.tavily
    ? '扫描后附语料外联网溯源补充提示，不改变离线结论'
    : '需先在右上角 AI 设置中配置 Tavily API Key';
}

function openAiSetup(prefill = true) {
  const dialog = $('aiSetup');
  $('aiStatus').textContent = llm.configured
    ? '已配置：' + llm.model + '。修改后保存即可切换；留空 API Key 表示沿用已保存的密钥。'
    : '未配置时所有功能仍可离线使用；AI 摘要将退化为确定性文字。';
  $('aiClear').hidden = !llm.configured;
  $('aiSave').disabled = !llm.configured;
  const placeholder = node('option', llm.configured ? llm.model : '先拉取模型列表');
  placeholder.value = llm.configured ? llm.model : '';
  $('aiModel').replaceChildren(placeholder);
  if (prefill && llm.configured) {
    $('aiBase').value = llm.baseUrl || '';
    $('aiKey').value = '';
    $('aiKey').placeholder = '已保存，留空沿用';
  }
  $('aiTavily').value = '';
  $('aiTavily').placeholder = llm.tavily ? '已保存，留空沿用' : 'tvly-…（可选）';
  dialog.showModal();
}

$('aiBtn').addEventListener('click', () => openAiSetup());

$('aiSetup').addEventListener('close', () => {
  localStorage.setItem('cg-ai-setup-seen', '1');
});

$('aiFetch').addEventListener('click', async () => {
  const base = $('aiBase').value.trim();
  const key = $('aiKey').value.trim();
  if (!base || !key) { $('aiStatus').textContent = '请先填写 Base URL 与 API Key，再拉取模型列表。'; return; }
  $('aiStatus').textContent = '正在拉取模型列表…';
  $('aiFetch').disabled = true;
  try {
    const data = await api('/api/llm/models', { base_url: base, api_key: key });
    llm.fetched = data.models;
    const select = $('aiModel');
    select.replaceChildren();
    data.models.forEach((id) => {
      const option = node('option', id);
      option.value = id;
      select.append(option);
    });
    select.disabled = false;
    const preferred = data.models.find((id) => /qwen|max|plus|turbo|pro/i.test(id)) || data.models[0];
    select.value = preferred;
    $('aiSave').disabled = false;
    $('aiStatus').textContent = '拉取到 ' + data.models.length + ' 个模型，已预选 ' + preferred + '；可手动更换后保存。';
  } catch (error) {
    $('aiStatus').textContent = error.message;
  } finally {
    $('aiFetch').disabled = false;
  }
});

$('aiSave').addEventListener('click', async () => {
  const model = $('aiModel').value;
  if (!model) { $('aiStatus').textContent = '请先拉取并选择模型。'; return; }
  const payload = { base_url: $('aiBase').value.trim(), model };
  if ($('aiKey').value.trim()) payload.api_key = $('aiKey').value.trim();
  if ($('aiTavily').value.trim()) payload.tavily_api_key = $('aiTavily').value.trim();
  $('aiStatus').textContent = '正在保存…';
  try {
    const data = await api('/api/llm/config', payload);
    llm.configured = true;
    llm.model = data.model;
    llm.tavily = !!data.tavily_configured;
    refreshAiButton();
    $('aiStatus').textContent = '已启用 ' + data.model + '（密钥 ' + data.key_masked + '）' +
      (data.tavily_configured ? '，联网检索已启用（Tavily 密钥 ' + data.tavily_key_masked + '）。' : '。');
    setTimeout(() => $('aiSetup').close(), 700);
  } catch (error) {
    $('aiStatus').textContent = error.message;
  }
});

$('aiClear').addEventListener('click', async () => {
  try {
    await api('/api/llm/clear', {});
    llm.configured = false;
    llm.model = '';
    llm.tavily = false;
    refreshAiButton();
    $('aiStatus').textContent = '已清除本机配置；所有功能恢复纯离线。';
    $('aiClear').hidden = true;
    $('aiSave').disabled = true;
  } catch (error) { $('aiStatus').textContent = error.message; }
});

/* AI 解读 / 联网溯源改为勾选项，随「开始来源审查」一并执行 */
async function runInterpret(code, name) {
  const data = await api('/api/interpret', { code, name });
  if (data.llm && data.llm.text) {
    renderAiCard('interpret', { model: data.llm.model, text: data.llm.text, searches: data.llm.searches });
  } else if (data.llm && data.llm.error) {
    renderAiCard('interpret', { text: data.markers.summary, offline: true, note: data.llm.error });
  } else {
    renderAiCard('interpret', { text: data.markers.summary, offline: true, note: '未配置大模型：以上为本机确定性许可证标记提取。' });
  }
}

async function runWebprobe(code, name, license, usage) {
  const data = await api('/api/webprobe', { code, name, license, usage });
  renderWebprobe(data);
}

$('assistSummary').addEventListener('click', async () => {
  if (busy || !latest) return;
  const button = $('assistSummary');
  button.disabled = true;
  button.textContent = '生成中…';
  try {
    const data = await api('/api/assist', { action: 'summary' });
    renderAiCard('summary', data);
  } catch (error) { toast(error.message); } finally {
    button.disabled = false;
    button.textContent = 'AI 摘要';
  }
});

$('askForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy) return;
  const question = $('askInput').value.trim();
  if (!question) return;
  const input = $('askInput');
  input.disabled = true;
  try {
    const data = await api('/api/assist', { action: 'ask', question,
      search: $('askWeb').checked && llm.tavily });
    renderAiCard('ask', Object.assign({ note: '问题：' + question }, data));
    $('askInput').value = '';
  } catch (error) { toast(error.message); } finally { input.disabled = false; input.focus(); }
});

$('licenceExplain').addEventListener('click', async () => {
  const button = $('licenceExplain');
  button.disabled = true;
  button.textContent = '解释中…';
  try {
    const data = await api('/api/license/explain', {
      source: $('sourceLicense').value, target: $('destinationLicense').value, usage: $('licenseUsage').value });
    if (data.llm && data.llm.text) {
      const wrap = $('licenseResult');
      wrap.append(node('b', 'AI 通俗解释 · ' + data.llm.model), node('p', data.llm.text, 'ai-inline'));
    } else if (data.llm && data.llm.error) {
      toast(data.llm.error);
    } else {
      toast('未配置大模型；上方为规则引擎的原始推理结果。');
    }
  } catch (error) { toast(error.message); } finally {
    button.disabled = false;
    button.textContent = 'AI 通俗解释';
  }
});

function initAi(health) {
  llm.configured = !!(health.llm && health.llm.configured);
  llm.model = (health.llm && health.llm.model) || '';
  llm.baseUrl = (health.llm && health.llm.base_url) || '';
  llm.tavily = !!(health.llm && health.llm.tavily_configured);
  refreshAiButton();
  $('licenceExplain').disabled = false;
  if (!llm.configured && !localStorage.getItem('cg-ai-setup-seen')) {
    localStorage.setItem('cg-ai-setup-seen', '1');
    openAiSetup(false);
  }
}

buildDial();
setDial();

api('/api/health').then((data) => {
  token = data.token;
  const stats = data.stats;
  $('corpusFiles').textContent = fmt(stats.documents);
  $('corpusChunks').textContent = fmt(stats.chunks);
  $('corpusPackages').textContent = fmt(stats.packages);
  $('corpusReadable').textContent = `${fmt(data.corpus.readable)}/${fmt(data.corpus.total)}`;
  $('engineModel').textContent = data.model.replace('（未加载模型）', '');
  $('engineLayers').textContent = (stats.params.active_layers || []).join(' · ');
  $('engineIndex').textContent = 'v' + stats.index_version;
  $('engineLicences').textContent = (stats.licenses || []).length + ' 种';
  $('factDocs').textContent = fmt(stats.documents);
  $('factChunks').textContent = fmt(stats.chunks);
  $('factPkgs').textContent = fmt(stats.packages);
  $('factLic').textContent = ((stats.licenses || []).length) + ' 种';
  const ready = data.ready;
  $('connection').textContent = ready ? '● 本机引擎就绪' : '● 语料缺失';
  $('connection').classList.toggle('is-ready', ready);
  $('connection').classList.toggle('is-down', !ready);
  if (!ready) { $('scan').disabled = true; toast('语料不完整，扫描已禁用；请重新建立语料。'); }
  initAi(data);
}).catch((error) => {
  $('connection').textContent = '● 本机引擎未连接';
  $('connection').classList.remove('is-ready');
  $('connection').classList.add('is-down');
  $('scan').disabled = true;
  toast(error.message);
});
