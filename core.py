"""期货结算成本日报：读交易所日行情、结算参数，生成可审计的内部估算。

IMPORTANT: Exchange parameters from AKShare are information references, not broker account-level facts.
"""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import math
import re
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
OUT = BASE / "reports"
TZ = ZoneInfo("Asia/Shanghai")
MARKETS = {"SHFE": "上期所", "INE": "能源中心", "DCE": "大商所", "CZCE": "郑商所", "CFFEX": "中金所", "GFEX": "广期所"}
COLUMNS = [
    ("exchange_name", "交易所"), ("variety_name", "品种"), ("contract", "合约"),
    ("is_main", "主力候选"), ("settlement_date", "结算日期"),
    ("settlement", "前一交易日结算价"), ("multiplier", "合约乘数"),
    ("notional", "合约价值(元)"), ("open_interest", "持仓量(手)"),
    ("exchange_margin_long_pct", "交易所投机多保证金(%)"),
    ("exchange_margin_short_pct", "交易所投机空保证金(%)"),
    ("company_margin_long_pct", "公司多头保证金(%)"),
    ("company_margin_short_pct", "公司空头保证金(%)"),
    ("exchange_margin_one_lot", "交易所多头一手保证金(元)"),
    ("display_exchange_margin_long_pct", "展示交易所保证金率(%；含历史标记)"),
    ("display_exchange_margin_short_pct", "展示交易所空头保证金率(%；含历史标记)"),
    ("display_exchange_margin_one_lot", "展示交易所一手保证金(元；含历史标记)"),
    ("display_exchange_margin_status", "展示交易所保证金状态"),
    ("display_exchange_margin_source", "展示交易所保证金来源"),
    ("display_company_margin_long_pct", "展示公司保证金率(%；含历史标记)"),
    ("display_company_margin_short_pct", "展示公司空头保证金率(%；含历史标记)"),
    ("display_company_margin_one_lot", "展示公司一手保证金(元；含历史标记)"),
    ("display_company_margin_status", "展示公司保证金状态"),
    ("display_company_margin_source", "展示公司保证金来源"),
    ("company_margin_one_lot", "公司多头一手保证金(元)"),
    ("historical_exchange_long_pct", "交易所历史保证金参考多头率(%)"),
    ("historical_exchange_short_pct", "交易所历史保证金参考空头率(%)"),
    ("historical_exchange_one_lot", "交易所历史参考一手估算金额(元)"),
    ("historical_exchange_basis", "交易所历史保证金来源日期及范围"),
    ("historical_exchange_source_url", "交易所历史参考URL"),
    ("historical_company_long_pct", "先锋公开历史公司保证金参考多头率(%)"),
    ("historical_company_short_pct", "先锋公开历史公司保证金参考空头率(%)"),
    ("historical_company_one_lot", "先锋历史保证金参考一手估算金额(元)"),
    ("historical_company_basis", "先锋历史公司保证金来源日期及范围"),
    ("historical_company_source_url", "先锋历史保证金参考URL"),
    ("exchange_margin_reference_long_pct", "公开保证金参考多头(%；非结算核验)"),
    ("exchange_margin_reference_one_lot", "公开参考一手保证金(元)"),
    ("company_margin_notice_reference_long_pct", "先锋历史公告推算多头参考率(%；非当日确认)"),
    ("company_margin_notice_reference_one_lot", "先锋历史公告推算一手资金(元)"),
    ("margin_reference_source", "参考数据来源"),
    ("company_notice_reference_source", "公司公告参考来源"),
    ("company_margin_source", "公司保证金核验来源"),
    ("company_fee_open", "客户开仓参考手续费/手(元)"),
    ("company_fee_close_yesterday", "客户平昨参考手续费/手(元)"),
    ("company_fee_close_today", "客户平今手续费/手(元;待核可为空)"),
    ("company_fee_open_plus_fund", "开仓含保障基金/手(元)"),
    ("company_fee_close_yesterday_plus_fund", "平昨含保障基金/手(元)"),
    ("company_fee_close_today_plus_fund", "平今含保障基金/手(元;待核可为空)"),
    ("overnight_round_trip_fee", "隔夜一开一平手续费合计/手(未含基金)(元)"),
    ("day_round_trip_fee", "日内一开一平手续费合计/手(未含基金)(元;待核可为空)"),
    ("overnight_round_trip_plus_fund", "隔夜一开一平含双边基金/手(元)"),
    ("day_round_trip_plus_fund", "日内一开一平含双边基金/手(元;待核可为空)"),
    ("fee_status", "手续费核验口径"),
    ("margin_source", "交易所保证金数据来源"),
    ("company_close_today_verified", "公司平今费核验状态"),
    ("company_fee_type", "公司开仓费计费方式"),
    ("company_fee_rule", "公司开仓费率规则值"),
    ("company_close_yesterday_fee_type", "平昨覆盖计费方式"),
    ("company_close_yesterday_fee_rule", "平昨覆盖收费值"),
    ("company_close_today_fee_type", "平今覆盖计费方式"),
    ("company_close_today_fee_rule", "平今覆盖收费值"),
    ("company_baseline_effective", "公司默认费率版本日期"),
    ("fund_open", "保障基金单边估算(元)"),
    ("exchange_fee_raw_open", "交易所原始开仓参数(未核单位)"),
    ("exchange_fee_raw_close_today", "交易所原始平今参数(未核单位)"),
    ("data_status", "核验状态"), ("issue", "缺口/提示"),
    ("fee_source", "公司费率依据"),
    ("data_source", "数据来源")]


def _as_float(x: Any) -> Optional[float]:
    if x is None or isinstance(x, bool):
        return None
    try:
        if isinstance(x, str):
            x = x.replace(",", "").strip().replace("%", "")
            if x in ("", "-", "--", "None", "nan", "NaN"):
                return None
        y = float(x)
        return y if math.isfinite(y) else None
    except (ValueError, TypeError):
        return None


def _ratio_percent(x: Any) -> Optional[float]:
    """Return percent units. Numeric <=1 interpreted as decimal ratio; strings 8% interpreted as 8."""
    y = _as_float(x)
    if y is None or y <= 0:
        return None
    if isinstance(x, str) and '%' in x:
        return y if y <= 100 else None
    if y <= 1:
        return round(y * 100, 6)
    return y if y <= 100 else None


def _safe_date(x: Any) -> str:
    return str(x or "").strip().replace("-", "").replace("/", "")[:8]


def _contract(x: Any) -> str:
    return str(x or "").strip().lower().replace(" ", "")


def _variety(x: Any, contract: str = "") -> str:
    raw = str(x or "").strip().lower()
    m = re.match(r"^[a-z]{1,3}", raw)
    if m:
        return m.group()
    m = re.match(r"^[a-z]{1,3}", contract)
    return m.group() if m else ""


def _is_futures_contract(s: str) -> bool:
    return bool(re.fullmatch(r"[a-z]{1,3}\d{3,4}", s)) and not s.endswith("99")


def _load_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _today_cutoff(now: datetime) -> date:
    """Prevents reading a potentially unfinished current trading day before 18:00 China time."""
    n = now.astimezone(TZ)
    return n.date() if n.time() >= time(18) else n.date() - timedelta(days=1)


def _row_dicts(df: Any) -> List[dict]:
    if df is None or getattr(df, "empty", False):
        return []
    if hasattr(df, 'to_dict'):
        return df.to_dict(orient="records")
    return [dict(x) for x in df]


def _fetch_daily(api: Any, cutoff: date, days: int = 18) -> tuple[dict, dict]:
    start = (cutoff - timedelta(days=days)).strftime('%Y%m%d')
    end = cutoff.strftime('%Y%m%d')
    per_market: dict[str, list[dict]] = {}
    errs: dict[str, str] = {}
    for market in MARKETS:
        try:
            df = api.get_futures_daily(start_date=start, end_date=end, market=market)
            rows = _row_dicts(df)
            clean = []
            for raw in rows:
                sym = _contract(raw.get("symbol"))
                d = _safe_date(raw.get("date"))
                settle = _as_float(raw.get("settle"))
                if not (_is_futures_contract(sym) and len(d) == 8 and d <= end and settle and settle > 0):
                    continue
                v = _variety(raw.get("variety"), sym)
                if not v:
                    continue
                clean.append({"exchange": market, "contract": sym, "variety": v, "date": d,
                              "settlement": settle, "open_interest": _as_float(raw.get("open_interest")),
                              "volume": _as_float(raw.get("volume")), "origin":raw.get("origin", "")})
            per_market[market] = clean
            if not clean:
                errs[market] = "该日期范围内未取到有效合约结算价"
        except Exception as ex:
            per_market[market] = []
            errs[market] = f"日行情获取失败：{type(ex).__name__}: {str(ex)[:150]}"
    return per_market, errs


def _pick_trading_day(per_market: dict) -> tuple[Optional[str], list[str]]:
    date_sets = {m: {r['date'] for r in recs} for m, recs in per_market.items() if recs}
    if not date_sets:
        return None, list(MARKETS)
    common = set.intersection(*date_sets.values()) if date_sets else set()
    if len(date_sets) == len(MARKETS) and common:
        return max(common), []
    # Partial output has a single price date, NEVER blend dates to fake complete coverage.
    counts = Counter(day for dates in date_sets.values() for day in dates)
    ranked = sorted(counts.items(), key=lambda x: (x[1], x[0]), reverse=True)
    chosen = ranked[0][0]
    missing = [m for m in MARKETS if chosen not in date_sets.get(m, set())]
    return chosen, missing


def _fetch_settle(api: Any, snapshot_date: str, tushare_token: str = "", tushare_client: Any = None) -> tuple[dict, dict]:
    params: dict[str, dict] = {}
    errs: dict[str, str] = {}
    for market in MARKETS:
        if market == "DCE":
            if tushare_token:
                try:
                    from dce_provider import margin_for_date
                    dce_params, message = margin_for_date(tushare_token, snapshot_date, client=tushare_client)
                    params[market] = dce_params
                    if not dce_params:
                        errs[market] = message
                except Exception as exc:
                    params[market] = {}
                    errs[market] = f"大商所保证金数据接入失败：{type(exc).__name__}: {str(exc)[:180]}"
            else:
                params[market] = {}
                errs[market] = "大商所不支持 AKShare futures_settle；未填 Tushare Token，合约保证金待核"
            # Authorized/manual local dated files are accepted only for EXACT report date.
            if not params.get('DCE'):
                try:
                    from dce_import import load_margin
                    imported=load_margin(DATA, snapshot_date)
                    if imported:
                        params['DCE']=imported
                        errs.pop('DCE', None)
                except Exception as exc:
                    errs['DCE']=f'人工CSV读取失败：{type(exc).__name__}: {str(exc)[:160]}'
            continue
        try:
            df = api.futures_settle(date=snapshot_date, market=market)
            d = {}
            for x in _row_dicts(df):
                sym = _contract(x.get('symbol'))
                if not _is_futures_contract(sym):
                    continue
                record_date = _safe_date(x.get('date'))
                if record_date and record_date != snapshot_date:
                    continue
                d[sym] = {
                    'long': _ratio_percent(x.get('spec_long_margin_ratio')) or _ratio_percent(x.get('long_margin_ratio')),
                    'short': _ratio_percent(x.get('spec_short_margin_ratio')) or _ratio_percent(x.get('short_margin_ratio')),
                    'raw_open_fee': str(x.get('trade_fee_ratio') if x.get('trade_fee_ratio') is not None else ''),
                    'raw_close_fee': str(x.get('close_today_fee_ratio') if x.get('close_today_fee_ratio') is not None else ''),
                }
            params[market] = d
            if not d:
                errs[market] = "当天交易所结算参数为空；未使用历史参数冒充最新值"
        except Exception as ex:
            params[market] = {}
            errs[market] = f"结算参数获取失败：{type(ex).__name__}: {str(ex)[:150]}"
    # Separate exact-day reviewed CSV fallback. Do not accept historical
    # or undocumented values as today's exchange margin.
    try:
        from parameter_import import load_exchange_margin
        manual = load_exchange_margin(DATA, snapshot_date)
        for market, contracts in manual.items():
            for sym, record in contracts.items():
                existing = params.setdefault(market, {}).get(sym, {})
                # Explicit user-reviewed exact-day CSV is preferred when present.
                params[market][sym] = {**existing, **record}
            if contracts:
                errs.pop(market, None)
    except Exception as exc:
        errs['manual_exchange_csv'] = f'人工保证金CSV读取失败：{type(exc).__name__}: {str(exc)[:160]}'
    # Explicitly labelled non-authoritative public references. These are NOT
    # settled exchange margin rates, and never override same-day verified values.
    if getattr(api, 'enable_public_margin_reference', False):
        from margin_reference import fetch_czce_reference, fetch_dce_reference
        for market, fetcher in [('CZCE', fetch_czce_reference), ('DCE', fetch_dce_reference)]:
            current = params.setdefault(market, {})
            try:
                fallback = fetcher(snapshot_date)
                installed = 0
                for sym, candidate in fallback.items():
                    existing = current.get(sym) or {}
                    if existing.get('long') is None and existing.get('short') is None:
                        current[sym] = {**existing, **candidate}
                        installed += 1
                if installed:
                    detail = f'{installed} 个合约仅取得公开参考值，非交易所结算核验'
                    errs[market] = (errs.get(market, '') + '；' + detail).lstrip('；')
            except Exception as exc:
                detail = f'公开参考源不可用：{type(exc).__name__}: {str(exc)[:100]}'
                errs[market] = (errs.get(market, '') + '；' + detail).lstrip('；')
    return params, errs


def _latest_override(overrides: list[dict], market: str, var: str, contract: str, snapshot_date: str, *, exact_day: bool = False) -> Optional[dict]:
    candidates = []
    for row in overrides:
        if row.get('exchange', '').upper().strip() != market or row.get('variety', '').lower().strip() != var:
            continue
        specific = _contract(row.get('contract'))
        if specific and specific != contract:
            continue
        eff = _safe_date(row.get('effective_from'))
        if exact_day and eff != snapshot_date:
            continue
        if not exact_day and eff and eff > snapshot_date:
            continue
        score = (1 if specific else 0, eff)
        candidates.append((score, row))
    return max(candidates, key=lambda x:x[0])[1] if candidates else None


def _fee_value(kind: Any, val: Any, notional: Optional[float]) -> Optional[float]:
    n = _as_float(val)
    if n is None or n < 0:
        return None
    typ = str(kind or '').upper().strip()
    if typ == 'FIXED':
        return round(n, 4)
    if typ == 'RATE' and notional is not None:
        return round(notional * n, 4)
    return None


def _nullable_round(x: Optional[float], ndigits: int = 4) -> Optional[float]:
    return round(x, ndigits) if x is not None else None


def _company_fees_for_day(snapshot: str) -> tuple[list[dict], str]:
    """选取不晚于结算日的最新已保存公司PDF版本。

    PDF 的“更新日期”仅用作版本选择，不代表账户费率实际生效日。
    """
    candidates: dict[str, Path] = {}
    current = DATA / 'company_fees.csv'
    if current.exists():
        rows = _load_csv(current)
        versions = [r.get('effective_from', '') for r in rows if r.get('effective_from')]
        if versions:
            candidates[max(versions)] = current
    for path in (DATA / 'history').glob('company_fees_*.csv'):
        version = path.stem.removeprefix('company_fees_')
        if re.fullmatch(r'20\d{6}', version):
            candidates[version[:4] + '-' + version[4:6] + '-' + version[6:]] = path
    date_iso = f'{snapshot[:4]}-{snapshot[4:6]}-{snapshot[6:]}'
    available = [date for date in candidates if date <= date_iso]
    if not available:
        return [], '无可用公司默认收费版本（报告日早于最早保存的PDF日期）'
    version = max(available)
    return _load_csv(candidates[version]), version


def generate(api: Any, now: Optional[datetime] = None, fund_per_100m: float = 9.0,
             require_complete: bool = False, tushare_token: str = "", tushare_client: Any = None) -> dict:
    now = now or datetime.now(TZ)
    cutoff = _today_cutoff(now)
    daily, daily_errs = _fetch_daily(api, cutoff)
    dce_daily_source = getattr(api,'daily_source','AKShare 官网日行情')
    # DCE's official website can block automated AKShare requests with HTTP 412.
    # Fallback is a licensed data relay and is only used when access is configured.
    if not daily.get('DCE'):
        candidates = sorted({r['date'] for m, rows in daily.items() if m != 'DCE' for r in rows}, reverse=True)
        if not candidates:
            candidates = [(cutoff-timedelta(days=i)).strftime('%Y%m%d') for i in range(7)]
        try:
            from dce_import import load_daily
            for date_key in candidates[:7]:
                imported=load_daily(DATA, date_key)
                if imported:
                    daily['DCE']=imported
                    daily_errs.pop('DCE',None)
                    dce_daily_source='用户核验的同交易日大商所日行情CSV导入'
                    break
        except Exception as ex:
            daily_errs['DCE']='大商所日行情CSV导入失败：'+str(ex)[:180]
        if not daily.get('DCE') and tushare_token:
            from dce_provider import daily_for_date
            attempts=[]
            for date_key in candidates[:5]:
                try:
                    dce_rows=daily_for_date(tushare_token, date_key, client=tushare_client)
                    if dce_rows:
                        daily['DCE']=dce_rows
                        daily_errs.pop('DCE',None)
                        dce_daily_source='Tushare fut_daily（大商所公开行情的授权转接）'
                        break
                    attempts.append(date_key+':空数据')
                except Exception as ex:
                    attempts.append(date_key+':'+type(ex).__name__+': '+str(ex)[:100])
            if not daily.get('DCE'):
                daily_errs['DCE']='大商所行情自动补采失败（Tushare）: '+'；'.join(attempts[:3])
    snap, missing = _pick_trading_day(daily)
    if not snap:
        details='；'.join(f"{m}: {e}" for m,e in daily_errs.items())
        raise RuntimeError("六市场均未取得有效日行情。接口/权限/网络诊断："+details[:850])
    if missing and require_complete:
        raise RuntimeError("六市场数据不完整：" + ','.join(missing))
    # Prevent silently presenting an older common date as the latest trading day.
    latest_available = {market: (max(r['date'] for r in rows) if rows else None)
                        for market,rows in daily.items()}
    lagging = [market for market, last in latest_available.items() if last and last > snap]
    # Calendar is NOT a trading-holiday calendar: warn conservatively without
    # manufacturing a price for a presumed session.
    report_day = date(int(snap[:4]),int(snap[4:6]),int(snap[6:]))
    possible_workdays = sum(1 for i in range(1,(cutoff-report_day).days+1)
                            if (report_day+timedelta(days=i)).weekday()<5)
    suspected_stale = possible_workdays >= 2
    settle, settle_errs = _fetch_settle(api, snap, tushare_token, tushare_client)
    contract_info = {(x['exchange'], x['variety'].lower()): x for x in _load_csv(DATA / 'contracts.csv')}
    company_rows, company_version = _company_fees_for_day(snap)
    company = {(x['exchange'], x['variety'].lower()): x for x in company_rows}
    company_ov = _load_csv(DATA / 'company_overrides.csv')
    try:
        from parameter_import import load_company_margin
        verified_company_margins = load_company_margin(DATA, snap)
    except Exception as exc:
        verified_company_margins = {}
        settle_errs['company_margin_csv'] = f'公司当日保证金 CSV 不可用：{type(exc).__name__}: {str(exc)[:120]}'
    exchange_ov = _load_csv(DATA / 'exchange_overrides.csv')
    applicable = []
    for market, recs in daily.items():
        applicable += [r for r in recs if r['date'] == snap]
    main = {}
    all_varieties = {(r['exchange'], r['variety']) for r in applicable}
    for r in applicable:
        k = (r['exchange'], r['variety'])
        oi = r['open_interest']
        # 没有有效持仓量时绝不凭合约月份或成交量假装确定了主力。
        if oi is None or oi <= 0:
            continue
        if k not in main or (oi, r['volume'] or 0, r['contract']) > (main[k]['open_interest'], main[k]['volume'] or 0, main[k]['contract']):
            main[k] = r
    unresolved_main = sorted(all_varieties - set(main))
    result = []
    for x in sorted(applicable, key=lambda r:(list(MARKETS).index(r['exchange']), r['variety'], r['contract'])):
        market, var, sym = x['exchange'], x['variety'], x['contract']
        spec = contract_info.get((market, var)) or {}
        co = company.get((market, var)) or {}
        override = _latest_override(company_ov, market, var, sym, snap) or {}
        # Exchange margin schedule must be confirmed for this *exact* trading day.
        ex_override = _latest_override(exchange_ov, market, var, sym, snap, exact_day=True) or {}
        manual_verified = (_safe_date(ex_override.get('verified_at')) <= now.astimezone(TZ).strftime('%Y%m%d')
                           and len(_safe_date(ex_override.get('verified_at'))) == 8
                           and bool(str(ex_override.get('source_note') or '').strip()))
        if not manual_verified:
            ex_override = {}
        m = _as_float(spec.get('multiplier'))
        price = x['settlement']
        notional = round(price * m, 4) if m else None
        from historical_margin import historical_exchange_reference, historical_company_reference
        # Historical snapshots are NEVER used to populate live/verified margin.
        old_exchange = historical_exchange_reference(market, var, sym, DATA)
        old_company = historical_company_reference(market, var, DATA)
        old_exchange_long = old_exchange.get('long')
        old_company_long = old_company.get('long')
        old_exchange_money = _nullable_round(notional * old_exchange_long / 100, 2) if notional is not None and old_exchange_long is not None else None
        old_company_money = _nullable_round(notional * old_company_long / 100, 2) if notional is not None and old_company_long is not None else None
        old_exchange_basis = (
            f"{old_exchange['as_of']} 历史快照｜{old_exchange['scope']}｜"
            f"{old_exchange['explanation']}｜同品种历史范围 "
            f"{old_exchange['long_range'][0]:g}–{old_exchange['long_range'][1]:g}%"
            if old_exchange else '没有历史资料')
        old_company_basis = (
            f"{old_company['as_of']} 先锋官网历史品种基准｜{old_company['explanation']}"
            if old_company else '没有历史资料')
        params = settle.get(market, {}).get(sym) or {}
        reference_only = params.get('reference_only') is True
        ex_long = None if reference_only else params.get('long')
        ex_short = None if reference_only else params.get('short')
        # Public reference values are deliberately separate from confirmed margin.
        reference_long = params.get('long') if reference_only else None
        reference_short = params.get('short') if reference_only else None
        manual_margin_applied = False
        for key,side in (('exchange_margin_long_pct','long'),('exchange_margin_short_pct','short')):
            val = _as_float(ex_override.get(key))
            if val is not None and 0 < val <= 100:
                if side=='long':ex_long=val
                else:ex_short=val
                manual_margin_applied = True
        company_today = verified_company_margins.get(market, {}).get(sym, {})
        comp_long = (_as_float(company_today.get('long')) if company_today.get('long') is not None
                     else _as_float(override.get('margin_long_pct')))
        comp_short = (_as_float(company_today.get('short')) if company_today.get('short') is not None
                      else _as_float(override.get('margin_short_pct')))
        company_margin_source = (company_today.get('origin') if company_today else
                                 '旧公司覆盖项（未按报告交易日复核）' if (comp_long is not None or comp_short is not None)
                                 else '缺少本交易日公司保证金核验数据')
        from margin_reference import published_addon_points, SOURCE_DATE, SOURCE_ANNOUNCEMENT
        notice_points = published_addon_points(market, var, snap)
        # Only a reference scenario using a historical public broker announcement.
        # It must NOT populate company_margin_{long,short}_pct.
        notice_base_long = ex_long if ex_long is not None else reference_long
        notice_base_short = ex_short if ex_short is not None else reference_short
        notice_long = (round(notice_base_long + notice_points, 6)
                       if notice_base_long is not None and notice_points is not None
                       and notice_base_long + notice_points <= 100 else None)
        notice_short = (round(notice_base_short + notice_points, 6)
                        if notice_base_short is not None and notice_points is not None
                        and notice_base_short + notice_points <= 100 else None)
        margin_reference_source = params.get('origin', '') if reference_only else ''
        notice_source = (f'先锋历史公开公告 {SOURCE_DATE}：加收 {notice_points} 个百分点；'
                         f'{SOURCE_ANNOUNCEMENT}；非本日确认值' if notice_points is not None else '')
        fee_type = override.get('open_fee_type') or co.get('open_fee_type')
        fee_val = override.get('open_fee_value') if override.get('open_fee_value') not in ('', None) else co.get('open_fee_value')
        fee_open = _fee_value(fee_type, fee_val, notional)
        # PDF gives a variety-level default "交易手续费" but does not certify a distinct 平昨/平今 rule.
        # 平昨 is an explicit reference assumption: use the same default single-side tariff unless
        # BOTH fields of a verified close-yesterday override are provided. Never infer 平今.
        yesterday_type = str(override.get('close_yesterday_fee_type') or '').strip()
        yesterday_value = override.get('close_yesterday_fee_value')
        if yesterday_type or yesterday_value not in ('', None):
            fee_close_yesterday = _fee_value(yesterday_type, yesterday_value, notional)
            close_yesterday_basis = '已填写平昨覆盖参数（需确认适用账户）' if fee_close_yesterday is not None else '平昨覆盖项不完整，待核'
        else:
            fee_close_yesterday = _fee_value(fee_type, fee_val, notional)
            close_yesterday_basis = '仅按默认单边费率试算平昨，未获公司独立确认'
        # A manually typed rate is not automatically an approved customer rate.
        # Require a dated check and an auditable nonempty origin.
        close_candidate = _fee_value(override.get('close_today_fee_type'), override.get('close_today_fee_value'), notional)
        verification_day = _safe_date(override.get('verified_at'))
        evidence = str(override.get('source_note') or '').strip()
        try:
            verified_date = date.fromisoformat(f'{verification_day[:4]}-{verification_day[4:6]}-{verification_day[6:]}')
        except ValueError:
            verified_date = None
        verification_valid = (verified_date is not None and
                              verification_day <= now.astimezone(TZ).strftime('%Y%m%d') and bool(evidence))
        fee_close = close_candidate if verification_valid else None
        close_today_verified = ('已录入核验日期与来源（仅适用已核实的默认规则）' if fee_close is not None
                                else '缺少有效核验日期/来源或平今费率，待核')
        fund = round(notional * fund_per_100m / 1e8, 6) if notional is not None else None
        def plus_fund(fee, sides=1):
            return round(fee + fund * sides, 4) if fee is not None and fund is not None else None
        fee_open_plus_fund = plus_fund(fee_open)
        fee_close_yesterday_plus_fund = plus_fund(fee_close_yesterday)
        fee_close_today_plus_fund = plus_fund(fee_close)
        overnight_round_trip = round(fee_open + fee_close_yesterday, 4) if fee_open is not None and fee_close_yesterday is not None else None
        day_round_trip = round(fee_open + fee_close, 4) if fee_open is not None and fee_close is not None else None
        overnight_round_trip_plus_fund = plus_fund(overnight_round_trip, 2)
        day_round_trip_plus_fund = plus_fund(day_round_trip, 2)
        fee_status = (('开仓默认估算' if fee_open is not None else '开仓待核') + '；' + close_yesterday_basis + '；' +
                      ('平今有来源记录（仍须核实适用账户）' if fee_close is not None else '平今无公司确认费率，故留空'))
        raw_open = params.get('raw_open_fee', '')
        raw_close = params.get('raw_close_fee', '')
        if ex_override.get('exchange_open_fee_type') and ex_override.get('exchange_open_fee_value'):
            raw_open = f"人工核验 {ex_override['exchange_open_fee_type']}:{ex_override['exchange_open_fee_value']}"
        if ex_override.get('exchange_close_today_fee_type') and ex_override.get('exchange_close_today_fee_value'):
            raw_close = f"人工核验 {ex_override['exchange_close_today_fee_type']}:{ex_override['exchange_close_today_fee_value']}"
        issues = []
        if not m: issues.append('缺少合约乘数')
        if (market, var) not in main: issues.append('持仓量缺失/为零，无法可靠确认主力合约')
        if ex_long is None or ex_short is None: issues.append('缺同日核验的交易所保证金参数')
        if reference_only: issues.append('公开参考值不能替代交易所结算参数')
        if market == 'DCE' and not params and not ex_override: issues.append('大商所合约保证金参数待核验（授权接口失败或未配置）')
        if comp_long is None or comp_short is None: issues.append('账户/公司保证金待确认')
        if fee_open is None: issues.append('公司开仓费率待确认')
        if fee_close_yesterday is None: issues.append('公司平昨费率覆盖项不完整/无可用默认收费')
        if fee_close is None: issues.append('公司平今费率或核验凭据待确认')
        if not ex_override and (raw_open in ('', 'None', 'nan') or raw_close in ('', 'None', 'nan')):
            issues.append('交易所手续费字段缺项')
        if (not ex_override) and (raw_open or raw_close):
            issues.append('交易所原始手续费尚未核对计费单位')
        if comp_long is not None and ex_long is not None and comp_long + 1e-8 < ex_long:
            issues.append('公司多头保证金低于交易所（疑似配置错误）')
        if comp_short is not None and ex_short is not None and comp_short + 1e-8 < ex_short:
            issues.append('公司空头保证金低于交易所（疑似配置错误）')
        status = '待核' if issues else '内部估算完整（仍以系统为准）'
        source = (x.get('origin') or (dce_daily_source if market == 'DCE' else '交易所日行情经AKShare获取')) + '；'
        source += ((params.get('origin') or '交易所结算参数经AKShare获取') if params else ('人工维护参数' if ex_override else '未获取结算参数'))
        result.append({
            'exchange': market, 'exchange_name': MARKETS[market], 'variety': var,
            'variety_name': spec.get('variety_name') or co.get('variety_name') or var,
            'contract': sym, 'is_main': '是' if (market, var) in main and main[(market, var)]['contract'] == sym else ('待核' if (market, var) not in main else '否'),
            'settlement_date': snap[:4]+'-'+snap[4:6]+'-'+snap[6:],
            'settlement': price, 'multiplier': m, 'notional': notional, 'open_interest': x['open_interest'],
            'exchange_margin_long_pct': ex_long, 'exchange_margin_short_pct': ex_short,
            'exchange_margin_reference_long_pct': reference_long,
            'exchange_margin_reference_short_pct': reference_short,
            'exchange_margin_reference_one_lot': _nullable_round(notional * reference_long/100 if notional and reference_long is not None else None,2),
            'company_notice_addon_points': notice_points,
            'company_margin_notice_reference_long_pct': notice_long,
            'company_margin_notice_reference_short_pct': notice_short,
            'company_margin_notice_reference_one_lot': _nullable_round(notional * notice_long/100 if notional and notice_long is not None else None,2),
            'margin_reference_source': margin_reference_source,
            'company_notice_reference_source': notice_source,
            'company_margin_source': company_margin_source,
            'historical_exchange_long_pct': old_exchange_long,
            'historical_exchange_short_pct': old_exchange.get('short'),
            'historical_exchange_one_lot': old_exchange_money,
            'historical_exchange_basis': old_exchange_basis,
            'historical_exchange_source_url': old_exchange.get('source_url',''),
            'historical_company_long_pct': old_company_long,
            'historical_company_short_pct': old_company.get('short'),
            'historical_company_one_lot': old_company_money,
            'historical_company_basis': old_company_basis,
            'historical_company_source_url': old_company.get('source_url',''),
            'company_margin_long_pct': comp_long, 'company_margin_short_pct': comp_short,
            'exchange_margin_one_lot': _nullable_round(notional * ex_long/100 if notional and ex_long is not None else None,2),
            'company_margin_one_lot': _nullable_round(notional * comp_long/100 if notional and comp_long is not None else None,2),
            'company_fee_open': fee_open, 'company_fee_close_yesterday': fee_close_yesterday,
            'company_fee_close_today': fee_close,
            'fund_open': fund, 'company_fee_open_plus_fund': fee_open_plus_fund,
            'company_fee_close_yesterday_plus_fund': fee_close_yesterday_plus_fund,
            'company_fee_close_today_plus_fund': fee_close_today_plus_fund,
            'overnight_round_trip_fee': overnight_round_trip,
            'day_round_trip_fee': day_round_trip,
            'overnight_round_trip_plus_fund': overnight_round_trip_plus_fund,
            'day_round_trip_plus_fund': day_round_trip_plus_fund,
            'fee_status': fee_status, 'company_close_today_verified':close_today_verified,
            'margin_source':(('同交易日人工覆盖项：'+str(ex_override.get('source_note'))) if manual_margin_applied else
                             (params.get('origin') or ('交易所结算参数经AKShare获取' if params else '交易所未提供可核验保证金'))),
            'company_close_yesterday_fee_type': yesterday_type,
            'company_close_yesterday_fee_rule': yesterday_value if yesterday_value is not None else '', 
            'exchange_fee_raw_open': raw_open, 'exchange_fee_raw_close_today': raw_close,
            'data_status': status, 'issue': '；'.join(issues), 'data_source': source,
            'company_fee_type': fee_type, 'company_fee_rule': fee_val,
            'company_close_today_fee_type': override.get('close_today_fee_type','') if fee_close is not None else '',
            'company_close_today_fee_rule': override.get('close_today_fee_value','') if fee_close is not None else '',
            'fee_source': override.get('source_note') or co.get('source_note', ''),
            'company_baseline_effective': override.get('effective_from') or co.get('effective_from', ''),
        })
    # Presentation fallback: prior-year/month historical snapshots are visible
    # beside the contract instead of hidden behind dozens of columns.
    # Audited exchange/company rates above remain unchanged (None if missing).
    from margin_display import enrich_margin_display
    for record in result:
        record.update(enrich_margin_display(record))
    return {
        'created_at_bjt': now.astimezone(TZ).isoformat(timespec='seconds'),
        'report_date': now.astimezone(TZ).date().isoformat(),
        'price_date': snap[:4]+'-'+snap[4:6]+'-'+snap[6:],
        'title': '期货手续费与保证金每日核验报告',
        'status': ('行情疑似陈旧（需核对节假日）' if suspected_stale else ('行情交易日错位（需核验）' if lagging else ('六市场同日覆盖（仍需核验上游完整性）' if not missing else '部分行情覆盖（不可直接对客）'))),
        'suspected_stale':suspected_stale, 'possible_workdays_without_new_data':possible_workdays,
        'missing_markets': missing, 'lagging_markets': lagging, 'market_latest_dates':latest_available,
        'daily_errors': daily_errs, 'params_errors': settle_errs,
        'dce_daily_source': dce_daily_source if daily.get('DCE') else '大商所行情未取得',
        'cn_equity_source_quality':getattr(api,'quality',{}),
        'dce_margin_source': (next(iter(settle['DCE'].values())).get('origin', '已取得') if settle.get('DCE') else '大商所合约保证金未取得'),
        'fund_rate_per_100m': fund_per_100m,
        'company_baseline': f'先锋期货开户默认手续费PDF（更新日期：{company_version}）；非账户级标准',
        'company_baseline_version': company_version,
        'unresolved_main': [{'exchange': market, 'variety': var} for market, var in unresolved_main],
        'records': result,
        'main_records': [r for r in result if r['is_main']=='是'],
    }


def _csv_bytes(records: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator='\n')
    writer.writerow([title for _,title in COLUMNS])
    for r in records:
        writer.writerow(['' if r.get(key) is None else r.get(key) for key,_ in COLUMNS])
    return ('\ufeff'+buf.getvalue()).encode('utf-8')


def _html_report(report: dict) -> bytes:
    # 离线HTML默认展示各品种具体主力合约；可切换全合约。
    esc = lambda x: html.escape('—' if x is None or x == '' else str(x))
    version_path = BASE / 'VERSION'
    build_version = version_path.read_text(encoding='utf-8').strip() if version_path.exists() else 'unknown'
    compact = [
        ('exchange_name', '交易所'), ('variety_name', '品种'), ('contract', '具体主力合约'),
        ('open_interest', '持仓量'), ('settlement', '结算价'), ('multiplier', '合约乘数'),
        ('notional', '一手名义价值'),
        ('display_exchange_margin_long_pct', '展示交易所保证金率（含历史）'),
        ('display_exchange_margin_one_lot', '展示交易所一手保证金（含历史）'),
        ('display_company_margin_long_pct', '展示公司保证金率（含历史）'),
        ('display_company_margin_one_lot', '展示公司一手保证金（含历史）'),
        ('display_exchange_margin_status', '交易所保证金口径'),
        ('display_company_margin_status', '公司保证金口径'),
        ('exchange_margin_long_pct', '当日报表交易所多头率%（未核空）'),
        ('company_margin_long_pct', '当前公司录入多头率%（未录空）'),
        ('historical_exchange_basis', '交易所历史依据/日期'),
        ('historical_company_basis', '先锋历史依据/日期'),
        ('company_fee_open', '开仓费/手'),
        ('company_fee_close_yesterday', '平昨费/手*'),
        ('company_fee_close_today', '平今费/手'),
        ('company_fee_open_plus_fund', '开仓含基金/手'),
        ('company_fee_close_yesterday_plus_fund', '平昨含基金/手'),
        ('company_fee_close_today_plus_fund', '平今含基金/手'),
        ('overnight_round_trip_plus_fund', '隔夜开平双边含基金/手*'),
        ('day_round_trip_plus_fund', '日内开平双边含基金/手'),
        ('fee_status', '手续费口径'), ('margin_source', '保证金来源'),
        ('data_status', '核验状态'), ('issue', '待核事项'),
    ]
    def table(columns: list[tuple[str,str]], records: list[dict]) -> str:
        head = ''.join(f'<th>{esc(label)}</th>' for _, label in columns)
        body = []
        for row in records:
            klass = 'warn' if row['data_status'] == '待核' else ''
            cols = ''.join(f'<td>{esc(row.get(field))}</td>' for field,_ in columns)
            body.append(f'<tr class="{klass}">{cols}</tr>')
        if not body:
            body.append(f'<tr><td colspan="{len(columns)}">没有可确认的具体主力合约，核验持仓量后再使用。</td></tr>')
        return '<div class="wrap"><table><thead><tr>' + head + '</tr></thead><tbody>' + ''.join(body) + '</tbody></table></div>'
    missing = ', '.join(MARKETS[m] for m in report['missing_markets']) or '无'
    unresolved = len(report.get('unresolved_main', []))
    main_table = table(compact, report['main_records'])
    all_table = table(COLUMNS, report['records'])
    markup = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>期货成本日报 {esc(report['price_date'])}</title>
<style>:root{{--ink:#162b43;--muted:#66778c;--line:#dae2eb}}body{{font-family:system-ui,"Microsoft YaHei",sans-serif;color:var(--ink);margin:30px;background:#f5f8fc}}main{{background:white;padding:28px;border-radius:15px}}h1{{margin:0 0 8px;font-size:25px}}p{{color:var(--muted)}}.stats{{display:flex;gap:16px;flex-wrap:wrap;margin:20px 0}}.stat{{border:1px solid var(--line);padding:12px 20px;border-radius:12px}}.stat b{{display:block;font-size:19px}}.warning{{padding:12px;background:#fff4e6;border:1px solid #f0d1a5;border-radius:9px;margin:18px 0}}.wrap{{overflow:auto;max-height:75vh;border:1px solid var(--line);border-radius:10px}}table{{border-collapse:collapse;font-size:12px;width:100%}}.full table{{min-width:2900px}}th,td{{text-align:left;border-bottom:1px solid #ebeff4;padding:9px 11px;white-space:nowrap}}thead th{{position:sticky;top:0;background:#e8f0fa;z-index:3}}tr.warn td{{color:#815d20}}tr:hover{{background:#f7faff}}footer{{margin-top:28px;color:var(--muted);font-size:12px}}button{{cursor:pointer;background:white;color:#28466b;border:1px solid #ccd9e6;border-radius:8px;padding:10px 15px;margin:0 8px 12px 0}}button.active{{background:#163a61;color:white}}@media print{{body{{margin:0;background:white}}.wrap{{max-height:none;overflow:visible}}table{{font-size:9px}}.full,button{{display:none!important}}}}</style></head><body><main>
<h1>期货手续费与保证金每日核验报告</h1><p><strong>软件版本：{esc(build_version)}</strong>｜默认按品种显示持仓量最大的具体主力合约。展示保证金优先采用当日报表参数；缺失时可显示公开参考或历史旧档并注明日期，<strong>历史参考≠今日应缴保证金</strong>。本 HTML 是生成时的静态快照，更新软件后须重新生成报告。</p>
<div class="stats"><div class="stat">生成日<b>{esc(report['report_date'])}</b></div><div class="stat">基准结算日<b>{esc(report['price_date'])}</b></div><div class="stat">行情完整性<b>{esc(report['status'])}</b></div><div class="stat">有效合约数<b>{len(report['records'])}</b></div><div class="stat">主力合约数<b>{len(report['main_records'])}</b></div><div class="stat">无法判定主力的品种<b>{unresolved}</b></div></div>
<div class="warning">缺失交易所：{esc(missing)}。公司默认收费依据：{esc(report['company_baseline'])}。<strong>*平昨</strong>仅按照公司开户默认单边费率试算，并不等于公司确认的独立平昨标准。<strong>平今</strong>没有已确认的覆盖参数时留空；日内合计同样留空。<strong>*保证金公开参考</strong>不是当日已核验交易所或公司收费，先锋历史公告加点不保证今天或某客户仍适用。<strong>历史保证金数字</strong>来自2026年3至8月的旧档案，和本日报当前结算价结合计算出的金额只是情景示例，绝非今日应缴金额。所有金额按一手、以结算价假设开平同价估算；<strong>每次成交均另计交易者保障基金（成交金额的亿分之九）</strong>，往返含双边基金。实际客户账户以成交价、差异化费率、交易结算单为准。</div>
<button id="mainbtn" class="active" onclick="toggle('main')">具体主力合约（默认）</button><button id="allbtn" onclick="toggle('all')">全部合约（核验用）</button>
<section id="main" class="main">{main_table}</section><section id="all" class="full" style="display:none">{all_table}</section>
<footer>本报告不等于客户实际交易费用；一手开平手续费分别计算。隔夜开平=开仓+平昨；日内开平=开仓+平今；含基金合计额外加双边基金，全部以同一结算价假设开平。保证金=结算价×合约乘数×保证金率。夜盘归属下一交易日。生成于北京时间 {esc(report['created_at_bjt'])}。</footer></main>
<script>function toggle(mode){{document.getElementById('main').style.display=mode==='main'?'':'none';document.getElementById('all').style.display=mode==='all'?'':'none';document.getElementById('mainbtn').className=mode==='main'?'active':'';document.getElementById('allbtn').className=mode==='all'?'active':'';}}</script></body></html>'''
    return markup.encode('utf-8')


def compare_previous(report: dict) -> dict:
    """Compare the latest earlier *saved* snapshot; no previous snapshot means no assumed change."""
    previous = []
    for p in OUT.glob('*/futures_cost_*_raw.json'):
        try:
            old = json.loads(p.read_text(encoding='utf-8'))
            if old.get('price_date','') < report['price_date'] and old.get('price_date',''):
                previous.append((old['price_date'],p,old))
        except (OSError,ValueError,KeyError):
            continue
    if not previous:
        return {'previous_price_date':None,'events':[],'message':'本地无更早日报；无法判断费率或保证金日变化'}
    _,_,old = max(previous,key=lambda a:(a[0],a[1].stat().st_mtime_ns))
    before = {(r['exchange'],r['contract']):r for r in old.get('records',[])}
    before_main = {(r['exchange'],r['variety']):r['contract'] for r in old.get('records',[]) if r.get('is_main')=='是'}
    events=[]
    for cur in report['records']:
        key=(cur['exchange'],cur['contract'])
        prior=before.get(key)
        if prior:
            for field,label in [('exchange_margin_long_pct','交易所多头保证金率'),
                                ('exchange_margin_short_pct','交易所空头保证金率'),
                                ('company_margin_long_pct','公司多头保证金率'),
                                ('company_margin_short_pct','公司空头保证金率'),
                                ('company_fee_rule','公司开仓费规则值'),
                                ('company_fee_type','公司开仓费计费方式'),
                                ('company_close_yesterday_fee_rule','公司平昨费规则值'),
                                ('company_close_yesterday_fee_type','公司平昨费计费方式'),
                                ('company_close_today_fee_rule','公司平今费规则值'),
                                ('company_close_today_fee_type','公司平今费计费方式'),
                                ('exchange_fee_raw_open','交易所原始开仓费字段'),
                                ('exchange_fee_raw_close_today','交易所原始平今费字段')]:
                a,b=prior.get(field),cur.get(field)
                if ('' if a is None else str(a)) != ('' if b is None else str(b)):
                    events.append({'exchange':cur['exchange_name'],'variety':cur['variety_name'],'contract':cur['contract'],
                                   'change':label,'old':a,'new':b,'note':'数据/配置发生变化；核验来源后才能对客说明'})
        if cur['is_main']=='是':
            prior_main=before_main.get((cur['exchange'],cur['variety']))
            if prior_main and prior_main != cur['contract']:
                events.append({'exchange':cur['exchange_name'],'variety':cur['variety_name'],'contract':cur['contract'],
                               'change':'主力候选换月','old':prior_main,'new':cur['contract'],
                               'note':'依据日行情持仓量，不代表官方主力认定'})
    return {'previous_price_date':old['price_date'],'events':events,
            'message':f'与本地 {old["price_date"]} 日报比较；检测到 {len(events)} 个字段/主力变化'}


def package_report(report: dict) -> tuple[bytes, dict]:
    name = 'futures_cost_' + report['price_date'].replace('-','')
    csv_all = _csv_bytes(report['records'])
    csv_main = _csv_bytes(report['main_records'])
    html_data = _html_report(report)
    metadata = {k:v for k,v in report.items() if k not in ('records','main_records')}
    raw_data = json.dumps({'price_date':report['price_date'],'records':report['records']},ensure_ascii=False,indent=2).encode('utf-8')
    changes = report.get('changes',{}).get('events',[])
    changes_buf=io.StringIO(); cw=csv.writer(changes_buf); cw.writerow(['交易所','品种','合约','变化项','原值','新值','说明'])
    for e in changes: cw.writerow([e.get(k,'') for k in ('exchange','variety','contract','change','old','new','note')])
    changes_csv=('\ufeff'+changes_buf.getvalue()).encode('utf-8')
    files = {f'{name}_all.csv':csv_all, f'{name}_main.csv':csv_main,
             f'{name}.html':html_data, f'{name}_audit.json':json.dumps(metadata,ensure_ascii=False,indent=2).encode('utf-8'),
             f'{name}_raw.json':raw_data, f'{name}_changes.csv':changes_csv}
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for file, content in files.items():
            z.writestr(file,content)
    return out.getvalue(), files


def save_report(report: dict) -> tuple[str, bytes]:
    report['changes']=compare_previous(report)
    report_dir = OUT / (report['price_date'].replace('-','')+'_'+ datetime.now(TZ).strftime('%Y%m%d_%H%M%S_%f'))
    report_dir.mkdir(parents=True, exist_ok=False)
    pack, files = package_report(report)
    for name,content in files.items():
        (report_dir/name).write_bytes(content)
    (report_dir/'full_bundle.zip').write_bytes(pack)
    checksums={name:hashlib.sha256(content).hexdigest() for name,content in files.items()}
    (report_dir/'sha256_manifest.json').write_text(json.dumps(checksums,ensure_ascii=False,indent=2),encoding='utf-8')
    return str(report_dir), pack
