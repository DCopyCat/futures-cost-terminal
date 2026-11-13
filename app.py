"""Windows / local dashboard. Start with: streamlit run app.py"""
from __future__ import annotations

import csv
import io
import traceback
from pathlib import Path
from datetime import datetime
import streamlit as st

from core import DATA, BASE, MARKETS, TZ, _load_csv, generate, save_report, package_report, _fee_value
from cne_runner import refresh_daily, CNE_CONFIG, CNE_DATA, LOG_DIR
from cne_provider import CNEquityFuturesAPI
from fee_pdf import parse_company_fee_pdf, fee_diff, install_fee_pdf
from company_fee_view import format_company_fee_rule
from exchange_fee_provider import (refresh_from_akshare, load_snapshot, variety_catalog,
                                   SNAPSHOT_NAME, SOURCE_NAME)
from parameter_import import (parse_exchange_margin_csv, install_exchange_margin_csv,
                              parse_company_close_today_csv, merge_company_close_today_csv,
                              parse_company_margin_csv, install_company_margin_csv)


# Local override files must never be committed to GitHub. Initialize blank
# schema-only files on first launch; never overwrite a user's local changes.
def _ensure_local_overrides():
    DATA.mkdir(parents=True, exist_ok=True)
    for name in ('company_overrides', 'exchange_overrides'):
        target = DATA / f'{name}.csv'
        example = BASE / 'templates' / f'{name}.example.csv'
        if not target.exists():
            target.write_bytes(example.read_bytes())

_ensure_local_overrides()

st.set_page_config(page_title="Futures Cost Terminal", page_icon="📊", layout="wide")
st.markdown('''<style>div.block-container{padding-top:2rem;max-width:1500px}h1{letter-spacing:-.5px}
[data-testid="stMetricValue"]{font-weight:700} .stButton button[kind="primary"]{border-radius:10px;height:3.1rem}</style>''', unsafe_allow_html=True)
st.title("期货每日结算成本工作台")
_BUILD_VERSION = (BASE/'VERSION').read_text(encoding='utf-8').strip() if (BASE/'VERSION').exists() else 'unknown'
_FEE_DATES = sorted({str(x.get('effective_from','')) for x in _load_csv(DATA/'company_fees.csv') if x.get('effective_from')})
_FEE_VERSION = _FEE_DATES[-1] if _FEE_DATES else '未知'
_EXCHANGE_FEE_PATH = DATA / SNAPSHOT_NAME
st.caption(f"软件版本 {_BUILD_VERSION} ｜ CNEquity 六市场具体主力 × 先锋默认手续费PDF（已保存 {_FEE_VERSION}）｜账户实际费率需核实")

tab1, tab2, tab3 = st.tabs(["📈 生成日报", "⚙️ 公司参数维护", "📚 使用边界与来源"])

with tab1:
    a,b,c = st.columns([1.3,1,1])
    with a:
        st.info("点击生成将先用 CNEquity 采集免费逐合约数据，再按最近完整交易日计算。夜盘计入所属交易日，不按自然日混算。")
    with b:
        strict = st.checkbox("仅允许六市场齐全时生成", value=False)
    with c:
        fund = st.number_input("保障基金：亿分之", min_value=0.0, max_value=1000.0, value=9.0, step=1.0,
                               help="依据先锋期货2026-11-02更新PDF：成交金额的亿分之九。与公司最新通知核对")
    with st.expander('🌻 SO葵花籽油：2026-11-12上市参数与四个首批合约（官方公告）',expanded=True):
        from so_listing import (listing_contract_rows, FIRST_DAY_REFERENCE_PRICE,
            MULTIPLIER as SO_MULTIPLIER, EXCHANGE_INITIAL_MARGIN_PCT as SO_MARGIN,
            EXCHANGE_FEE_PERMYRIAD as SO_FEE, FEE_ANNOUNCEMENT_URL,
            LISTING_ANNOUNCEMENT_URL)
        so_rows=listing_contract_rows()
        st.caption('郑商所正式上市资料：SO2705 / SO2707 / SO2709 / SO2711；20吨/手，最小跳动1元/吨、每跳20元；初始交易所保证金8%，一般开仓和平今手续费均为成交金额万分之1。11月12日上市初期涨跌停板7%（首日14%）。')
        st.dataframe([{
            '上市合约':r['contract'], '上市日':r['listed_at'],
            '交易单位':f"{r['multiplier']:g}吨/手",
            '每跳盈亏':f"{r['value_per_tick']:g}元/手",
            '交易所挂牌保证金':f"{r['exchange_margin_listing_pct']:g}%（挂牌参考）",
            '交易所开仓':f"万分之{r['exchange_open_fee_permyriad']:g}",
            '交易所平今':f"万分之{r['exchange_close_today_fee_permyriad']:g}",
            '先锋默认手续费':r['broker_default_fee_status'],
            '先锋公司保证金':r['broker_margin_status'],
        } for r in so_rows],hide_index=True,use_container_width=True)
        st.info(f'SO 挂牌基准价 {FIRST_DAY_REFERENCE_PRICE:,.0f} 元/吨的**演算**：名义价值 ¥{FIRST_DAY_REFERENCE_PRICE*SO_MULTIPLIER:,.0f}/手，交易所挂牌保证金参考 ¥{FIRST_DAY_REFERENCE_PRICE*SO_MULTIPLIER*SO_MARGIN/100:,.0f}/手，交易所开仓参考 ¥{FIRST_DAY_REFERENCE_PRICE*SO_MULTIPLIER*SO_FEE/10000:,.2f}/手。挂牌基准价不是2026-11-12的实际结算价。公司收费必须另行核实。')
        st.markdown(f'[郑商所上市公告（转载）]({LISTING_ANNOUNCEMENT_URL}) | [郑商所手续费正式通知]({FEE_ANNOUNCEMENT_URL})')
    with st.expander('📋 先锋期货开户默认手续费完整基准（离线可查）',expanded=False):
        all_company_fees = _load_csv(DATA/'company_fees.csv')
        versions = sorted({str(r.get('effective_from','')) for r in all_company_fees if r.get('effective_from')})
        current_fee_version = versions[-1] if versions else '未知'
        default_rows = [r for r in all_company_fees if r.get('effective_from') == current_fee_version]
        st.caption(f'已保存的先锋默认手续费 PDF：{current_fee_version}；含 {len(default_rows)} 条已核实旧品种。SO是2026-11-12新上市品种，未纳入此PDF，须另核公司收费。固定元/手或按成交金额比例收费，均不含保障基金。')
        fee_catalog = [{
            '交易所': MARKETS.get(r['exchange'],r['exchange']),
            '品种': r.get('variety_name',''), '代码': r['variety'],
            '★先锋开户默认单边收费规则': format_company_fee_rule(r.get('open_fee_type'),r.get('open_fee_value')),
            'PDF更新日期': r.get('effective_from','')
        } for r in default_rows]
        fee_catalog.append({
            '交易所':'郑商所','品种':'葵花籽油','代码':'so',
            '★先锋开户默认单边收费规则':'待核（SO 2026-11-12上市，旧PDF无此品种）',
            'PDF更新日期':'待核',
        })
        if fee_catalog:
            st.dataframe(fee_catalog,hide_index=True,use_container_width=True,height=350)
            buffer=io.StringIO(newline='')
            writer=csv.DictWriter(buffer,fieldnames=list(fee_catalog[0]),lineterminator='\n')
            writer.writeheader();writer.writerows(fee_catalog)
            st.download_button('↓ 下载先锋默认手续费88品种+SO待核清单CSV',
                               data=('\ufeff'+buffer.getvalue()).encode('utf-8'),
                               file_name='先锋开户默认手续费_'+current_fee_version+'.csv',
                               mime='text/csv')
        else:
            st.warning('没有已保存的先锋默认手续费表，请去“公司参数维护”导入最新 PDF。')
    with st.expander('⚖️ 六市场逐品种交易所参考手续费 vs 先锋默认手续费（离线可查）',expanded=True):
        st.caption('交易所数据来自 AKShare futures_comm_info → 九期网第三方逐合约参考，不是交易所核验结算单。固定元/手、按成交金额万分之计费，平今可能与开仓不同。公司默认收费不是客户账户费率。')
        if st.button('⟳ 更新六市场交易所手续费参考（联网）',key='refresh_exchange_fee_ref'):
            try:
                stats=refresh_from_akshare(_EXCHANGE_FEE_PATH)
                st.success(f"参考数据已更新：{stats['contracts']} 合约、{stats['varieties']} 品种；费率源更新日期 {stats['updated_min']} 至 {stats['updated_max']}。")
            except Exception as err:
                st.warning('第三方数据更新失败（不清除已有缓存）：'+str(err)[:280])
        exchange_fee_rows=load_snapshot(_EXCHANGE_FEE_PATH)
        st.write(f'本机有第三方手续费参考：{len(exchange_fee_rows)} 个具体合约；如未联网成功，使用2026-11-10历史快照；实时接口：{SOURCE_NAME}')
        _broker_rows=_load_csv(DATA/'company_fees.csv')
        _version=max((r.get('effective_from','') for r in _broker_rows),default='')
        _broker_rows=[r for r in _broker_rows if r.get('effective_from','')==_version]
        if not any(r.get('exchange')=='CZCE' and r.get('variety')=='so' for r in _broker_rows):
            _broker_rows.append({'exchange':'CZCE','variety':'so','variety_name':'葵花籽油',
                                 'open_fee_type':'','open_fee_value':'','effective_from':'待核'})
        _cat=variety_catalog(exchange_fee_rows,_broker_rows)
        _catalog=[{
            '交易所':MARKETS.get(c['exchange'],c['exchange']),
            '品种':c['variety_name'],'代码':c['variety'],
            '交易所开仓参考规则':c['exchange_open_rule'],
            '第三方费率更新':c['exchange_fee_update'] or '待核',
            '覆盖合约数':c['reference_contracts'],
            '先锋默认收费规则':format_company_fee_rule(c['broker_default_type'],c['broker_default_value']),
            '先锋PDF日期':c['broker_date'],
        } for c in _cat]
        if _catalog:
            st.dataframe(_catalog,hide_index=True,use_container_width=True,height=390)
            buf=io.StringIO(newline='')
            writer=csv.DictWriter(buf,fieldnames=list(_catalog[0]),lineterminator='\n')
            writer.writeheader();writer.writerows(_catalog)
            st.download_button('↓ 下载六市场交易所与先锋默认手续费参考对照CSV',
                data=('\ufeff'+buf.getvalue()).encode('utf-8'),
                file_name='exchange_vs_broker_fee_reference.csv',mime='text/csv')
        st.caption('如果某品种不同合约适用不同费率，以上只提示差异；真正金额必须在主力合约日报用该具体合约的结算价换算。没有获取到的品种保持待核，绝不拿其他合约或交易所费率填补。')
    with st.expander('大商所自动保证金与结算价：Tushare 授权接入（可选）'):
        st.caption('CNEquity 对大商所期货默认使用免费的新浪补充行情，部分无成交合约可能缺失。Tushare 仅作为可选备用，非默认，也不是免费保证金源。')
        token=st.text_input('Tushare Token（仅保留在当前浏览器会话中，不写入日报）',type='password',key='tushare_token')
        st.caption('有 Token 不等于有权限。无授权时可尝试带日期的免费第三方参考数据，但不等于已核验交易所保证金。')
        st.caption('大商所官方对外门户 API 自 2025-12 开放，注册用户可申请免费接入业务参数；需在官网「数据服务 → 数据工具 → API服务」申请并获取官方接口文档后才能配置正式对接。')
    with st.expander('CNEquity 免费数据源检查 / 上次失败日志'):
        st.caption('CNEquity 不是在线现成 API，第一次需要在本机建立独立期货湖。工具自动创建配置；不会初始化整套 A 股。')
        st.write('独立期货配置：',str(CNE_CONFIG))
        st.write('本地 Parquet 数据：',str(CNE_DATA))
        log=LOG_DIR/'cne_last_run.json'
        if log.exists():
            import json
            try:
                last=json.loads(log.read_text(encoding='utf-8'))
                st.write('上一次采集状态：',last.get('status','未知'))
                st.write('采集模式：',last.get('capture_mode','未知'))
                st.write('采集退出码：',last.get('capture_exit_codes',[]),' | 数据完整性审计退出码：',last.get('quality_gate_exit_code'))
                st.json({'采集前本地湖':last.get('lake_before',{}).get('by_exchange',{}),
                         '采集后本地湖':last.get('lake_after',{}).get('by_exchange',{})})
                st.caption('完整性审计：0 表示检查通过；1 表示检测到缺口；2 表示证据不足。采集已写入数据与合约完整性是两回事。')
                for i,step in enumerate(last.get('steps',[])):
                    st.write(f"第 {i+1} 步：退出码 {step.get('exit_code')}；{' '.join(step.get('args',[])[:4])}")
                    st.code(str(step.get('output',''))[-2300:] or '无日志输出',language='text')
            except Exception as exc:
                st.error('日志读取失败：'+str(exc))
            st.download_button('下载 CNEquity 本地采集日志',data=log.read_bytes(),file_name='cne_last_run.json',mime='application/json')
        else:
            st.caption('本机尚无采集日志，第一次生成日报后在这里查看。')
        st.caption('HTTP 403/412、官网限流或新浪合约覆盖不足无法由此工具强行绕过；只显示真实已采集数据。')
    include_dce=st.checkbox('同时采集大商所免费逐合约行情（首次可能涉及大量上游请求）',value=True,
                            help='CNEquity 的 DCE 新浪路由首次可能枚举数百个具体合约；取消勾选可先生成五市场报告，大商所会显示缺失。')
    force_repair=st.checkbox('手动补采最近 8 日行情（故障修复专用，日常不勾选）',value=False,
                             help='正常每天应当执行增量日更。仅在明显缺漏且上游允许重试时使用补采，不能绕过限流。')
    col_run, col_demo = st.columns([2,1])
    with col_run:
        trigger_real=st.button('⟳ 免费更新并生成真实日报（CNEquity）',type='primary',use_container_width=True)
    with col_demo:
        trigger_demo=st.button('查看演示效果（虚构数据）',use_container_width=True)
    if trigger_real:
        with st.spinner('正在按 CNEquity 官方 CLI 采集六交易所的逐合约行情；被限流的市场会保留明确诊断……'):
            try:
                with st.status('CNEquity 正在采集…',expanded=True) as run_status:
                    update = refresh_daily(include_dce=include_dce,force_backfill=force_repair,progress=lambda msg:st.write(msg))
                    run_status.update(label='本次 CNEquity 采集步骤已结束，开始计算报告',state='complete')
                st.session_state['cn_update']=update
                if update.get('capture_exit_codes') and any(c!=0 for c in update['capture_exit_codes']):
                    st.warning('CNEquity 采集存在失败或降级：仍会尝试读取本地已发布行情。报告日期及缺失交易所必须自行核对。')
                # Independent fee source; its outage must not block real price reports.
                if (not _EXCHANGE_FEE_PATH.exists() or
                    datetime.fromtimestamp(_EXCHANGE_FEE_PATH.stat().st_mtime,TZ).date() < datetime.now(TZ).date()):
                    try:
                        refreshed=refresh_from_akshare(_EXCHANGE_FEE_PATH)
                        st.info(f"交易所手续费参考更新：{refreshed['contracts']} 个具体合约，{refreshed['varieties']} 个品种。")
                    except Exception as fee_error:
                        st.warning('交易所手续费参考刷新失败，仍可生成日报；参考列沿用有日期缓存或待核：'+str(fee_error)[:230])
                api = CNEquityFuturesAPI(CNE_CONFIG)
                report = generate(api, fund_per_100m=fund, require_complete=strict,
                                  tushare_token=token)
                report['cn_equity_update_status']=update['status']
                report['cn_equity_quality_gate_exit_code']=update.get('quality_gate_exit_code')
                report['cn_equity_update_steps']=[{'command':' '.join(s['args'][:4]),'exit_code':s['exit_code']} for s in update['steps']]
                if update.get('capture_exit_codes') and any(c!=0 for c in update['capture_exit_codes']):
                    report['status']='CNEquity 采集有降级（需核实日期和合约覆盖）'
                if update.get('quality_gate_exit_code') not in (None,0):
                    report['status'] += '；数据完整性证据不足/缺口（不可视为全量）'
                directory, bundle=save_report(report)
                st.session_state['report']=report
                st.session_state['bundle']=bundle
                st.session_state['directory']=directory
                st.session_state['is_demo']=False
                st.session_state.pop('failure',None)
                st.success(f"已生成本地已发布数据报告：{report['price_date']}；主力 {len(report['main_records'])} 条、全合约 {len(report['records'])} 条。请核对源端完整性和日期。")
            except Exception as ex:
                message=f"{type(ex).__name__}: {ex}"
                st.session_state['failure']=message
                # The trace is local; no Token or user data is included in our own messages.
                log_dir=BASE/'logs'; log_dir.mkdir(exist_ok=True)
                (log_dir/'last_error.txt').write_text(message+'\n\n'+traceback.format_exc(),encoding='utf-8')
                st.error('未能获取可用的 CNEquity 已发布行情。下面显示具体诊断，绝不使用演示数据冒充真实报价。')
                st.code(message,language='text')
                if st.session_state.get('cn_update'):
                    st.json({'采集状态':st.session_state['cn_update']['status'],
                         '采集退出码':st.session_state['cn_update'].get('capture_exit_codes'),
                         '数据完整性状态':st.session_state['cn_update'].get('quality_gate_exit_code')})
    if trigger_demo:
        from demo_api import DemoAPI
        report=generate(DemoAPI(),now=datetime.now(TZ),fund_per_100m=fund)
        report['status']='模拟数据 · 非真实行情'
        report['company_baseline']='演示数据（仅测试界面，绝对不可对客）'
        bundle,_=package_report(report)
        st.session_state['report']=report
        st.session_state['bundle']=bundle
        st.session_state['directory']='仅在当前浏览器展示演示，未写入真实报告目录'
        st.session_state['is_demo']=True
        st.success('已打开可查看的演示报告。价格和持仓量均为虚构。')
    if st.session_state.get('failure') and not trigger_real and not trigger_demo:
        st.error('上一次真实报告未生成：'+st.session_state['failure'][:800])
    if 'report' in st.session_state:
        report = st.session_state['report']
        if st.session_state.get('is_demo'):
            st.warning('⚠️ 当前为演示模式：所有价格、持仓量、结算日展示均来自程序内置测试数据，不是真实交易所数据，禁止对客。')
        else:
            st.info('已生成真实数据采集报告。请继续核查缺失交易所、保证金与公司账户参数，再决定是否用于沟通。')
        metrics = st.columns(5)
        for col,label,value in zip(metrics,['行情结算日','行情状态','有效期货合约','具体主力合约','待核记录'],[
            report['price_date'],report['status'],len(report['records']),len(report['main_records']),
            sum(r['data_status']=='待核' for r in report['records'])]):
            col.metric(label,value)
        if report.get('unresolved_main'):
            st.warning(f"有 {len(report['unresolved_main'])} 个品种的持仓量缺失/为零，不能可靠认定具体主力；已在主力视图中排除，请去全合约查询核验。")
        if report.get('suspected_stale'):
            st.error(f"行情可能过期：结算日后已有约 {report.get('possible_workdays_without_new_data')} 个普通工作日。节假日需核实，禁止直接标成最新日报。")
        if report['missing_markets']:
            st.error('本次没有覆盖：'+', '.join(MARKETS[m] for m in report['missing_markets'])+'；**不能当作完整市场报告使用**。')
        if report.get('lagging_markets'):
            st.error('交易日错位：以下市场已有更晚日行情，但本报告的共同交易日更早：'+
                ', '.join(MARKETS[m] for m in report['lagging_markets'])+ '。请勿将此报告当成最新结算日。')
        changes = report.get('changes',{})
        if changes.get('previous_price_date'):
            st.markdown(f"**与前次日报 {changes['previous_price_date']} 的变动对比**")
            st.caption(changes.get('message',''))
            if changes.get('events'):
                st.dataframe(changes['events'],hide_index=True,use_container_width=True,height=220)
            else:
                st.success('与此前保存的报告相比，未发现已覆盖字段的费率规则、保证金率或主力候选变化。')
        else:
            st.caption('首次生成：没有更早的本地日报，暂不显示日变化。')
        if report['params_errors'] or report['daily_errors']:
            with st.expander('数据源诊断与缺口（展开可查看原因）',expanded=bool(report['missing_markets'])):
                st.json({'行情获取问题':report['daily_errors'], '结算参数问题':report['params_errors'],
                         '大商所行情来源':report.get('dce_daily_source'),
                         '大商所保证金来源':report.get('dce_margin_source'),
                         '各市场最新行情交易日':report.get('market_latest_dates'),
                         'CNEquity本地数据质量':report.get('cn_equity_source_quality'),
                         'CNEquity更新结果':report.get('cn_equity_update_status'),
                         '完整性审计退出码':report.get('cn_equity_quality_gate_exit_code')})
        selected_market = st.multiselect('交易所',list(MARKETS),default=list(MARKETS),format_func=lambda x:MARKETS[x])
        view_mode = st.radio('显示范围',['具体主力合约（默认）','全部合约（核验用）'],index=0,horizontal=True)
        only_main = view_mode.startswith('具体主力')
        keyword = st.text_input('合约/品种搜索',placeholder='rb / 豆粕 / lc2701 / IF')
        rows = report['main_records'] if only_main else report['records']
        rows = [r for r in rows if r['exchange'] in selected_market and (not keyword or keyword.lower() in (r['contract']+r['variety_name']+r['variety']).lower())]
        st.markdown('#### 逐合约收费对照：交易所开仓参考｜先锋默认｜毛差｜倍数')
        st.info('**SO葵花籽油已按郑商所2026-11-12首批四个合约接入**，交易所挂牌费率采用郑商所正式通知，上市保证金8%作带日期参考；公司费率、公司保证金待核。其余品种按第三方参考比对。**新增：交易所逐合约开仓、平昨、平今参考手续费**，直接放在先锋默认手续费旁，并计算每手理论毛差及收费倍数。两者都用同一结算价换算。交易所为第三方参考、先锋为开户默认，两者不等同客户真实收费；毛差不等同利润。')
        st.warning('【历史参考补齐】交易所历史数据为 2026年7–8月旧档；先锋公司历史公开基准为2026年3月20日发布。旧保证金率与报告日结算价相乘的金额仅是情景估算，不是今天交易所或公司实际保证金。请以结算单/交易所及公司当日核定值为准。')
        st.caption(f'开仓默认收费参考先锋 {_FEE_VERSION} PDF；平昨仅按同一默认单边费率假设，需向公司核实。平今没有经确认的单独标准时显示「待核」，不能等同开仓费；往返费用包含两次成交的保障基金。')
        show_fields = [
          ('exchange_name','交易所'), ('variety_name','品种'), ('contract','具体主力合约'),
          ('settlement','结算价'),
          ('exchange_fee_reference_display','交易所开仓/手（第三方参考）'),
          ('company_default_fee_display','★先锋默认手续费/手（PDF）'),
          ('broker_minus_exchange_display','先锋-交易所参考毛差/手'),
          ('broker_over_exchange_display','先锋/交易所参考倍数'),
          ('exchange_fee_reference_close_yesterday','交易所平昨/手（参考）'),
          ('exchange_fee_reference_close_today','交易所平今/手（参考）'),
          ('exchange_fee_reference_status','交易所费更新日期/口径'),
          ('company_default_fee_rule','先锋默认收费规则'),
          ('company_default_fee_version','PDF更新日期'),
          ('display_exchange_margin_long_pct','展示交易所保证金率（含历史）'),
          ('display_exchange_margin_one_lot','展示交易所一手保证金（含历史）'),
          ('display_company_margin_long_pct','展示公司保证金率（含历史）'),
          ('display_company_margin_one_lot','展示公司一手保证金（含历史）'),
          ('display_exchange_margin_status','交易所保证金口径'),
          ('display_company_margin_status','公司保证金口径'),
          ('company_fee_open','开仓/手（含本地覆盖）'),
          ('company_fee_close_yesterday','平昨/手*'), ('company_fee_close_today','平今/手'),
          ('company_fee_open_plus_fund','开仓含基金'),
          ('company_fee_close_yesterday_plus_fund','平昨含基金'),
          ('company_fee_close_today_plus_fund','平今含基金'),
          ('overnight_round_trip_plus_fund','隔夜开平双边含基金*'),
          ('day_round_trip_plus_fund','日内开平双边含基金'),
          ('historical_exchange_basis','交易所旧档日期/口径'),
          ('historical_company_basis','先锋历史公司来源日期'),
          ('company_margin_one_lot','当前公司录入一手保证金（未录为空）'),
          ('exchange_margin_reference_long_pct','公开保证金参考率%*'),
          ('exchange_margin_reference_one_lot','公开参考一手保证金*'),
          ('company_margin_notice_reference_long_pct','先锋公告推算公司参考率%*'),
          ('company_margin_notice_reference_one_lot','先锋公告推算一手资金*'),
          ('margin_reference_source','公开参考来源'),
          ('company_margin_source','公司保证金核验来源'),
          ('exchange_margin_long_pct','交易所多头保证金%'),
          ('exchange_margin_short_pct','交易所空头保证金%'),
          ('margin_source','保证金来源'),
          ('company_close_today_verified','平今核验状态'),
          ('fee_status','手续费口径'), ('data_status','核验状态')]
        fee_fields = {'company_fee_open','company_fee_close_yesterday','company_fee_close_today',
                      'company_fee_open_plus_fund','company_fee_close_yesterday_plus_fund',
                      'company_fee_close_today_plus_fund','overnight_round_trip_plus_fund',
                      'day_round_trip_plus_fund'}
        verified_fields = fee_fields | {'company_margin_one_lot','exchange_margin_long_pct',
                                        'exchange_margin_short_pct','company_margin_long_pct',
                                        'company_margin_short_pct'}
        view = [{label:('待核' if k in verified_fields and r.get(k) is None else r.get(k))
                 for k,label in show_fields} for r in rows]
        if not view:
            st.warning('当前筛选下没有可展示的合约。请切换「全部合约」、取消搜索筛选或展开数据源诊断。')
        st.dataframe(view, use_container_width=True, hide_index=True, height=580)
        st.caption(f'交易所费参考源：AKShare futures_comm_info/九期网，单边开仓/平昨/平今对应的同合约第三方口径；毛差与倍数仅供分析，不可当公司净利润。先锋开户默认费来自 {_FEE_VERSION} PDF，不含保障基金，按结算价估算；账户覆盖值在后续“开仓/手”列。最前面的“展示保证金”四列依次选择当日报表参数→公开参考→历史旧档；每个数字自带状态或旧档日期。正式当日核验字段不被覆盖。历史资料：交易所2026年7–8月、先锋公司公开参数2026年3月；金额仅为情景估算，不能直接对客。')
        st.caption('* 平昨参考值仅为同默认单边费率假设；不保证实际平昨费率相同。表中所有费用为**每一手**、假设开平都在相同结算价成交；账户差异化费率以实际交易结算单为准。')
        with st.expander('按客户实际成交价模拟开仓/平仓成本（不录入客户信息）'):
            if rows:
                choices={f"{r['exchange_name']} · {r['variety_name']} · {r['contract']}":r for r in rows}
                selected=choices[st.selectbox('选择具体合约',list(choices),key='fee_calc_sym')]
                k1,k2,k3=st.columns(3)
                with k1: open_price=st.number_input('模拟开仓成交价',min_value=0.000001,value=float(selected['settlement']),format='%.4f',key='fee_calc_open_'+selected['exchange']+'_'+selected['contract'])
                with k2: close_price=st.number_input('模拟平仓成交价',min_value=0.000001,value=float(selected['settlement']),format='%.4f',key='fee_calc_close_'+selected['exchange']+'_'+selected['contract'])
                with k3: lots=st.number_input('手数',min_value=1,value=1,step=1,key='fee_calc_lots')
                scenario=st.radio('平仓类型',['平昨','平今'],horizontal=True,key='fee_calc_scenario')
                multiplier=selected.get('multiplier')
                if multiplier is None or multiplier<=0:
                    st.warning('当前合约缺乘数，不能计算费用。')
                else:
                    open_n=open_price*multiplier
                    close_n=close_price*multiplier
                    open_fee=_fee_value(selected.get('company_fee_type'),selected.get('company_fee_rule'),open_n)
                    if scenario=='平今':
                        close_fee=(_fee_value(selected.get('company_close_today_fee_type'),selected.get('company_close_today_fee_rule'),close_n)
                                   if selected.get('company_fee_close_today') is not None else None)
                    else:
                        close_type=selected.get('company_close_yesterday_fee_type') or selected.get('company_fee_type')
                        close_rule=selected.get('company_close_yesterday_fee_rule')
                        if close_rule in (None,'') and not selected.get('company_close_yesterday_fee_type'):
                            close_rule=selected.get('company_fee_rule')
                        close_fee=_fee_value(close_type,close_rule,close_n)
                    fund_rate=report.get('fund_rate_per_100m',9)/1e8
                    fund_two=(open_n+close_n)*fund_rate
                    f1,f2,f3=st.columns(3)
                    f1.metric('开仓手续费(未含基金)',f'{open_fee*lots:,.4f} 元' if open_fee is not None else '待核')
                    f2.metric('平仓手续费(未含基金)',f'{close_fee*lots:,.4f} 元' if close_fee is not None else '待核')
                    f3.metric('开平合计(含双边基金)',f'{(open_fee+close_fee+fund_two)*lots:,.4f} 元' if open_fee is not None and close_fee is not None else '待核')
                    if scenario=='平今' and close_fee is None:
                        st.warning('没有经公司确认的平今手续费，不能计算日内完整开平成本。')
                    if scenario=='平昨' and not selected.get('company_close_yesterday_fee_type'):
                        st.warning('平昨暂按开户默认单边费率试算，不代表已确认客户平昨收费。')
                    st.caption('仅用输入的假设成交价重算手续费，不存储客户信息；交易账户实际收费以结算单为准。')
        from core import _html_report, _csv_bytes
        col_html,col_csv,col_zip=st.columns(3)
        suffix='_DEMO' if st.session_state.get('is_demo') else ''
        with col_html:
            st.download_button('↓ 直接下载日报网页',data=_html_report(report),
                file_name='期货成本日报_'+report['price_date']+suffix+'.html',mime='text/html',use_container_width=True)
        with col_csv:
            st.download_button('↓ 直接下载主力CSV',data=_csv_bytes(report['main_records']),
                file_name='期货主力合约_'+report['price_date']+suffix+'.csv',mime='text/csv',use_container_width=True)
        with col_zip:
            st.download_button('↓ 下载全部报告ZIP',data=st.session_state['bundle'],
                file_name='futures_cost_'+report['price_date'].replace('-','')+suffix+'.zip',
                mime='application/zip',use_container_width=True)
        st.caption('工作台本机保存位置：'+st.session_state['directory'])
        st.caption('交易所手续费参考来自 AKShare / 九期网，可能跨交易日且合约差异显著；比对列绝不代表真实客户佣金收入。手续费来源：先锋最新已保存开户默认 PDF；固定元/手或成交金额比例计费，客户账户实际收取及平今规则另核。行情来源：CNEquity 开源期货湖；交易所核验保证金：结算参数/同日核验 CSV；CZCE/DCE 免费备用仅供参考；先锋历史公告加点仅作情景估算；公司实际保证金：当日公司核验文件或核实的账户设置。')
    else:
        st.markdown('#### 当前尚未生成日报')
        st.info('点击「免费更新并生成真实日报」会初始化/更新独立 CNEquity 期货湖，再展示具体主力合约；首次需下载上游行情，若受限流，查看上方日志。演示按钮始终不联网。')
        st.markdown('#### 你将看到什么？')
        st.markdown('点击后默认显示具体主力合约的交易所开仓/平昨/平今第三方参考手续费、先锋默认手续费、理论毛差及倍数、保证金与开平成本；第三方未覆盖的具体合约仍标为待核。')

    with st.expander('查看本机以前保存的真实日报（无需重新联网）'):
        from core import OUT
        saved_reports=sorted(OUT.glob('*/futures_cost_*.html'),reverse=True)
        if not saved_reports:
            st.caption('尚未生成真实日报，因此 reports 文件夹里没有历史 HTML。软件刚启动时这是正常的。')
        else:
            prev=st.selectbox('选择历史结算日报',saved_reports,
                              format_func=lambda p:p.parent.name+' / '+p.name)
            st.download_button('↓ 下载这份已保存日报',data=prev.read_bytes(),
                              file_name=prev.name,mime='text/html')

    with st.expander('📚 87个期货品种历史保证金参考总览（无需联网）',expanded=True):
        st.caption('历史数据不是当天交易所/公司核定值：交易所源自2026年7—8月，先锋公司源自2026年3月20日官网日常品种基准。特殊合约或临近交割月可能提保。')
        from historical_margin import historical_catalog
        history = historical_catalog(DATA)
        product_names = {(str(p.get('exchange','')).upper(),str(p.get('variety','')).lower()):p.get('variety_name','')
                         for p in _load_csv(DATA/'contracts.csv')}
        display_history = [{
            '交易所': MARKETS.get(x['exchange'],x['exchange']),
            '品种': product_names.get((x['exchange'],x['variety']),x['variety']),
            '代码': x['variety'],
            '交易所旧档多%': x['exchange_long_pct'],
            '交易所旧档空%': x['exchange_short_pct'],
            '交易所历史范围%': x['exchange_long_range'],
            '交易所旧档日期': x['exchange_as_of'],
            '旧档匹配方式': x['exchange_scope'],
            '先锋旧公司多%': x['company_long_pct'],
            '先锋旧公司空%': x['company_short_pct'],
            '先锋官网发布日期': x['company_as_of'],
            '交易所来源': x['exchange_url'],
            '先锋公司来源': x['company_url'],
        } for x in history]
        if display_history:
            st.dataframe(display_history,hide_index=True,use_container_width=True,height=430)
            csv_buffer=io.StringIO(newline='')
            writer=csv.DictWriter(csv_buffer,fieldnames=list(display_history[0]),lineterminator='\n')
            writer.writeheader();writer.writerows(display_history)
            st.download_button('↓ 下载87品种历史保证金参考CSV',
                data=('\ufeff'+csv_buffer.getvalue()).encode('utf-8'),
                file_name='historical_margin_reference_2026.csv',
                mime='text/csv')
        else:
            st.info('未找到内置历史保证金基准，请检查 data/historical_*_margin.csv。')

with tab2:
    st.markdown('#### 默认公司收费与合约规格')
    company_fees = _load_csv(DATA / 'company_fees.csv')
    fee_versions = sorted({r.get('effective_from', '') for r in company_fees if r.get('effective_from')})
    latest_fee = fee_versions[-1] if fee_versions else '未知'
    st.caption(f'公司默认费率来自先锋期货PDF（更新日期 {latest_fee}），**不是自动实时费率或客户账户实际费率**。覆盖项优先，支持指定某合约与生效日期。所有数据只保存在本机。')
    st.markdown('**导入新版公司手续费 PDF（需要人工提供新版公司文件）**')
    st.caption('识别五列表格及更新日期，先预览数量与差异，确认后才会覆盖默认表；旧版自动备份。仅导入开户默认开仓费，绝不猜测平今费和保证金。')
    pdf_upload = st.file_uploader('上传先锋期货最新手续费标准PDF', type=['pdf'], key='company_pdf')
    if pdf_upload is not None:
        try:
            pdf_raw = pdf_upload.getvalue()
            uploaded_version, uploaded_fees = parse_company_fee_pdf(pdf_raw)
            delta = fee_diff(company_fees, uploaded_fees)
            st.info(f'PDF更新日期：{uploaded_version}；识别 {len(uploaded_fees)} 条；收费方式/数值变更 {len(delta)} 条。')
            if delta:
                st.dataframe(delta, hide_index=True, use_container_width=True)
            else:
                st.caption('与当前基准相比无收费数值变化；可能仅更新PDF版本日期。')
            if st.button('确认以此PDF更新公司默认费率', type='primary'):
                result = install_fee_pdf(pdf_raw, DATA)
                st.success(f"公司费率已更新至 {result['version']}，共 {result['rows']} 条；旧版已存到 data/history")
                st.rerun()
        except Exception as error:
            st.error(f'PDF解析/导入校验失败：{type(error).__name__}: {error}')
    st.write(f"已载入 {len(_load_csv(DATA/'contracts.csv'))} 种合约规格、{len(company_fees)} 条公司默认收费。")
    st.warning('公司保证金与平今费没有统一可靠公开源。要形成准确客户报价，需要拿到公司内部授权参数或逐账户核对。')
    st.markdown('**批量导入已确认的开户默认平今手续费 CSV**')
    st.caption('采用 templates/company_close_today_template.csv。必须填写生效日、核验日期、具体出处；支持明确免收的 0。仅默认收费，不录客户身份信息，不意味着适用于所有客户账户。')
    closing_upload=st.file_uploader('导入公司默认平今规则（CSV）',type=['csv'],key='bulk_close_today')
    if closing_upload is not None:
        try:
            closing_rows=parse_company_close_today_csv(closing_upload.getvalue())
            st.success(f'格式检查通过：{len(closing_rows)} 条平今规则。请复核来源与账户适用范围。')
            st.dataframe(closing_rows,hide_index=True,use_container_width=True)
            if st.button('确认合并已核验平今规则',key='install_close_today'):
                n=merge_company_close_today_csv(closing_upload.getvalue(),DATA)
                st.success(f'已在本地合并 {n} 条；重新生成报告生效。')
        except Exception as ex:
            st.error('平今规则批量导入失败：'+str(ex))
    st.markdown('**六市场同日合约保证金 CSV（核验补充）**')
    st.caption('采用 templates/exchange_margin_daily_template.csv，必须是官方或经过人工核实的单一交易日、具体合约保证金率。无法自动证明 CSV 真实，且不会延用到次日。')
    margin_upload=st.file_uploader('导入六市场同交易日保证金（CSV）',type=['csv'],key='multi_market_margin')
    if margin_upload is not None:
        try:
            parsed_day, margins=parse_exchange_margin_csv(margin_upload.getvalue())
            count=sum(len(v) for v in margins.values())
            st.success(f'格式检查通过：交易日 {parsed_day}，{count} 个合约。仅按本日适用。')
            if st.button('确认保存该日六市场保证金',key='install_exchange_margin'):
                thedate,n=install_exchange_margin_csv(margin_upload.getvalue(),DATA)
                st.success(f'已在本地保存 {thedate} 共 {n} 个合约；重新生成日报生效。')
        except Exception as ex:
            st.error('交易所保证金导入失败：'+str(ex))
    st.markdown('**公司同交易日保证金 CSV（由内部系统/官方日报核验）**')
    st.caption('采用 templates/company_margin_daily_template.csv，只保存某交易日具体合约的公司默认多空保证金；不收录客户信息，不自动推广为其他交易日或所有账户。')
    company_margin_upload=st.file_uploader('导入公司当日默认保证金（CSV）',type=['csv'],key='company_margin_day')
    if company_margin_upload is not None:
        try:
            dated, confirmed=parse_company_margin_csv(company_margin_upload.getvalue())
            count=sum(len(v) for v in confirmed.values())
            st.success(f'公司保证金 CSV 格式核验：{dated} 共 {count} 个具体合约。')
            if st.button('确认保存公司当日保证金',key='save_company_margin_day'):
                dated,n=install_company_margin_csv(company_margin_upload.getvalue(),DATA)
                st.success(f'保存 {dated} 的公司默认保证金 {n} 条；重新生成日报后更新。')
        except Exception as ex:
            st.error('公司保证金 CSV 校验失败：'+str(ex))
    st.markdown('**公司费率与保证金覆盖项（编辑后需保存）**')
    st.caption('若公司给出了独立平昨或平今费率，可填写 close_yesterday_fee_type/value、close_today_fee_type/value；RATE 为成交金额比例的小数，FIXED 为元/手。**平今必须同时提供 verified_at（核验日）和 source_note（来源说明）才会计算**。勿填入客户身份信息。')
    import pandas as pd
    path = DATA/'company_overrides.csv'
    raw = pd.read_csv(path, dtype=str).fillna('')
    for column in ['close_yesterday_fee_type','close_yesterday_fee_value']:
        if column not in raw.columns: raw[column]=''
    if raw.empty:
        raw = pd.DataFrame([{key:'' for key in raw.columns}])
    edits = st.data_editor(raw, num_rows='dynamic',use_container_width=True, hide_index=True,key='company_overrides')
    if st.button('保存公司参数覆盖项'):
        to_save = edits.fillna('').astype(str)
        to_save = to_save[to_save.apply(lambda row:any(str(x).strip() for x in row.values),axis=1)]
        to_save.to_csv(path,index=False,encoding='utf-8-sig')
        st.success(f'已保存 {len(to_save)} 条覆盖配置（仅当前电脑）')
    st.markdown('**大商所官网/授权系统导出的CSV——无 Token 时的替代方案**')
    st.caption('将官方渠道拿到的数据手工映射成标准 CSV 后导入。程序严格检查交易日，不会把旧结算日参数应用于今天。此处上传文件仅供本机内部核验。')
    date_margin=st.file_uploader('大商所每日合约保证金（CSV）',type=['csv'],key='dce_margin')
    if date_margin is not None:
        try:
            from dce_import import parse_margin_csv
            thedate,pars=parse_margin_csv(date_margin.getvalue())
            st.success(f'已解析 {thedate} 共 {len(pars)} 个合约；这是手工导入的数据，不代表由本程序自动核实官方真伪。')
            if st.button('确认保存该日保证金CSV',key='install_margin'):
                (DATA/('dce_margin_'+thedate+'.csv')).write_bytes(date_margin.getvalue())
                st.success('保证金导入成功；仅用于相同交易日的报告。')
        except Exception as ex:
            st.error('CSV格式校验失败：'+str(ex))
    date_daily=st.file_uploader('大商所每日合约结算价、持仓量（CSV）',type=['csv'],key='dce_daily')
    if date_daily is not None:
        try:
            from dce_import import parse_daily_csv
            thedate,rows=parse_daily_csv(date_daily.getvalue())
            st.success(f'已解析 {thedate} 共 {len(rows)} 个具体合约；仅用于该交易日。')
            if st.button('确认保存该日日行情CSV',key='install_daily'):
                (DATA/('dce_daily_'+thedate+'.csv')).write_bytes(date_daily.getvalue())
                st.success('日行情导入成功；重新生成日报后生效。')
        except Exception as ex:
            st.error('CSV格式校验失败：'+str(ex))
    st.markdown('**交易所缺失参数手工覆盖项**')
    st.caption('交易所人工覆盖只允许 effective_from **精确等于报告结算日**；旧日期不会自动沿用。建议优先用上面的六市场每日保证金 CSV。')
    path2 = DATA/'exchange_overrides.csv'
    raw2 = pd.read_csv(path2,dtype=str).fillna('')
    if raw2.empty:
        raw2 = pd.DataFrame([{key:'' for key in raw2.columns}])
    edits2 = st.data_editor(raw2,num_rows='dynamic',use_container_width=True,hide_index=True,key='exchange_overrides')
    if st.button('保存交易所人工核验项'):
        to_save=edits2.fillna('').astype(str)
        to_save=to_save[to_save.apply(lambda row:any(str(x).strip() for x in row.values),axis=1)]
        to_save.to_csv(path2,index=False,encoding='utf-8-sig')
        st.success(f'已保存 {len(to_save)} 条交易所参数')
    st.caption('fee_type: RATE=成交金额比例的小数（例如万分之5填0.0005），FIXED=元/手；保证金百分比直接填 12 表示12%。交易所原始参数未核单位时仅用于显示。')

with tab3:
    st.markdown('''**费用规则**：先锋2026-11-02 PDF 给出品种级开户默认交易手续费，并未单列平昨或平今。开仓使用此默认标准估算；平昨仅按同一单边标准试算且标注待核；平今无确认覆盖值时禁止自动填入。隔夜往返=开仓+平昨；日内往返=开仓+平今；含基金的往返费用包含两笔交易各自的保障基金。

    **定价规则**：结算基准日为最近完整交易日；结算价只用于估算资金占用与按成交额计费的基准金额。
    实际成交手续费应根据成交价格、成交时间、开平仓方向、是否平今、各账户费率和保障基金计算，不能拿结算价替代实际成交价。

    **风险控制**：① 六市场缺任一即显示不完整；② 五市场 `futures_settle` 与大商所 Tushare 授权参数或指定交易日CSV分开；③ 交易所接口原始手续费字段的计费单位可能不统一，未确认前不将其转换为金额；④ 先锋公司费率以2026-11-02最新版PDF为初始值，后续如有新PDF可在本工具校验后手动更新，实际以交易与结算系统/最新批复为准；⑤ 公司保证金率不预设“+3%”。

    **具体主力合约**：按单一交易日、每个品种最大有效持仓量筛选，平手以成交量和合约名打破；持仓量缺失不强行判定。不是“主力连续指数”。

    **交易日**：上个工作日21:00开始的夜盘属于下一个交易日。周一早上最近的完整结算通常是周五，而周一夜盘归属周二交易日（节假日以交易所日历为准）。

    **数据来源**：CNEquity 期货湖 (`futures_bars` 的交易所/新浪上游记录) → 本地具体主力合约 → 先锋公司收费 PDF。交易所保证金仍独立依赖 AKShare/授权/人工核验，**CNEquity 当前不能自动提供完整逐日保证金数据**。大商所免费新浪路由可能缺无成交合约，不应称为全量验收。
    官方数据口径请参考[上期所数据](https://www.shfe.com.cn/reports/tradedata/dailyandweeklydata/)、[能源中心数据](https://www.ine.cn/reports/tradedata/dailyandweeklydata/)、[广期所](https://www.gfex.com.cn/)、[AKShare接口说明](https://github.com/akfamily/akshare/blob/main/docs/data/futures/futures.md)、[Tushare日行情](https://tushare.pro/document/2?doc_id=138)、[Tushare结算参数](https://tushare.pro/document/2?doc_id=141)、[Tushare大商所交易参数](https://tushare.pro/document/2?doc_id=502)。

    **运行条件**：本机安装 cnequity，并能访问交易所/新浪数据源；免费不代表稳定可达。首次仅建立期货湖，不会下载 A 股市场。客户信息不要录入本工具。手续费PDF的“更新日期”不是客户费率实际生效日。''')
