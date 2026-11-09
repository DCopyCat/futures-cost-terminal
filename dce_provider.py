"""大商所合约级数据。严格按结算日匹配，不回退到历史保证金。

Tushare Pro is an *optional licensed data relay*, not an unrestricted DCE API.
Credential is only accepted in process memory; never written to the report.
"""
from __future__ import annotations

import re
from typing import Any


def records(df: Any) -> list[dict]:
    if df is None or getattr(df, 'empty', False):
        return []
    if hasattr(df, 'to_dict'):
        return df.to_dict(orient='records')
    return [dict(r) for r in df]


def canon(x: Any) -> str:
    x = str(x or '').split('.')[0].strip().lower()
    return x if re.fullmatch(r'[a-z]{1,3}\d{3,4}', x) else ''


def valid_day(x: Any) -> str:
    return str(x or '').replace('-', '').replace('/', '')[:8]


def num(x: Any) -> float | None:
    try:
        if x is None or str(x).strip() in ('', '--', '-', 'nan', 'None'):
            return None
        z = float(x)
        return z if -1e12 < z < 1e12 else None
    except (ValueError, TypeError):
        return None


def from_daily(df: Any, date: str) -> list[dict]:
    """Tushare fut_daily: settle / oi / vol for actual DCE month contracts."""
    out = []
    for r in records(df):
        sym = canon(r.get('ts_code'))
        day = valid_day(r.get('trade_date'))
        settle = num(r.get('settle'))
        if not (sym and day == date and settle is not None and settle > 0):
            continue
        out.append({'exchange':'DCE', 'contract':sym,
                    'variety':re.match(r'[a-z]{1,3}',sym).group(),
                    'date':day,'settlement':settle,
                    'open_interest':num(r.get('oi')), 'volume':num(r.get('vol'))})
    return out


def _ratio_as_percent(value: Any) -> float | None:
    """Tushare fut_settle margins are decimal ratios (0.12 = 12%)."""
    rate = num(value)
    return round(rate*100, 6) if rate is not None and 0 < rate <= 1 else None


def from_fut_settle(df: Any, date: str) -> dict[str, dict]:
    """Uses authoritative field units from Tushare's documented fut_settle schema."""
    out = {}
    for r in records(df):
        sym = canon(r.get('ts_code'))
        if not sym or valid_day(r.get('trade_date')) != date:
            continue
        long = _ratio_as_percent(r.get('long_margin_rate'))
        short = _ratio_as_percent(r.get('short_margin_rate'))
        if long is None and short is None:
            continue
        out[sym] = {'long':long, 'short':short,'raw_open_fee':'','raw_close_fee':'',
                    'origin':'Tushare fut_settle（大商所来源，非公司账户保证金）'}
    return out


def from_dce_trade_param(df: Any, date: str) -> dict[str,dict]:
    """Fallback: spec_buy_rate is already percent units, not a decimal ratio.

    This endpoint does NOT document a spec_sell_rate. Never assume equal short rates.
    """
    out = {}
    for r in records(df):
        sym = canon(r.get('ts_code'))
        if not sym or valid_day(r.get('trade_date')) != date:
            continue
        trade_type = str(r.get('trade_type',''))
        if trade_type and '期货' not in trade_type and 'future' not in trade_type.lower():
            continue
        long = num(r.get('spec_buy_rate'))
        if long is None or not 0 < long <= 100:
            continue
        # Do not infer SELL rate from BUY rate; the public schema lacks it.
        out[sym] = {'long':round(long,6),'short':None,'raw_open_fee':'','raw_close_fee':'',
                    'origin':'Tushare fut_trade_param_dce（仅投机买保证金，卖保证金待核）'}
    return out


def _client(token: str, client=None):
    if client is not None:
        return client
    import tushare as ts
    return ts.pro_api(token)


def daily_for_date(token: str, date: str, client=None) -> list[dict]:
    if not token:
        return []
    return from_daily(_client(token,client).fut_daily(trade_date=date,exchange='DCE'),date)


def margin_for_date(token: str, date: str, client=None) -> tuple[dict[str,dict], str]:
    """Try 2000-point fut_settle first, then optional 5000-point trade parameter.

    Does not persist tokens. Does not return figures from a different trading day.
    """
    if not token:
        return {}, '未配置 Tushare Token；大商所保证金缺失（非软件故障）'
    api = _client(token,client)
    errors=[]
    try:
        params=from_fut_settle(api.fut_settle(trade_date=date,exchange='DCE'),date)
        if params:
            return params,f'Tushare fut_settle 返回 {len(params)} 个大商所合约参数（交易日 {date}）'
        errors.append('fut_settle 返回空值或该日无有效大商所参数')
    except Exception as e:
        errors.append(f'fut_settle: {type(e).__name__}: {str(e)[:180]}')
    try:
        params=from_dce_trade_param(api.fut_trade_param_dce(trade_date=date),date)
        if params:
            return params, f'Tushare fut_trade_param_dce 返回 {len(params)} 个买入保证金参数；空头仍待核（交易日 {date}）'
        errors.append('fut_trade_param_dce 返回空值或无有效合约')
    except Exception as e:
        errors.append(f'fut_trade_param_dce: {type(e).__name__}: {str(e)[:180]}')
    return {}, '；'.join(errors)
