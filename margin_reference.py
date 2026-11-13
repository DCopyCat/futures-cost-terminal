"""Non-authoritative, clearly labelled fallback references for DCE/CZCE margins.

Only an independently verified exchange settlement parameter or an exact-day
reviewed CSV can be treated as an authoritative exchange margin. Values from
these sources remain *references* even if publication date equals the report day.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

SOURCE_ANNOUNCEMENT = 'https://www.xfqh.cn/dt/233.59196.html'
SOURCE_DATE = '2026-03-09'
# Public broker announcement: add-on in percentage points, NOT an account-specific tariff.
PUBLIC_ADDON_POINTS = {
    'INE': {'sc': 7, 'lu': 7},
    'SHFE': {'fu': 7, 'bu': 5, 'br': 3},
    'DCE': {'pg': 5, 'l': 5, 'v': 5, 'pp': 5, 'eg': 5, 'eb': 5,
            'bz': 5, 'jm': 3, 'p': 3, 'm': 3, 'a': 3, 'b': 3},
    'CZCE': {'ma': 5, 'ta': 5, 'px': 5, 'pl': 5, 'pf': 5,
             'pr': 5, 'sh': 5, 'ur': 5},
}


def published_addon_points(exchange: str, variety: str, day: str) -> int | None:
    """Historical, labelled public reference, not proof still effective today."""
    if str(day).replace('-', '') < '20260309':
        return None
    return PUBLIC_ADDON_POINTS.get(exchange.upper(), {}).get(variety.lower())


def _rows(frame: Any) -> list[dict]:
    if frame is None or getattr(frame, 'empty', False):
        return []
    if hasattr(frame, 'to_dict'):
        return frame.to_dict(orient='records')
    return [dict(r) for r in frame]


def _contract(value: Any) -> str:
    s = str(value or '').strip().lower().replace(' ', '')
    return s if re.fullmatch(r'[a-z]{1,3}\d{3,4}', s) else ''


def _pct(value: Any) -> float | None:
    """Strict percent parser; never guess ambiguous text or negative rates."""
    if value is None or isinstance(value, bool):
        return None
    s = str(value).strip()
    if s.endswith('%'):
        s = s[:-1].strip()
        try: pct = float(s)
        except ValueError: return None
    else:
        try: v = float(s)
        except ValueError: return None
        pct = v * 100 if 0 < v < 1 else v
    if not (0 < pct <= 100):
        return None
    return round(pct, 6)


def fetch_czce_reference(day: str, ak_module: Any = None) -> dict[str, dict]:
    """CZCE public contract-reference table for requested date; not settled margins."""
    if ak_module is None:
        import akshare as ak_module
    frame = ak_module.futures_contract_info_czce(date=day)
    res = {}
    for r in _rows(frame):
        code = _contract(r.get('合约代码'))
        margin = _pct(r.get('交易保证金率'))
        if code and margin is not None:
            res[code] = {
                'long': margin, 'short': margin, 'reference_only': True,
                'origin': f'郑商所合约参考数据（请求日期 {day}，非逐日结算确认）',
                'reference_date': day,
            }
    return res


def fetch_dce_reference(day: str, ak_module: Any = None) -> dict[str, dict]:
    """DCE third-party dated rows. Provider margin category can differ from exchange."""
    if ak_module is None:
        import akshare as ak_module
    frame = ak_module.futures_comm_js(date=day)
    res = {}
    for r in _rows(frame):
        market = str(r.get('交易所') or '').strip().lower()
        if '大连' not in market and market != 'dce':
            continue
        row_day = str(r.get('日期') or '').replace('-', '').replace('/', '').strip()
        if row_day != day:
            continue  # Explicitly reject stale third-party data.
        code = _contract(r.get('合约代码'))
        buy = _pct(r.get('保证金/买开'))
        sell = _pct(r.get('保证金/卖开'))
        if code and (buy is not None or sell is not None):
            res[code] = {
                'long': buy, 'short': sell, 'reference_only': True,
                'origin': f'第三方行情页 {day} 保证金参考（非交易所/先锋已核验标准）',
                'reference_date': day,
            }
    return res