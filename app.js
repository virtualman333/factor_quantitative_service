'use strict';
const path = require('path');
const mysql = require('mysql2/promise');

module.exports = app => {
    async function initOkxApi() {
        const {OkxV5Api } = await import('okx-v5-api');
        // 这里初始化 OKX API（例如创建实例）
        return new OkxV5Api({
            apiBaseUrl: 'https://www.okx.com/',
            profileConfig: {
                apiKey: app.config.okxAccount.apiKey,
                secretKey: app.config.okxAccount.secretKey,
                passPhrase: app.config.okxAccount.apiPass,
            }
        });
    }
    async function initBianceApi() {
        const {MainClient } = await import('binance');
        return new MainClient({
            api_key:app.config.bianceAccount.apiKey ,
            api_secret: app.config.bianceAccount.secretKey,
            // Connect to testnet environment
            // testnet: true,
        })
    }
    app.beforeStart(async () => {
        // MySQL 连接参数（默认按你的要求）
        const MYSQL_HOST = process.env.DB_HOST || process.env.MYSQL_HOST || '47.119.132.60';
        const MYSQL_PORT = Number(process.env.DB_PORT || process.env.MYSQL_PORT || 3306);
        const MYSQL_USER = process.env.DB_USER || process.env.MYSQL_USER || 'intelligenceAutoTrade';
        const MYSQL_PASSWORD = process.env.DB_PASS || process.env.MYSQL_PASSWORD || 'intelligenceAutoTrade';
        const MYSQL_DATABASE = process.env.DB_NAME || process.env.MYSQL_DATABASE || 'intelligenceautotrade';

        app.coreLogger.info('[db] using mysql at %s:%s/%s', MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE);

        let pool;
        try {
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
        } catch (err) {
            app.coreLogger.error('[db] create pool error: %s', err && err.message ? err.message : err);
            throw err;
        }

        // 暴露到 app 与 ctx
        app.db = pool;
        app.context.db = pool;

        // 确保表存在（与爬虫一致）
        try {
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
        } catch (err) {
            app.coreLogger.error('[db] create table error: %s', err && err.message ? err.message : err);
            throw err;
        }
        // okxClient 初始化
        // initOkxApi().then(okxClient => {
        //     app.okxClient = okxClient;
        // });

        initBianceApi().then(bianceClient => {
            app.bianceClient = bianceClient;
        })
    });

    app.beforeClose(async () => {
        if (app.db) {
            try {
                await app.db.end();
            } catch (_) {}
        }
    });
};
