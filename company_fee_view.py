"""Human-readable brokerage fee tariff labels; amounts are computed by core."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation


def format_company_fee_rule(kind: str | None, raw_value: object) -> str:
    """RATE is a decimal share of notional; FIXED is RMB/lot."""
    kind = str(kind or '').strip().upper()
    try:
        amount = Decimal(str(raw_value).strip())
    except (InvalidOperation, ValueError):
        return '待核'
    if not amount.is_finite() or amount < 0:
        return '待核'
    if kind == 'RATE':
        if amount > 1:
            return '待核'
        val = (amount * Decimal('10000')).normalize()
        return f'成交金额万分之{format(val,"f")}'
    if kind == 'FIXED':
        return f'固定{format(amount.normalize(),"f")}元/手'
    return '待核'


def make_company_default_fee_display(amount: float | None, rule: str, version: str) -> str:
    """Do not invent a one-lot price without settlement notional."""
    if rule == '待核':
        return '待核'
    if amount is None:
        return '待核（缺结算价/乘数）'
    stamp = f'（PDF {version}）' if version and version != '未知' else '（PDF日期待核）'
    return f'¥{amount:,.2f}/手{stamp}'
