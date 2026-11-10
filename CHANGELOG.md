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

## v0.6.2-rc1 — 2026-11-10

- 从此前工作簿恢复 619 条交易所历史保证金样本，覆盖 87 个期货品种；同时录入先锋期货官网 2026-03-20 公布的 87 条品种级公司历史保证金率。
- 默认主力合约视图展示历史率、来源日期、历史率×当前结算价的一手情景金额；同合约快照优先，缺失时回退同品种历史众数并标注范围。
- 未核验的当日交易所或公司保证金继续显示待核，不得用旧日期冒充实时结算值。

## v0.5.1 — 2026-11-10

- 修复 Windows `启动工作台.bat` 启动后打开两个相同工作台页面的问题：移除额外 PowerShell 浏览器调用，只让 Streamlit 自动打开一次（`--server.headless false`）。
- 增加启动脚本离线回归测试，保持行情与手续费计算代码不变。


## v0.6.1-rc1 — 2026-11-10

- 郑商所官方合约参考、按交易日严格筛选的大商所第三方保证金参考备用路线；不冒充交易所结算保证金。
- 根据先锋 2026-03-09 公告为部分品种增加独立的**历史公告加点情景估算**，明确与公司当日实际保证金分列。
- 新增同一交易日、逐合约的公司默认保证金核验 CSV 导入与数据源标注；以前的公司覆盖项继续保留但标示未按日核验。
- 新增离线测试和大商所免费官方门户 API 申请说明。

## v0.5.0 — 2026-11-09

- 主力合约日报：按同一结算日的最大持仓量选择具体可交易合约。
- CNEquity 免费逐合约行情本地采集与缺口诊断（需在实际网络环境验证）。
- 引入先锋期货 2026-11-02 默认手续费基准，计算开仓、平昨参考、平今核验及双边保障基金。
- 保留全合约筛选、客户端成交价/手数速算、HTML 和 CSV 导出。
- 建立私有 GitHub 仓库准备结构、自动化离线测试、忽略本地数据与账户配置。

> 版本标签代表代码版本，不代表交易所参数或公司费率当天有效。
