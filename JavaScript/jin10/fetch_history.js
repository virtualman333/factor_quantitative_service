'use strict';

/*
 临时功能：通过金十接口递归抓取历史“重要”快讯，并写入 MySQL
 要点：
 - 仅处理 important == 1 的数据
 - 抽取 data.content 并基于 IGNORE_KEYWORDS 过滤
 - 用 item.time 作为 captured_at 导入时间
 - 完成一轮后，用本轮最后一项的 time 作为下一轮请求的 max_time，若相同则退 1 秒避免死循环
 - 通过环境变量或命令行参数控制起始/终止时间和节流：
   * MAX_TIME / --max-time : 初始 max_time（默认当前本地时间）
   * MIN_TIME / --min-time : 当下一轮 max_time 早于或等于此时间则停止（可选）
   * PAGES_LIMIT           : 最大翻页轮数（默认 2000）
   * PAUSE_MS              : 每轮之间暂停毫秒（默认 300）
   * CHANNEL               : 接口 channel 参数（默认 -8200）

 依赖：Node >= 18（原生 fetch）
 运行：
   npm run fetch-jin10-history -- --max-time="2025-08-14 13:00:00" --min-time="2025-08-01 00:00:00"
 */

const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const mysql = require('mysql2/promise');

// ---- 配置文件加载（JavaScript/jin10/config.local.json > JavaScript/jin10/config.json）----
function applyConfigFromFile() {
  try {
    const candidates = ['config.local.json', 'config.json'];
    for (const name of candidates) {
      const p = path.join(__dirname, name);
      if (!fs.existsSync(p)) continue;
      const raw = fs.readFileSync(p, 'utf-8');
      const data = JSON.parse(raw);
      if (data && typeof data === 'object') {
        for (const [k, v] of Object.entries(data)) {
          if (process.env[k] != null && process.env[k] !== '') continue; // 不覆盖已存在 env
          let val = v;
          if (Array.isArray(v)) val = v.join(',');
          else if (typeof v === 'boolean' || typeof v === 'number') val = String(v);
          else if (v == null) continue;
          process.env[k] = val;
        }
      }
      console.log(`[config] loaded ${name}`);
      break; // 命中一个文件后即停止（local 优先）
    }
  } catch (e) {
    console.warn('[config] load failed:', e && e.message ? e.message : e);
  }
}
applyConfigFromFile();

// ---- MySQL 初始化（与 JavaScript/jin10/index.js 保持一致）----
const MYSQL_HOST = process.env.DB_HOST || process.env.MYSQL_HOST || '47.119.132.60';
const MYSQL_PORT = Number(process.env.DB_PORT || process.env.MYSQL_PORT || 3306);
const MYSQL_USER = process.env.DB_USER || process.env.MYSQL_USER || 'intelligenceAutoTrade';
const MYSQL_PASSWORD = process.env.DB_PASS || process.env.MYSQL_PASSWORD || 'intelligenceAutoTrade';
const MYSQL_DATABASE = process.env.DB_NAME || process.env.MYSQL_DATABASE || 'intelligenceautotrade';

let pool;
async function initMySQL() {
  if (pool) return pool;
  pool = mysql.createPool({
    host: MYSQL_HOST,
    port: MYSQL_PORT,
    user: MYSQL_USER,
    password: MYSQL_PASSWORD,
    database: MYSQL_DATABASE,
    waitForConnections: true,
    connectionLimit: Number(process.env.DB_POOL_SIZE || 5),
    charset: 'utf8mb4',
    timezone: 'local',
  });

  const createSql = `
    CREATE TABLE IF NOT EXISTS flash_entries (
      id BIGINT AUTO_INCREMENT PRIMARY KEY,
      text LONGTEXT NOT NULL,
      text_hash CHAR(64) NOT NULL,
      source VARCHAR(32) DEFAULT 'jin10',
      captured_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      INDEX idx_flash_entries_captured_at (captured_at),
      UNIQUE KEY ux_flash_entries_hash (text_hash)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
  `;
  await pool.query(createSql);
  return pool;
}

async function insertEntryWithTime(text, timeStr) {
  const hash = crypto.createHash('sha256').update(text, 'utf8').digest('hex');
  const [res] = await pool.execute(
    'INSERT IGNORE INTO flash_entries (text, text_hash, source, captured_at) VALUES (?, ?, ?, ?)',
    [text, hash, 'jin10', timeStr]
  );
  return { changes: res.affectedRows || 0, lastID: res.insertId || 0 };
}

// ---- 文本处理与过滤 ----
function normalizeText(s) {
  if (!s) return '';
  let t = String(s);
  t = t.replace(/[\u200B-\u200D\uFEFF]/g, ''); // 零宽
  t = t.replace(/\u3000/g, ' '); // 全角空格
  t = t.replace(/\s+/g, ' ').trim(); // 折叠空白
  return t;
}

const IGNORE_KEYWORDS = (process.env.IGNORE_KEYWORDS || 'vip,一览,图示,点击查看,点击获取,点击观看')
  .split(',')
  .map((s) => s.trim().toLowerCase())
  .filter(Boolean);

function shouldIgnore(text) {
  const lower = (text || '').toLowerCase();
  if (IGNORE_KEYWORDS.some((kw) => lower.includes(kw))) return true;
  const trimmed = (text || '').trim();
  if (trimmed.endsWith('?') || trimmed.endsWith('？') || trimmed.endsWith('！') || trimmed.endsWith('!')) return true;
  return false;
}

// ---- 时间工具 ----
function parseTimeStrToDate(s) {
  // 期望格式：YYYY-MM-DD HH:mm:ss
  if (!s) return null;
  const m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})$/);
  if (!m) return null;
  const [, Y, M, D, h, m2, s2] = m;
  return new Date(Number(Y), Number(M) - 1, Number(D), Number(h), Number(m2), Number(s2)); // 本地时区
}

function formatDateToYmdHms(d) {
  const pad = (n) => String(n).padStart(2, '0');
  const Y = d.getFullYear();
  const M = pad(d.getMonth() + 1);
  const D = pad(d.getDate());
  const h = pad(d.getHours());
  const m = pad(d.getMinutes());
  const s = pad(d.getSeconds());
  return `${Y}-${M}-${D} ${h}:${m}:${s}`;
}

function encodeMaxTimeParam(s) {
  // 接口示例用加号连接日期与时间：YYYY-MM-DD+HH:mm:ss
  // 注意：后续我们手动拼接查询字符串，避免 URLSearchParams 将 '+' 编码为 '%2B'
  return String(s).replace(' ', '+');
}

// ---- CLI 参数解析（支持 --max-time 与 --min-time）----
function parseCliArgs() {
  const args = process.argv.slice(2);
  const result = {};
  for (const a of args) {
    const m = a.match(/^--([^=]+)=(.*)$/);
    if (m) {
      result[m[1]] = m[2];
    }
  }
  return result;
}

// ---- 抓取逻辑 ----
const API_BASE = 'https://flash-api.jin10.com/get_flash_list';
const CHANNEL = process.env.CHANNEL || '-8200';
const VIP = '1';
// 可配置的应用头
const X_APP_ID = process.env.X_APP_ID || process.env.JIN10_X_APP_ID || 'bVBF4FyRTn5NJF5n';
const X_VERSION = process.env.X_VERSION || process.env.JIN10_X_VERSION || '1.0.0';
const HANDLE_ERROR_HEADER = String(process.env.HANDLEERROR || process.env.JIN10_HANDLEERROR || 'true');

// 重试与节流设置
const RETRY = Number(process.env.RETRY || 5);
const RETRY_BASE_MS = Number(process.env.RETRY_BASE_MS || 800);
const RETRY_JITTER_MS = Number(process.env.RETRY_JITTER_MS || 200);

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

function buildHeaders() {
  const headers = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Connection': 'keep-alive',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
    'Referer': 'https://www.jin10.com/',
    'Origin': 'https://www.jin10.com',
    'Host': 'flash-api.jin10.com',
    'Accept-Encoding': 'gzip, deflate, br',
    'X-Requested-With': 'XMLHttpRequest',
    'x-app-id': X_APP_ID,
    'x-version': X_VERSION,
    'handleerror': HANDLE_ERROR_HEADER,
    // 浏览器提示头（部分风控可能检查）
    'sec-ch-ua': '"Google Chrome";v="127", "Chromium";v="127", "Not=A?Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-site',
    // Edge/Chrome 可能发送的优先级提示
    'priority': 'u=1, i',
  };
  const cookie = process.env.JIN10_COOKIE || process.env.JIN10_COOKIES || '';
  if (cookie) headers['Cookie'] = cookie;
  const ua = process.env.UA || process.env.JIN10_UA || '';
  if (ua) headers['User-Agent'] = ua;
  return headers;
}

async function fetchOnce(maxTimeStr) {
  // 保持与浏览器一致：max_time 中为未编码的加号
  const q = `channel=${encodeURIComponent(CHANNEL)}&vip=${encodeURIComponent(VIP)}&max_time=${encodeMaxTimeParam(maxTimeStr)}`;
  const url = `${API_BASE}?${q}`;
  // 可选调试：打印一次 URL（不含敏感 Cookie）
  if (process.env.DEBUG_URL) console.log('[history] GET', url);

  let lastErr;
  for (let attempt = 1; attempt <= RETRY; attempt++) {
    try {
      const res = await fetch(url, {
        method: 'GET',
        headers: buildHeaders(),
      });
      if (!res.ok) {
        const txt = await res.text().catch(() => '');
        const err = new Error(`HTTP ${res.status} ${res.statusText}: ${txt.slice(0, 200)}`);
        // 对 5xx/429/403 做重试
        if ([429, 403, 500, 502, 503, 504].includes(res.status) && attempt < RETRY) {
          const backoff = RETRY_BASE_MS * Math.pow(2, attempt - 1) + Math.floor(Math.random() * RETRY_JITTER_MS);
          console.warn(`[history] fetch attempt ${attempt} failed (${res.status}), backoff ${backoff}ms`);
          await sleep(backoff);
          continue;
        }
        throw err;
      }

      // 某些情况下会返回 text/html（如网关错误页），这里容错处理
      const ct = res.headers.get('content-type') || '';
      let data;
      if (ct.includes('application/json')) {
        data = await res.json();
      } else {
        const txt = await res.text();
        try { data = JSON.parse(txt); } catch (_) {
          throw new Error(`Unexpected content-type: ${ct}; body: ${txt.slice(0, 200)}`);
        }
      }

      const arr = (data && Array.isArray(data.data)) ? data.data : Array.isArray(data) ? data : [];
      return arr;
    } catch (e) {
      lastErr = e;
      if (attempt < RETRY) {
        const backoff = RETRY_BASE_MS * Math.pow(2, attempt - 1) + Math.floor(Math.random() * RETRY_JITTER_MS);
        console.warn(`[history] fetch attempt ${attempt} error: ${e && e.message ? e.message : e}; retry in ${backoff}ms`);
        await sleep(backoff);
        continue;
      }
      break;
    }
  }
  throw lastErr || new Error('fetchOnce failed');
}

async function main() {
  await initMySQL();

  const cli = parseCliArgs();
  const PAGES_LIMIT = Number(process.env.PAGES_LIMIT || 2000);
  const PAUSE_MS = Number(process.env.PAUSE_MS || 300);

  const nowStr = formatDateToYmdHms(new Date());
  const initialMax = cli['max-time'] || process.env.MAX_TIME || nowStr;
  const minTimeStr = cli['min-time'] || process.env.MIN_TIME || '';
  const minDate = minTimeStr ? parseTimeStrToDate(minTimeStr) : null;
  const minTs = minDate ? minDate.getTime() : null;

  let page = 0;
  let maxTimeStr = initialMax;
  let processed = 0, inserted = 0, skippedIgnored = 0, skippedNotImportant = 0, skippedEmpty = 0, duplicates = 0;

  console.log('[history] start with max_time =', maxTimeStr, 'min_time =', minTimeStr || '(none)');

  while (page < PAGES_LIMIT) {
    page += 1;
    let arr;
    try {
      arr = await fetchOnce(maxTimeStr);
    } catch (e) {
      console.error(`[history] fetch page ${page} failed:`, e && e.message ? e.message : e);
      break;
    }

    if (!arr || arr.length === 0) {
      console.log(`[history] page ${page}: empty, stop.`);
      break;
    }

    // 处理本页数据
    for (const item of arr) {
      processed += 1;
      if (!item || item.important !== 1) { skippedNotImportant += 1; continue; }
      const timeStr = item.time || '';
      const content = item.data && typeof item.data.content === 'string' ? item.data.content : '';
      const normalized = normalizeText(content);
      if (!normalized) { skippedEmpty += 1; continue; }
      if (shouldIgnore(normalized)) { skippedIgnored += 1; continue; }

      try {
        const r = await insertEntryWithTime(normalized, timeStr);
        if (r.changes > 0) inserted += 1; else duplicates += 1;
      } catch (e) {
        console.warn('[history] insert failed:', e && e.message ? e.message : e);
      }
    }

    // 计算下一轮的 max_time
    const last = arr[arr.length - 1];
    const lastTime = last && last.time ? String(last.time) : maxTimeStr;

    let nextMax = lastTime;
    if (nextMax === maxTimeStr) {
      const dt = parseTimeStrToDate(nextMax) || new Date();
      dt.setSeconds(dt.getSeconds() - 1);
      nextMax = formatDateToYmdHms(dt);
    }

    // 终止条件：到达下界
    if (minTs != null) {
      const nextDt = parseTimeStrToDate(nextMax) || new Date();
      if (nextDt.getTime() <= minTs) {
        console.log(`[history] reached min_time boundary (${minTimeStr}), stop.`);
        maxTimeStr = nextMax;
        break;
      }
    }

    maxTimeStr = nextMax;
    console.log(`[history] page ${page} done. next max_time -> ${maxTimeStr}`);

    if (PAUSE_MS > 0) await new Promise((r) => setTimeout(r, PAUSE_MS));
  }

  console.log('[history] summary:', { processed, inserted, skippedIgnored, skippedNotImportant, skippedEmpty, duplicates, lastMaxTime: maxTimeStr, pages: page });
}

main()
  .catch((err) => {
    console.error('[history] fatal:', err && err.stack ? err.stack : err);
    process.exitCode = 1;
  })
  .finally(async () => {
    try { if (pool) await pool.end(); } catch (_) {}
  });

process.on('SIGINT', async () => {
  console.log('\n[history] SIGINT');
  try { if (pool) await pool.end(); } catch (_) {}
  process.exit(0);
});
