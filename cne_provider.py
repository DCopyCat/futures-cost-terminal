"""CNEquity public futures_bars -> existing Futures Cost Terminal adapter.

CNEquity is a *local data lake*, not a guarantee that today's records exist.
This adapter only reads published contracts, never manufactures prices or margins.
Official fields: symbol, exchange, trade_date, product, settle, open_interest,
volume, source, data_version. It does NOT supply a validated fee/margin schedule.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
import re
from typing import Any, Callable

CNE_TO_LOCAL = {"SHF":"SHFE", "INE":"INE", "DCE":"DCE", "CZC":"CZCE", "GFE":"GFEX", "CFE":"CFFEX"}
LOCAL_TO_CNE = {v:k for k,v in CNE_TO_LOCAL.items()}
CODE_RE = re.compile(r"^([A-Z]{1,3})(\d{4})\.([A-Z]{3})$")


def _rows(frame: Any) -> list[dict]:
    if frame is None:
        return []
    if hasattr(frame, 'to_dicts'):
        return frame.to_dicts()  # polars
    if hasattr(frame, 'to_dict'):
        return frame.to_dict(orient='records')  # pandas
    return list(frame)


def _yyyymmdd(value: Any) -> str:
    if isinstance(value, (date,)):
        return value.strftime('%Y%m%d')
    text = str(value or '').strip().replace('-', '').replace('/', '')
    return text[:8] if re.fullmatch(r'\d{8}.*',text) else ''


def parse_bars(frame: Any, start: str, end: str) -> tuple[dict[str,list[dict]],dict]:
    """Validate schema and normalise CNE market codes; do not interpolate missing OI."""
    parsed = {m:[] for m in LOCAL_TO_CNE}
    rejected = Counter()
    seen = set()
    by_upstream = Counter()
    date_counts = Counter()
    oi_missing = Counter()
    for item in _rows(frame):
        exch = str(item.get('exchange','')).upper().strip()
        canonical = str(item.get('symbol','')).upper().strip()
        match = CODE_RE.fullmatch(canonical)
        day = _yyyymmdd(item.get('trade_date'))
        if not match or exch not in CNE_TO_LOCAL or match.group(3)!=exch or not start<=day<=end:
            rejected['非法合约/交易日/交易所'] += 1
            continue
        try:
            settle=float(item.get('settle'))
            oi=item.get('open_interest')
            volume=item.get('volume')
            oi=float(oi) if oi is not None else None
            volume=float(volume) if volume is not None else None
        except (ValueError,TypeError):
            rejected['非法结算价/持仓量'] += 1
            continue
        if not 0<settle<1e10 or (oi is not None and oi<0) or (volume is not None and volume<0):
            rejected['非法数值'] += 1
            continue
        key=(canonical,day)
        if key in seen:
            rejected['重复主键'] += 1
            continue
        seen.add(key)
        local_market=CNE_TO_LOCAL[exch]
        upstream = str(item.get('source','')).strip()
        by_upstream[(local_market,upstream)] += 1
        date_counts[(local_market,day)] += 1
        if oi is None or oi <= 0: oi_missing[local_market] += 1
        parsed[local_market].append({
            'symbol':match.group(1).lower()+match.group(2),
            'date':day,'settle':settle,'open_interest':oi,'volume':volume,
            'variety':match.group(1).lower(),
            'origin':('CNEquity futures_bars'+ (f'（上游:{upstream}）' if upstream else '')),
        })
    return parsed, {'accepted':sum(len(v) for v in parsed.values()), 'rejected':dict(rejected),
                    'by_exchange':{k:len(v) for k,v in parsed.items()},
                    'upstream':{f'{m}:{src or "unknown"}':cnt for (m,src),cnt in by_upstream.items()},
                    'latest_dates':{m:max((d for (e,d) in date_counts if e==m),default=None) for m in parsed},
                    'by_exchange_day':{f'{e}:{d}':n for (e,d),n in date_counts.items()},
                    'oi_missing_or_zero':dict(oi_missing),
                    'limitations':['DCE 新浪源不能证明无成交合约覆盖完整'] if parsed['DCE'] else []}


class CNEquityFuturesAPI:
    """Read the latest available CNE published parquet via documented load().

    Exchange margin schedules are still routed to AKShare independently. Failure
    of that separate source must not stop the futures price report.
    """
    daily_source='CNEquity futures_bars（本地已发布数据，含上游来源）'
    enable_public_margin_reference = True
    def __init__(self, config_path: Path, loader: Callable|None=None, margin_api: Any=None):
        self.config_path = Path(config_path)
        self._loader = loader
        self._margin_api = margin_api
        self._cache_key = None
        self._cache = {}
        self.quality = {}

    def _load(self,start:str,end:str):
        if not self.config_path.exists() and self._loader is None:
            raise RuntimeError(f'期货湖配置文件未建立: {self.config_path}；请先点击「采集并生成日报」。')
        if self._loader is None:
            try:
                from cnequity.query import load
                from cnequity.config import load_config
                cfg=load_config(str(self.config_path))
                frame=load('futures_bars', config=cfg, start=f'{start[:4]}-{start[4:6]}-{start[6:]}',
                           end=f'{end[:4]}-{end[4:6]}-{end[6:]}')
            except Exception as e:
                raise RuntimeError(f'CNEquity 本地湖读取失败（检查首次采集及已发布数据）：{type(e).__name__}: {e}') from e
        else:
            frame=self._loader(start,end)
        self._cache,self.quality=parse_bars(frame,start,end)
        self._cache_key=(start,end)

    def get_futures_daily(self,start_date:str,end_date:str,market:str):
        if self._cache_key != (start_date,end_date):
            self._load(start_date,end_date)
        return self._cache.get(market,[])

    def futures_settle(self,date:str,market:str):
        if market=='DCE':
            raise RuntimeError('CNEquity 尚未提供大商所逐日已验收保证金表；需另外使用核实来源。')
        if self._margin_api is not None:
            return self._margin_api.futures_settle(date=date,market=market)
        try:
            import akshare as ak
            return ak.futures_settle(date=date,market=market)
        except Exception as ex:
            raise RuntimeError(f'AKShare 结算参数不可用（与 CNEquity 日行情独立）：{type(ex).__name__}: {ex}') from ex
