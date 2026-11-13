"""Visible margin fallback labels, not audited margin substitutions.

All fields here are VIEW ONLY. Never overwrite the verified exchange/company
margin values used by downstream reports or account calculations.
"""
from __future__ import annotations

import math
from typing import Any


def _pct(value: Any) -> float | None:
    if value is None or str(value).strip() in ('', 'None', 'nan', 'NaN'):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and 0 < number <= 100 else None


def _fmt_rate(number: float | None, status: str) -> str:
    if number is None:
        return '待核（无历史资料）'
    number_str = f'{number:g}'
    return f'{number_str}%（{status}）'


def _fmt_one_lot(number: float | None, notional: float | None, status: str) -> str:
    if number is None or notional is None:
        return '待核（无可用参数）'
    return f'{notional * number / 100:,.2f} 元（{status}）'


def _pick_exchange(record: dict, side: str) -> tuple[float | None, str, str]:
    rate = _pct(record.get(f'exchange_margin_{side}_pct'))
    if rate is not None:
        return rate, '当前接口/核验值', str(record.get('margin_source') or '当日报告参数，需核对交易所公告')
    rate = _pct(record.get(f'exchange_margin_reference_{side}_pct'))
    if rate is not None:
        return rate, '公开参考', str(record.get('margin_reference_source') or '非交易所已核验结算值')
    rate = _pct(record.get(f'historical_exchange_{side}_pct'))
    if rate is not None:
        basis = str(record.get('historical_exchange_basis') or '')
        as_of = basis[:10] if len(basis) >= 10 else '旧档'
        return rate, f'历史 {as_of}', basis
    return None, '待核', '当前未取得核验参数，历史参考库也无对应品种'


def _pick_company(record: dict, side: str) -> tuple[float | None, str, str]:
    rate = _pct(record.get(f'company_margin_{side}_pct'))
    origin = str(record.get('company_margin_source') or '')
    if rate is not None:
        # Legacy override is not verified for the report trade date.
        label = '旧手工值待核' if '旧公司覆盖项' in origin else '公司录入待账户核验'
        return rate, label, origin or '公司参数需核对账户适用范围'
    rate = _pct(record.get(f'historical_company_{side}_pct'))
    if rate is not None:
        basis = str(record.get('historical_company_basis') or '')
        as_of = basis[:10] if len(basis) >= 10 else '旧档'
        return rate, f'历史 {as_of}', basis
    rate = _pct(record.get(f'company_margin_notice_reference_{side}_pct'))
    if rate is not None:
        return rate, '历史公告推算', str(record.get('company_notice_reference_source') or '非当日公司核定值')
    return None, '待核', '当前未取得公司核验参数，历史参考库也无对应品种'


def enrich_margin_display(record: dict) -> dict:
    """Return extra visible labels with provenance and zero changes to raw rates."""
    result: dict[str, str] = {}
    try:
        notional = float(record.get('notional'))
        if not (math.isfinite(notional) and notional > 0):
            notional = None
    except (ValueError, TypeError):
        notional = None
    for prefix, picker in [('exchange', _pick_exchange), ('company', _pick_company)]:
        long_rate, long_status, long_source = picker(record, 'long')
        short_rate, short_status, short_source = picker(record, 'short')
        result[f'display_{prefix}_margin_long_pct'] = _fmt_rate(long_rate, long_status)
        result[f'display_{prefix}_margin_short_pct'] = _fmt_rate(short_rate, short_status)
        result[f'display_{prefix}_margin_one_lot'] = _fmt_one_lot(long_rate, notional, long_status)
        result[f'display_{prefix}_margin_status'] = (long_status if long_status == short_status
                                                     else f'多:{long_status} / 空:{short_status}')
        result[f'display_{prefix}_margin_source'] = long_source if long_source == short_source else f'多:{long_source}；空:{short_source}'
    return result