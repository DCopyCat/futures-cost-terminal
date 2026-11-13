"""SO sunflower-oil futures listing parameters, sourced from CZCE 2026 announcements.

These are historical LAUNCH terms (not a real-time margin/fee quote).
No broker-specific fee is implied. Never make up futures settlement prices or OI.
"""
from __future__ import annotations

from datetime import date

EXCHANGE = 'CZCE'
VARIETY = 'so'
NAME = '葵花籽油'
FIRST_LISTED = '20261112'
INITIAL_CONTRACTS = ('so2705', 'so2707', 'so2709', 'so2711')
MULTIPLIER = 20.0
TICK_SIZE = 1.0
EXCHANGE_INITIAL_MARGIN_PCT = 8.0
EXCHANGE_FEE_PERMYRIAD = 1.0
FIRST_DAY_REFERENCE_PRICE = 10000.0  #挂牌基准价, NOT settlement
DAILY_LIMIT_PCT_LISTING = 7.0
FIRST_DAY_LIMIT_PCT = 14.0
ANNOUNCEMENT_DATE = '2026-11-06'
FEE_ANNOUNCEMENT_URL = 'https://www.czce.com.cn/cn/gyjys/jysdt/ggytz/webinfo/2026/11/44faa39c5e8c44ab9de6fd443cb84bbf.htm'
LISTING_ANNOUNCEMENT_URL = 'https://www.xzfutures.com/article/10126581/index.html'
CONTRACT_SPEC_URL = 'https://finance.eastmoney.com/a/202611113928234610.html'
REFERENCE_PRICE_SOURCE_URL = 'https://www.zjncf.com.cn/ajax/ajaxExchange'


def is_initial_so_contract(exchange: str, contract: str, trade_date: str) -> bool:
    """Scope official initial listing references to the four announced contracts,
    on or after the actual launch. Later exchange revisions require rechecking.
    """
    date_key = str(trade_date or '').replace('-', '').replace('/', '')[:8]
    return (str(exchange).upper() == EXCHANGE
            and str(contract).lower() in INITIAL_CONTRACTS
            and len(date_key) == 8 and date_key.isdigit()
            and date_key >= FIRST_LISTED)


def listing_contract_rows() -> list[dict]:
    return [{
        'exchange': EXCHANGE, 'contract': symbol.upper(), 'variety': VARIETY,
        'variety_name': NAME, 'listed_at': '2026-11-12',
        'multiplier': MULTIPLIER, 'tick_size': TICK_SIZE,
        'value_per_tick': MULTIPLIER * TICK_SIZE,
        'exchange_margin_listing_pct': EXCHANGE_INITIAL_MARGIN_PCT,
        'exchange_open_fee_permyriad': EXCHANGE_FEE_PERMYRIAD,
        'exchange_close_today_fee_permyriad': EXCHANGE_FEE_PERMYRIAD,
        'first_day_reference_price': FIRST_DAY_REFERENCE_PRICE,
        'first_day_limit_pct': FIRST_DAY_LIMIT_PCT,
        'listing_period_limit_pct': DAILY_LIMIT_PCT_LISTING,
        'fee_source': FEE_ANNOUNCEMENT_URL,
        'margin_source': LISTING_ANNOUNCEMENT_URL,
        'broker_default_fee_status': '先锋公司默认收费待核',
        'broker_margin_status': '先锋公司保证金待核',
    } for symbol in INITIAL_CONTRACTS]


def official_exchange_fee_record(exchange: str, contract: str, trade_date: str) -> dict | None:
    """CZCE published general trading and close-today rate of 1/10000.

    Ordinary close-yesterday is the general trading fee (same 1/10000).
    No exchange settlement or customer rate is implied.
    """
    if not is_initial_so_contract(exchange, contract, trade_date):
        return None
    return {
        'exchange': EXCHANGE, 'contract': str(contract).lower(), 'variety': VARIETY,
        'open_rate_permyriad': EXCHANGE_FEE_PERMYRIAD,
        'open_fixed_yuan': None,
        'close_yesterday_rate_permyriad': EXCHANGE_FEE_PERMYRIAD,
        'close_yesterday_fixed_yuan': None,
        'close_today_rate_permyriad': EXCHANGE_FEE_PERMYRIAD,
        'close_today_fixed_yuan': None,
        'fee_updated_at': ANNOUNCEMENT_DATE,
        'source_name': '郑商所郑商函〔2026〕1014号挂牌费率公告（需核后续调整）',
        'source_url': FEE_ANNOUNCEMENT_URL,
        'retrieved_at_utc': '',
    }
