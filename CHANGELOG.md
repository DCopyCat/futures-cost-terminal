# Changelog

## v0.6.6-rc1 — 2026-11-13

- Added the four CZCE SO sunflower-oil futures launch contracts (SO2705/2707/2709/2711); 20 tonnes/lot, RMB 1/ton tick, RMB 20/tick; exchange launch margin reference 8%, launch day bands ±7% (first day ±14%).
- Source-backed official listing open / ordinary close / close-today exchange fee one ten-thousandth. Exchange fee is never copied into the broker default; SO remains broker fee and broker margin pending until Pioneer confirms.
- SO visible in offline listing/catalogues even without CNEquity market data; no fabricated settlement price, OI, or continuous contract. Existing 88-product 2026-11-02 broker PDF unchanged.
- Unit tests for effective date, proper contract size, 4-contract scope, official fee calculation and no pre-launch backfilling.


## [0.6.0-rc1] - 2026-11-09

- Prefer incremental derivatives daily update after initial small-window backfill; retain manual short-window repair without bypassing upstream limits.
- Distinguish CNEquity futures-bar capture failures from independent derivates quality-gate results (including unverified exits).
- Show per-exchange/day data counts, latest dates, upstream provenance and missing/zero open-interest counts; preserve DCE Sina coverage warning.
- Add six-market, exact-trade-day, contract-level exchange margin CSV import with source attribution. Prevent reusing old manual exchange margins on the next trading day.
- Add reviewed default-account close-today fee CSV import with effective date, verified date, provenance and explicit free-fee support; without evidence, close-today amount and intraday round-trip stay unquoted.
- Extend Streamlit UI/exports with margin source, fee validation status and imported parameters. No client-specific account identifiers or credentials are stored.
- Offline regression expanded to 19 tests; live exchange accessibility and broker account pricing **not verified**.

# 版本记录（Changelog）

## v0.6.5-rc1 — 2026-11-11

- 新增六市场逐合约交易所开仓/平昨/平今费率第三方参考（AKShare futures_comm_info）、独立日期缓存与免费刷新。
- 在主力合约首页并排展示交易所开仓参考费、先锋默认费、理论毛差、倍数，导出HTML/CSV同步；特殊合约严格匹配，0费率及过期来源必须注明。
- 交易所第三方参考不是核实的官方结算费，毛差不是公司利润；新增日期与计费单位回归测试。

## v0.6.4-rc1 — 2026-11-11

- 核对先锋2026-11-02版PDF共88条收费标准；与现有 data/company_fees.csv 逐行一致（无臆造的更新）。
- 主力合约首页新增高亮“★先锋默认手续费/手（PDF）”、收费规则及PDF更新日期；区别于已有账户本地覆盖费率。
- HTML/CSV同步增加收费字段、日期和来源；88品种离线收费速查与CSV导出。
- 不推定平今手续费，保障基金仍单列；新增回归测试。
  
## v0.6.3-rc1 — 2026-11-10

- 修复主力合约 HTML/Streamlit 首页保证金仍为横杠的显示问题：缺少当日核验值时，直接在前排展示带历史日期标记的旧档费率和一手情景估算。
- 增加可审计来源和版本号，保持原始核验字段不变；静态导出文件需要重新生成。
- 增加自动化回归测试覆盖豆一历史参考回退、当日参数优先、旧手工值标记和导出视图。

## v0.6.2-rc2 — 2026-11-10

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

- 在工作台首页内置离线87品种历史保证金参考总览与CSV导出，独立于行情更新成功与否。
