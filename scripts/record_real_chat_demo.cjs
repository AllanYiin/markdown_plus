'use strict';

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const Module = require('module');

const bundledNodeModules = 'C:\\Users\\allan\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\node_modules';
process.env.NODE_PATH = [
  process.env.NODE_PATH || '',
  bundledNodeModules,
  path.join(bundledNodeModules, '.pnpm', 'playwright-core@1.59.1', 'node_modules'),
  path.join(bundledNodeModules, '.pnpm', 'playwright@1.59.1', 'node_modules'),
].filter(Boolean).join(path.delimiter);
Module._initPaths();

const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const DATA_ROOT = path.resolve(ROOT, '..', 'benchmark', 'results', 'research_report', 'research_report_03');
const OUT_DIR = path.join(ROOT, 'out', 'real-chat-demo');
const PORT = Number(process.env.CHAT_DEMO_PORT || 8771);
const BASE_URL = `http://127.0.0.1:${PORT}`;
const QUESTION = '從性價比來看該選擇哪個向量資料庫?';

const MODE = process.argv[2] || 'record';
const REHEARSE = MODE === 'rehearse';
const DISCOVER = MODE === 'discover';
const CLEAN_UI = process.env.CLEAN_UI === '1';

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function waitForHealth(timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = '';
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${BASE_URL}/api/health`);
      if (res.ok) return await res.json();
      lastError = `HTTP ${res.status}`;
    } catch (err) {
      lastError = err.message;
    }
    await sleep(500);
  }
  throw new Error(`server did not become healthy: ${lastError}`);
}

function startServer() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const stdout = fs.openSync(path.join(OUT_DIR, 'server.stdout.log'), 'w');
  const stderr = fs.openSync(path.join(OUT_DIR, 'server.stderr.log'), 'w');
  const child = spawn('python', ['server.py', '--port', String(PORT)], {
    cwd: ROOT,
    stdio: ['ignore', stdout, stderr],
    env: process.env,
    windowsHide: true,
  });
  child.on('exit', code => {
    if (code !== null && code !== 0) {
      console.error(`server exited with code ${code}`);
    }
  });
  return child;
}

async function injectCursor(page) {
  await page.evaluate(() => {
    if (document.getElementById('demo-cursor')) return;
    const cursor = document.createElement('div');
    cursor.id = 'demo-cursor';
    cursor.innerHTML = `<svg width="26" height="26" viewBox="0 0 24 24" fill="none">
      <path d="M5 3L19 12L12 13L9 20L5 3Z" fill="white" stroke="#111827" stroke-width="1.7" stroke-linejoin="round"/>
    </svg>`;
    cursor.style.cssText = [
      'position:fixed',
      'z-index:999999',
      'pointer-events:none',
      'width:26px',
      'height:26px',
      'left:0',
      'top:0',
      'transition:left .12s linear, top .12s linear',
      'filter:drop-shadow(1px 2px 3px rgba(0,0,0,.35))',
    ].join(';');
    document.body.appendChild(cursor);
    document.addEventListener('mousemove', event => {
      cursor.style.left = `${event.clientX}px`;
      cursor.style.top = `${event.clientY}px`;
    });
  });
}

async function injectSubtitleBar(page) {
  await page.evaluate(() => {
    if (document.getElementById('demo-subtitle')) return;
    const bar = document.createElement('div');
    bar.id = 'demo-subtitle';
    bar.style.cssText = [
      'position:fixed',
      'left:0',
      'right:0',
      'bottom:0',
      'z-index:999998',
      'padding:12px 26px',
      'background:rgba(15,23,42,.84)',
      'color:white',
      'font:600 17px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC",sans-serif',
      'text-align:center',
      'opacity:0',
      'transition:opacity .25s',
      'pointer-events:none',
    ].join(';');
    document.body.appendChild(bar);
  });
}

async function showSubtitle(page, text, hold = 900) {
  if (CLEAN_UI) {
    if (text && hold) await page.waitForTimeout(Math.min(hold, 350));
    return;
  }
  await page.evaluate(t => {
    const bar = document.getElementById('demo-subtitle');
    if (!bar) return;
    bar.textContent = t || '';
    bar.style.opacity = t ? '1' : '0';
  }, text);
  if (text && hold) await page.waitForTimeout(hold);
}

async function moveAndClick(page, locator, label, postClickDelay = 700) {
  const el = typeof locator === 'string' ? page.locator(locator).first() : locator;
  if (!(await el.isVisible().catch(() => false))) {
    throw new Error(`"${label}" not visible`);
  }
  await el.scrollIntoViewIfNeeded();
  await page.waitForTimeout(250);
  const box = await el.boundingBox();
  if (box) {
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 14 });
    await page.waitForTimeout(350);
  }
  await el.click();
  await page.waitForTimeout(postClickDelay);
}

async function typeSlowly(page, locator, text, label) {
  const el = typeof locator === 'string' ? page.locator(locator).first() : locator;
  if (!(await el.isVisible().catch(() => false))) {
    throw new Error(`"${label}" not visible`);
  }
  await moveAndClick(page, el, label, 250);
  await el.fill('');
  await el.pressSequentially(text, { delay: 28 });
  await page.waitForTimeout(500);
}

async function ensureVisible(page, selector, label) {
  const el = page.locator(selector).first();
  const visible = await el.isVisible().catch(() => false);
  console.log(`${visible ? 'REHEARSAL OK' : 'REHEARSAL FAIL'}: ${label} -> ${selector}`);
  return visible;
}

async function discover(page) {
  const fields = await page.evaluate(() => {
    const els = [];
    document.querySelectorAll('input, select, textarea, button, [contenteditable], details, summary').forEach(el => {
      const style = window.getComputedStyle(el);
      const visible = style.visibility !== 'hidden' && style.display !== 'none';
      if (!visible) return;
      els.push({
        tag: el.tagName,
        id: el.id || '',
        cls: el.className || '',
        type: el.type || '',
        name: el.name || '',
        placeholder: el.placeholder || '',
        text: (el.textContent || '').trim().substring(0, 80),
        dataMode: el.getAttribute('data-mode') || el.getAttribute('data-doc-mode') || '',
        role: el.getAttribute('role') || '',
      });
    });
    return els;
  });
  fs.writeFileSync(path.join(OUT_DIR, 'discover-elements.json'), JSON.stringify(fields, null, 2), 'utf8');
  console.log(JSON.stringify(fields, null, 2));
}

async function uploadDoc(page, mode, filePath, subtitle) {
  await selectMode(page, mode, subtitle);
  const selector = `.doc-load[data-doc-mode="${mode}"]`;
  console.log(`UPLOAD ${mode}: ${filePath}`);
  await moveAndClick(page, selector, `load ${mode}`, 300);
  await page.locator('#file-input').setInputFiles(filePath);
  await page.waitForFunction(
    ({ modeName }) => {
      const id = modeName === 'plain' ? 'doc-stats-plain' : 'doc-stats-blocks';
      const text = document.getElementById(id)?.textContent || '';
      return text.includes('tokens') && !text.includes('… tokens');
    },
    { modeName: mode },
    { timeout: 20000 },
  );
  await page.waitForTimeout(1300);
}

async function selectMode(page, mode, subtitle) {
  await showSubtitle(page, subtitle);
  await moveAndClick(page, `.mode-tab[data-mode="${mode}"]`, `select ${mode}`, 900);
}

async function askQuestion(page, mode, subtitle) {
  console.log(`ASK ${mode}`);
  await selectMode(page, mode, subtitle);
  await typeSlowly(page, '#chat-input', QUESTION, `question ${mode}`);
  await showSubtitle(page, mode === 'plain'
    ? 'Plain CLI：模型自行下 bash 指令找證據'
    : 'Markdown+：模型使用 mdp_* block 工具找證據');
  await moveAndClick(page, '#chat-send', `send ${mode}`, 1000);
  await page.waitForFunction(
    ({ modeName }) => {
      const id = modeName === 'plain' ? 'status-plain' : 'status-blocks';
      const text = document.getElementById(id)?.textContent || '';
      return text.startsWith('完成') || text.startsWith('錯誤');
    },
    { modeName: mode },
    { timeout: 360000 },
  );
  await page.waitForTimeout(3500);
}

async function extractReport(page) {
  return await page.evaluate(() => {
    const collect = mode => {
      const panel = document.getElementById(`panel-${mode}`);
      const status = document.getElementById(`status-${mode}`)?.textContent || '';
      const stats = document.getElementById(`doc-stats-${mode}`)?.textContent || '';
      const cards = Array.from(panel?.querySelectorAll('.tool-card') || []).map(card => {
        return {
          kind: card.querySelector('.tool-kind')?.textContent || '',
          name: card.querySelector('.tool-name')?.textContent || '',
          inline: card.querySelector('.tool-args-inline')?.textContent || '',
          body: card.querySelector('.tool-body')?.textContent?.slice(0, 1200) || '',
        };
      });
      const answers = Array.from(panel?.querySelectorAll('.msg-assistant .msg-body') || [])
        .map(el => el.textContent || '')
        .filter(Boolean);
      return { status, stats, cards, answers };
    };
    return { blocks: collect('blocks'), plain: collect('plain') };
  });
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const server = startServer();
  let browser;
  try {
    const health = await waitForHealth();
    console.log('HEALTH', JSON.stringify(health));
    console.log(`MODE ${MODE}`);
    browser = await chromium.launch({ headless: true });
    const contextOptions = {
      viewport: { width: 1280, height: 720 },
      deviceScaleFactor: 1,
    };
    if (!DISCOVER && !REHEARSE) {
      contextOptions.recordVideo = { dir: OUT_DIR, size: { width: 1280, height: 720 } };
    }
    const context = await browser.newContext(contextOptions);
    const page = await context.newPage();
    await page.goto(`${BASE_URL}/chat.html`, { waitUntil: 'domcontentloaded' });
    await injectCursor(page);
    if (!CLEAN_UI) await injectSubtitleBar(page);
    await page.waitForTimeout(1000);

    if (DISCOVER) {
      await discover(page);
      await context.close();
      return;
    }

    const selectors = [
      ['.doc-load[data-doc-mode="blocks"]', 'Markdown+ load button'],
      ['.mode-tab[data-mode="blocks"]', 'Markdown+ tab'],
      ['.mode-tab[data-mode="plain"]', 'Plain tab'],
      ['#chat-input', 'Chat input'],
      ['#chat-send', 'Send button'],
    ];
    let ok = true;
    for (const [selector, label] of selectors) {
      ok = (await ensureVisible(page, selector, label)) && ok;
    }
    if (!ok) throw new Error('rehearsal selectors failed');
    console.log('REHEARSAL SELECTORS OK');

    await uploadDoc(
      page,
      'blocks',
      path.join(DATA_ROOT, 'markdown_plus.md'),
      'Step 1 - Markdown+ 載入 markdown_plus.md',
    );
    await uploadDoc(
      page,
      'plain',
      path.join(DATA_ROOT, 'markdown.md'),
      'Step 2 - Plain CLI 載入 markdown.md',
    );

    if (REHEARSE) {
      await showSubtitle(page, 'Rehearsal passed - selectors and uploads verified', 1500);
      console.log('REHEARSAL COMPLETE');
      await context.close();
      return;
    }

    await askQuestion(page, 'blocks', 'Step 3 - Markdown+ 先查詢');
    await showSubtitle(page, '看工具卡：mdp_search_blocks / mdp_read_block', 1500);
    await page.evaluate(() => document.getElementById('messages-blocks')?.scrollTo({ top: 0, behavior: 'smooth' }));
    await page.waitForTimeout(1200);
    await page.evaluate(() => document.getElementById('messages-blocks')?.scrollTo({ top: 10000, behavior: 'smooth' }));
    await page.waitForTimeout(2200);

    await askQuestion(page, 'plain', 'Step 4 - Plain CLI 查詢同一題');
    await showSubtitle(page, '看工具卡：bash 指令與 stdout 行號證據', 1500);
    await page.evaluate(() => document.getElementById('messages-plain')?.scrollTo({ top: 0, behavior: 'smooth' }));
    await page.waitForTimeout(1200);
    await page.evaluate(() => document.getElementById('messages-plain')?.scrollTo({ top: 10000, behavior: 'smooth' }));
    await page.waitForTimeout(2500);

    await selectMode(page, 'blocks', 'Step 5 - 對比：block 工具回傳更聚焦的上下文');
    await page.waitForTimeout(2500);
    await selectMode(page, 'plain', 'Step 6 - 對比：row/line 讀取更依賴行號範圍');
    await page.waitForTimeout(2500);
    await showSubtitle(page, '重點不是答案本身，而是兩種讀取策略的上下文成本', 2500);
    await showSubtitle(page, '', 700);

    const report = await extractReport(page);
    fs.writeFileSync(path.join(OUT_DIR, 'real_chat_recording_report.json'), JSON.stringify(report, null, 2), 'utf8');

    const video = page.video();
    await context.close();
    if (video) {
      const src = await video.path();
      const dest = path.join(OUT_DIR, 'real_chat_demo.webm');
      fs.copyFileSync(src, dest);
      console.log('VIDEO', dest);
    }
  } finally {
    if (browser) await browser.close().catch(() => {});
    server.kill('SIGTERM');
  }
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
