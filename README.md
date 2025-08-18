# Jin10.com 实时快讯爬虫（Node.js + Puppeteer + MySQL）

一个尽量简单的 Node.js 项目，用 Puppeteer 抓取 `https://www.jin10.com/` 页面中所有 `class="flash-text"` 的内容（包含后续实时更新），并保存到远程 MySQL 数据库（可通过环境变量配置连接）。

## 目录结构

- `scripts/jin10/index.js` 主程序（Puppeteer + MutationObserver + MySQL）
- `package.json` 依赖与脚本
- `.gitignore` 忽略常见本地文件

## 运行要求

- Node.js >= 18（建议 18+）
- Windows/ macOS/ Linux 均可

## Python代码执行方法
- 按requirements.txt安装依赖
- pip install