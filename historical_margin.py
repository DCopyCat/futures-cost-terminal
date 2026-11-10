"""Dated historical margin references. NEVER use for current settlement/required margin.

Data inputs come from prior user-provided 2026 July/August exchange-margin workbook
and the 2026-03-20 Pioneer Futures public company-margin schedule.

Percent units are 7.0 for 7%, never decimals 0.07. A variety-level
mode derived from historical contracts is descriptive, not a contract quote.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_DATA_DIR = Path(__file__).resolve().parent / 'data'


def _read(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding='utf-8-sig', newline='') as fh:
        return list(csv.DictReader(fh))


def _pct(raw: Any) -> float | None:
    try:
        number = float(raw)
    except (ValueError, TypeError):
        return None
    return number if 0 < number <= 100 else None


@lru_cache(maxsize=8)
def _exchange_index(path: str):
    exact: dict[tuple[str, str], dict] = {}
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in _read(Path(path)):
        ex = row.get('exchange', '').upper().strip()
        var = row.get('variety', '').lower().strip()
        sym = row.get('contract', '').lower().strip()
        if not (ex and var):
            continue
        long = _pct(row.get('long_margin_pct'))
        short = _pct(row.get('short_margin_pct'))
        if long is None or short is None:
            continue
        item = {**row, 'long': long, 'short': short}
        groups[(ex, var)].append(item)
        if sym:
            exact[(ex, sym)] = item
    return exact, groups


def historical_exchange_reference(exchange: str, variety: str, contract: str = '',
                                  data_dir: Path | None = None) -> dict:
    """As-of snapshot, exact contract if present, otherwise historical variety mode.

    Never infer current-day applicability from a same-month contract code.
    The historical mode has no legal/current pricing authority.
    """
    data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    exact, groups = _exchange_index(str(data_dir/'historical_exchange_margin.csv'))
    exchange = str(exchange or '').upper().strip()
    variety = str(variety or '').lower().strip()
    contract = str(contract or '').lower().strip()
    sample = exact.get((exchange, contract)) if contract else None
    rows = groups.get((exchange, variety), [])
    if not rows:
        return {}
    if sample is None:
        frequencies = Counter((r['long'], r['short']) for r in rows)
        # Prefer the typical historical schedule rather than an expiring, delivery
        # month or one-off special contract. Do not claim contract applicability.
        (long, short), n = sorted(frequencies.items(), key=lambda z: (-z[1], z[0]))[0]
        sample = next(r for r in rows if (r['long'], r['short']) == (long, short))
        scope = 'VARIETY_BASE' if not sample.get('contract') else 'VARIETY_MODE'
    else:
        long, short = sample['long'], sample['short']
        n = 1
        scope = 'ARCHIVE_CONTRACT'
    lvals = [r['long'] for r in rows]
    svals = [r['short'] for r in rows]
    return {
        'long': long, 'short': short,
        'as_of': sample.get('as_of') or '',
        'scope': scope,
        'coverage': len(rows),
        'mode_support': n,
        'long_range': (min(lvals), max(lvals)),
        'short_range': (min(svals), max(svals)),
        'source_id': sample.get('source_id') or '',
        'source_url': sample.get('source_url') or '',
        'original_contract': sample.get('original_contract') or '',
        'explanation': ('历史相同合约快照，已过期；不可代替今天的结算率' if scope == 'ARCHIVE_CONTRACT'
                        else ('历史品种级基准，未覆盖当前合约特殊提保' if scope == 'VARIETY_BASE'
                              else f'历史同品种最常见保证金样本 {n}/{len(rows)}，未证明适用于当前合约')),
    }


@lru_cache(maxsize=8)
def _company_index(path: str):
    result = {}
    for r in _read(Path(path)):
        ex = r.get('exchange','').upper().strip()
        var = r.get('variety','').lower().strip()
        long = _pct(r.get('company_long_margin_pct'))
        short = _pct(r.get('company_short_margin_pct'))
        if ex and var and long is not None and short is not None:
            result[(ex,var)] = {**r, 'long':long,'short':short}
    return result


def historical_company_reference(exchange: str, variety: str,
                                 data_dir: Path | None = None) -> dict:
    data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    row = _company_index(str(data_dir/'historical_company_margin.csv')).get(
        (str(exchange).upper().strip(), str(variety).lower().strip()))
    if not row:
        return {}
    return {
        'long':row['long'],'short':row['short'],
        'as_of':row['as_of'],'scope':'VARIETY_STANDARD',
        'source_url':row['source_url'],
        'explanation':'先锋期货历史公开日常保证金品种基准；非本交易日确认值，专项合约/优惠/风险提保另行核对',
    }