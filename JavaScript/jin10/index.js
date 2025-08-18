/*
 极简 Jin10.com 爬虫
 - 使用 Puppeteer 捕获实时“.flash-text”内容
 - 保存到远程 MySQL 数据库
 */

const path = require('path');
const fs = require('fs');
const puppeteer = require('puppeteer');
const mysql = require('mysql2/promise');
const crypto = require('crypto');

// ---- 配置文件加载（config.local.json > config.json）----
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
          // 不覆盖已有的真实环境变量
          if (process.env[k] != null && process.env[k] !== '') continue;
          let val = v;
          if (Array.isArray(v)) {
            val = v.join(',');
          } else if (typeof v === 'boolean' || typeof v === 'number') {
            val = String(v);
          } else if (v == null) {
            continue;
          }
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

// ---- MySQL 初始化 ----
const MYSQL_HOST = process.env.DB_HOST || process.env.MYSQL_HOST || '47.119.132.60';
const MYSQL_PORT = Number(process.env.DB_PORT || process.env.MYSQL_PORT || 3306);
const MYSQL_USER = process.env.DB_USER || process.env.MYSQL_USER || 'intelligenceAutoTrade';
const MYSQL_PASSWORD = process.env.DB_PASS || process.env.MYSQL_PASSWORD || 'intelligenceAutoTrade';
const MYSQL_DATABASE = process.env.DB_NAME || process.env.MYSQL_DATABASE || 'intelligenceautotrade';

let pool; // mysql 连接池

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
      captured_date DATE AS (DATE(captured_at)) STORED,
      INDEX idx_flash_entries_captured_at (captured_at),
      UNIQUE KEY ux_flash_entries_hash_date (text_hash, captured_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
  `;
  await pool.query(createSql);
  
  // 迁移：确保已存在的表也具备按“文本哈希+日期”的唯一约束
  try {
    // 1) 确保生成列 captured_date 存在
    const [cols] = await pool.query("SHOW COLUMNS FROM flash_entries LIKE 'captured_date'");
    if (!Array.isArray(cols) || cols.length === 0) {
      await pool.query("ALTER TABLE flash_entries ADD COLUMN captured_date DATE AS (DATE(captured_at)) STORED");
      console.log('[mysql] added generated column captured_date');
    }

    // 2) 检查索引情况
    const [idx] = await pool.query('SHOW INDEX FROM flash_entries');
    const rows = Array.isArray(idx) ? idx : [];
    const hasOldUnique = rows.some(r => r.Key_name === 'ux_flash_entries_hash' && (r.Non_unique === 0 || r.Non_unique === '0'));

    // 旧唯一索引仅基于 text_hash，会阻止跨日期的重复文本
    if (hasOldUnique) {
      try {
        await pool.query('ALTER TABLE flash_entries DROP INDEX ux_flash_entries_hash');
        console.log('[mysql] dropped old unique index ux_flash_entries_hash');
      } catch (e) {
        console.warn('[mysql] drop old unique index failed:', e && e.message ? e.message : e);
      }
    }

    // 重新获取索引并确保新唯一索引存在
    const [idx2] = await pool.query('SHOW INDEX FROM flash_entries');
    const rows2 = Array.isArray(idx2) ? idx2 : [];
    const hasNewUnique = rows2.some(r => r.Key_name === 'ux_flash_entries_hash_date');
    if (!hasNewUnique) {
      try {
        await pool.query('ALTER TABLE flash_entries ADD UNIQUE KEY ux_flash_entries_hash_date (text_hash, captured_date)');
        console.log('[mysql] added unique index ux_flash_entries_hash_date (text_hash, captured_date)');
      } catch (e) {
        console.warn('[mysql] add new unique index failed:', e && e.message ? e.message : e);
      }
    }
  } catch (e) {
    console.warn('[mysql] migration check failed:', e && e.message ? e.message : e);
  }
  return pool;
}

// ---- 可恢复错误与重试封装 ----
const TRANSIENT_CODES = new Set([
  'ECONNRESET',
  'ETIMEDOUT',
  'EPIPE',
  'ECONNREFUSED',
  'EHOSTUNREACH',
  'PROTOCOL_CONNECTION_LOST',
  'ER_LOCK_DEADLOCK',
  'ER_LOCK_WAIT_TIMEOUT',
]);

function isTransientError(err) {
  if (!err) return false;
  const code = err.code || (err.cause && err.cause.code);
  if (code && TRANSIENT_CODES.has(code)) return true;
  const msg = String(err.message || '').toLowerCase();
  if (
    /read econnreset|reset by peer|socket hang up|connection lost|getaddrinfo enotfound|connect etimedout|ehostunreach|econnrefused/.test(
      msg
    )
  ) {
    return true;
  }
  return false;
}

async function withRetry(
  fn,
  {
    retries = 5,
    baseDelay = 300,
    maxDelay = 5000,
    jitter = true,
    onRetry = () => {},
  } = {}
) {
  let attempt = 0;
  // eslint-disable-next-line no-constant-condition
  while (true) {
    try {
      return await fn();
    } catch (err) {
      attempt += 1;
      if (attempt > retries || !isTransientError(err)) throw err;
      let delay = Math.min(maxDelay, baseDelay * 2 ** (attempt - 1));
      if (jitter) delay = Math.round(delay * (0.7 + Math.random() * 0.6));
      try { onRetry(err, attempt, delay); } catch (_) {}
      await new Promise((r) => setTimeout(r, delay));
    }
  }
}

async function insertEntry(text) {
  const hash = crypto.createHash('sha256').update(text, 'utf8').digest('hex');
  // 通过重试包装执行，处理 ECONNRESET 等瞬时错误
  const exec = () =>
    pool.execute(
      'INSERT IGNORE INTO flash_entries (text, text_hash, source) VALUES (?, ?, ?)',
      [text, hash, 'jin10']
    );
  const [res] = await withRetry(exec, {
    retries: Number(process.env.DB_RETRY || 5),
    baseDelay: Number(process.env.DB_RETRY_BASE || 300),
    maxDelay: Number(process.env.DB_RETRY_MAX || 5000),
    onRetry: (err, attempt, wait) => {
      console.warn(
        `[DB RETRY] attempt=${attempt} wait=${wait}ms code=${err && err.code} msg=${err && err.message}`
      );
    },
  });
  return { changes: res.affectedRows || 0, lastID: res.insertId || 0 };
}

// ---- 进程级去重（TTL）----
const DEDUP_WINDOW_MS = Number(process.env.DEDUP_WINDOW_MS || 3000); // 默认 3 秒
const recentTexts = new Map(); // 文本 -> 最近出现时间戳

function normalizeText(s) {
  if (!s) return '';
  let t = String(s);
  // 移除零宽字符
  t = t.replace(/[\u200B-\u200D\uFEFF]/g, '');
  // 规范全角空格
  t = t.replace(/\u3000/g, ' ');
  // 折叠空白
  t = t.replace(/\s+/g, ' ').trim();
  return t;
}

function shouldInsertText(text) {
  const now = Date.now();
  const last = recentTexts.get(text);
  if (last && now - last < DEDUP_WINDOW_MS) return false;
  recentTexts.set(text, now);
  // 定期清理
  if (recentTexts.size > 5000) {
    for (const [k, ts] of recentTexts) {
      if (now - ts > DEDUP_WINDOW_MS * 3) recentTexts.delete(k);
    }
  }
  return true;
}

// 忽略关键词（可通过 IGNORE_KEYWORDS 配置，默认：'vip,一览,图示'）
const IGNORE_KEYWORDS = (process.env.IGNORE_KEYWORDS || 'vip,一览,图示,点击查看,点击获取,点击观看')
  .split(',')
  .map((s) => s.trim().toLowerCase())
  .filter(Boolean);

function shouldIgnore(text) {
  const lower = (text || '').toLowerCase();
  // 关键词过滤
  if (IGNORE_KEYWORDS.some((kw) => lower.includes(kw))) return true;
  // 以问号（半角/全角）结尾则过滤
  const trimmed = (text || '').trim();
  if (trimmed.endsWith('?') || trimmed.endsWith('？') || trimmed.endsWith('！') || trimmed.endsWith('!')) return true;
  return false;
}

// ---- Puppeteer 爬虫 ----
let browser;
// 使用 Puppeteer 自带的 Chromium，移除本地浏览器路径探测与 executablePath
const headlessSetting = process.env.HEADLESS
  ? (process.env.HEADLESS === 'false' ? false : true)
  : 'new';
const targetUrl = process.env.JIN10_URL || 'https://www.jin10.com/';
// 仅抓取 .is-important 下的目标元素（来自配置 IS_IMPORTANT 或 isImportant）
const importantOnly = (() => {
  const v = process.env.IS_IMPORTANT ?? process.env.isImportant ?? '';
  const s = String(v).trim().toLowerCase();
  return s === '1' || s === 'true' || s === 'yes';
})();

async function start() {
  const launchOptions = {
    headless: headlessSetting, // 设置 HEADLESS=false 可以看到浏览器窗口
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-blink-features=AutomationControlled',
    ],
    defaultViewport: { width: 1280, height: 900 },
  };

  // 初始化 MySQL 连接与表结构
  await initMySQL();

  browser = await puppeteer.launch(launchOptions);

  const page = await browser.newPage();
  console.log('使用 Puppeteer 自带的 Chromium 启动浏览器');
  await page.setUserAgent(
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
  );
  await page.setExtraHTTPHeaders({ 'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8' });
  await page.evaluateOnNewDocument(() => {
    try {
      Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    } catch (e) {}
  });

  // 转发页面控制台日志（用于调试观察器行为）
  page.on('console', (msg) => console.log('[页面]', msg.text()));

  // 打开目标站点
  await page.goto(targetUrl, {
    waitUntil: 'domcontentloaded',
    timeout: 90_000,
  });

  // 尝试关闭 Cookie/同意 弹窗
  try {
    await page.evaluate(() => {
      const keywords = ['同意', '我知道了', '接受', 'Accept', '同意并继续'];
      const candidates = Array.from(
        document.querySelectorAll('button, a, [role="button"], .btn')
      );
      for (const text of keywords) {
        const el = candidates.find((e) => (e.innerText || '').includes(text));
        if (el) {
          el.click();
          break;
        }
      }
    });
  } catch (_) {}

  // 确认页面已有 .flash-text；若无则继续等待实时更新
  try {
    await page.waitForSelector(
      importantOnly
        ? '.is-important .flash-text, .is-important .right-content_intro'
        : '.flash-text, .right-content_intro',
      { timeout: 60_000 }
    );
  } catch (_) {
    console.log('初始加载未找到 .flash-text 或 .right-content_intro；等待实时更新...');
  }

  // 向页面暴露 Node 函数，用于接收新文本
  await page.exposeFunction('nodeInsertFlash', async (text) => {
    if (!text || typeof text !== 'string') return;
    const normalized = normalizeText(text);
    if (!normalized) return;
    if (shouldIgnore(normalized)) {
      console.log('已过滤（命中忽略关键词）:', normalized);
      return;
    }
    if (!shouldInsertText(normalized)) {
      console.log('已去重（TTL 窗口内跳过）:', normalized);
      return;
    }
    try {
      const res = await insertEntry(normalized);
      if (res && res.changes > 0) {
        console.log(`已写入 #${res.lastID}: ${normalized}`);
      } else {
        console.log('数据库唯一约束：重复已忽略：', normalized);
      }
    } catch (err) {
      console.error('数据库插入错误:', err && err.message ? err.message : err);
    }
  });

  // 安装 MutationObserver，捕获现有及新增的目标内容
  await page.evaluate((importantOnly) => {
    if (window.__FLASH_OBS_ATTACHED__) {
      console.log('已在主文档安装观察器，跳过');
      return;
    }
    window.__FLASH_OBS_ATTACHED__ = true;
    const seen = new Set();
    const targetSel = importantOnly
      ? '.is-important .flash-text, .is-important .right-content_intro'
      : '.flash-text, .right-content_intro';

    function getText(el) {
      const t = (el.innerText || el.textContent || '').trim();
      return t;
    }

    function collectFromRoot(root) {
      const list = [];
      if (root instanceof Element && root.matches(targetSel)) list.push(root);
      if (root instanceof Element) {
        list.push(...root.querySelectorAll(targetSel));
      } else if (root === document) {
        list.push(...document.querySelectorAll(targetSel));
      }
      return list;
    }

    function handleElements(els) {
      for (const el of els) {
        const text = getText(el);
        if (text && !seen.has(text)) {
          seen.add(text);
          // 忽略 TS：page.exposeFunction 已提供该方法
          // @ts-ignore
          window.nodeInsertFlash(text);
        }
      }
    }

    // 初始扫描
    handleElements(collectFromRoot(document));

    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.type === 'childList') {
          m.addedNodes.forEach((n) => {
            handleElements(collectFromRoot(n));
          });
        } else if (m.type === 'characterData') {
          const el = m.target && m.target.parentElement
            ? m.target.parentElement.closest('.flash-text, .right-content_intro')
            : null;
          if (el) {
            if (!importantOnly || el.closest('.is-important')) handleElements([el]);
          }
        } else if (m.type === 'attributes') {
          const el = m.target instanceof Element ? m.target : null;
          if (el) {
            if (el.matches(targetSel)) handleElements([el]);
            else handleElements(el.querySelectorAll(targetSel));
          }
        }
      }
    });

    observer.observe(document.documentElement || document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
    });

    console.log('已在主文档安装 .flash-text 观察器');
  }, importantOnly);

  // 为所有已存在的 iframe 注入观察器（适配站点在 iframe 中渲染）
  for (const frame of page.frames()) {
    try {
      await frame.evaluate((importantOnly) => {
        if (window.__FLASH_OBS_ATTACHED__) {
          console.log('该 iframe 已安装观察器，跳过');
          return;
        }
        window.__FLASH_OBS_ATTACHED__ = true;
        const seen = new Set();
        const targetSel = importantOnly
          ? '.is-important .flash-text, .is-important .right-content_intro'
          : '.flash-text, .right-content_intro';

        function getText(el) {
          const t = (el.innerText || el.textContent || '').trim();
          return t;
        }

        function collectFromRoot(root) {
          const list = [];
          if (root instanceof Element && root.matches(targetSel)) list.push(root);
          if (root instanceof Element) {
            list.push(...root.querySelectorAll(targetSel));
          } else if (root === document) {
            list.push(...document.querySelectorAll(targetSel));
          }
          return list;
        }

        function handleElements(els) {
          for (const el of els) {
            const text = getText(el);
            if (text && !seen.has(text)) {
              seen.add(text);
              // @ts-ignore
              window.nodeInsertFlash(text);
            }
          }
        }

        // iframe 初始扫描
        handleElements(collectFromRoot(document));

        const observer = new MutationObserver((mutations) => {
          for (const m of mutations) {
            if (m.type === 'childList') {
              m.addedNodes.forEach((n) => {
                handleElements(collectFromRoot(n));
              });
            } else if (m.type === 'characterData') {
              const el = m.target && m.target.parentElement
                ? m.target.parentElement.closest('.flash-text, .right-content_intro')
                : null;
              if (el) {
                if (!importantOnly || el.closest('.is-important')) handleElements([el]);
              }
            } else if (m.type === 'attributes') {
              const el = m.target instanceof Element ? m.target : null;
              if (el) {
                if (el.matches(targetSel)) handleElements([el]);
                else handleElements(el.querySelectorAll(targetSel));
              }
            }
          }
        });

        observer.observe(document.documentElement || document.body, {
          childList: true,
          subtree: true,
          characterData: true,
          attributes: true,
        });

        console.log('已在 iframe 中安装 .flash-text 观察器');
      }, importantOnly);
    } catch (_) {}
  }

  // 监听后续挂载的 iframe
  page.on('frameattached', async (frame) => {
    try {
      await frame.evaluate((importantOnly) => {
        if (window.__FLASH_OBS_ATTACHED__) {
          console.log('新挂载 iframe 已有观察器，跳过');
          return;
        }
        window.__FLASH_OBS_ATTACHED__ = true;
        const seen = new Set();
        const targetSel = importantOnly
          ? '.is-important .flash-text, .is-important .right-content_intro'
          : '.flash-text, .right-content_intro';

        function getText(el) {
          const t = (el.innerText || el.textContent || '').trim();
          return t;
        }

        function collectFromRoot(root) {
          const list = [];
          if (root instanceof Element && root.matches(targetSel)) list.push(root);
          if (root instanceof Element) {
            list.push(...root.querySelectorAll(targetSel));
          } else if (root === document) {
            list.push(...document.querySelectorAll(targetSel));
          }
          return list;
        }

        function handleElements(els) {
          for (const el of els) {
            const text = getText(el);
            if (text && !seen.has(text)) {
              seen.add(text);
              // @ts-ignore
              window.nodeInsertFlash(text);
            }
          }
        }

        // iframe 初始扫描
        handleElements(collectFromRoot(document));

        const observer = new MutationObserver((mutations) => {
          for (const m of mutations) {
            if (m.type === 'childList') {
              m.addedNodes.forEach((n) => {
                handleElements(collectFromRoot(n));
              });
            } else if (m.type === 'characterData') {
              const el = m.target && m.target.parentElement
                ? m.target.parentElement.closest('.flash-text, .right-content_intro')
                : null;
              if (el) {
                if (!importantOnly || el.closest('.is-important')) handleElements([el]);
              }
            } else if (m.type === 'attributes') {
              const el = m.target instanceof Element ? m.target : null;
              if (el) {
                if (el.matches(targetSel)) handleElements([el]);
                else handleElements(el.querySelectorAll(targetSel));
              }
            }
          }
        });

        observer.observe(document.documentElement || document.body, {
          childList: true,
          subtree: true,
          characterData: true,
          attributes: true,
        });

        console.log('已在新挂载的 iframe 中安装 .flash-text 观察器');
      }, importantOnly);
    } catch (_) {}
  });

  console.log('爬虫已启动。按 Ctrl+C 结束。');

  // 保持进程无限期运行
  // eslint-disable-next-line no-constant-condition
  while (true) {
    await new Promise((r) => setTimeout(r, 60_000));
  }
}

start().catch(async (err) => {
  console.error('Fatal error:', err);
  try { if (browser) await browser.close(); } catch (_) {}
  try { if (pool) await pool.end(); } catch (_) {}
  process.exit(1);
});

// 平滑关闭
process.on('SIGINT', async () => {
  console.log('\nShutting down...');
  try { if (browser) await browser.close(); } catch (_) {}
  try {
    if (pool) await pool.end();
    console.log('MySQL pool closed.');
  } catch (_) {}
  process.exit(0);
});
