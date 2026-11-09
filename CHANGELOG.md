# Changelog

## [0.6.0-rc1] - 2026-11-09

- Prefer incremental derivatives daily update after initial small-window backfill; retain manual short-window repair without bypassing upstream limits.
- Distinguish CNEquity futures-bar capture failures from independent derivates quality-gate results (including unverified exits).
- Show per-exchange/day data counts, latest dates, upstream provenance and missing/zero open-interest counts; preserve DCE Sina coverage warning.
- Add six-market, exact-trade-day, contract-level exchange margin CSV import with source attribution. Prevent reusing old manual exchange margins on the next trading day.
- Add reviewed default-account close-today fee CSV import with effective date, verified date, provenance and explicit free-fee support; without evidence, close-today amount and intraday round-trip stay unquoted.
- Extend Streamlit UI/exports with margin source, fee validation status and imported parameters. No client-specific account identifiers or credentials are stored.
- Offline regression expanded to 19 tests; live exchange accessibility and broker account pricing **not verified**.

# 版本记录（Changelog）

## v0.5.0 — 2026-11-09

- 主力合约日报：按同一结算日的最大持仓量选择具体可交易合约。
- CNEquity 免费逐合约行情本地采集与缺口诊断（需在实际网络环境验证）。
- 引入先锋期货 2026-11-02 默认手续费基准，计算开仓、平昨参考、平今核验及双边保障基金。
- 保留全合约筛选、客户端成交价/手数速算、HTML 和 CSV 导出。
- 建立私有 GitHub 仓库准备结构、自动化离线测试、忽略本地数据与账户配置。

> 版本标签代表代码版本，不代表交易所参数或公司费率当天有效。
