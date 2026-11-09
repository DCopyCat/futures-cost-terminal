"""Strict dated CSV import for DCE parameters; never assume stale margins are live."""
from __future__ import annotations
import csv
import io
from pathlib import Path
from dce_provider import canon, num, valid_day


def parse_margin_csv(raw: bytes) -> tuple[str,dict[str,dict]]:
    content=raw.decode('utf-8-sig')
    rows=list(csv.DictReader(io.StringIO(content)))
    required={'trade_date','contract','long_margin_pct','short_margin_pct','source_note'}
    if not rows or not required.issubset(set(rows[0])):
        raise ValueError('CSV缺字段，需要 trade_date,contract,long_margin_pct,short_margin_pct,source_note')
    dates=set()
    params={}
    for r in rows:
        day=valid_day(r.get('trade_date'))
        sym=canon(r.get('contract'))
        long=num(r.get('long_margin_pct'))
        short=num(r.get('short_margin_pct'))
        note=str(r.get('source_note') or '').strip()
        if not sym or len(day)!=8 or not note:
            raise ValueError('合约代码、日期或来源说明不合法')
        if long is None and short is None:
            raise ValueError(f'{sym} 多空保证金至少有一个')
        if (long is not None and not 0<long<=100) or (short is not None and not 0<short<=100):
            raise ValueError(f'{sym} 保证金须填写百分数（例如12表示12%）')
        dates.add(day)
        if sym in params:
            raise ValueError('合约代码重复：'+sym)
        params[sym]={'long':long,'short':short,'raw_open_fee':'','raw_close_fee':'',
                     'origin':'用户核验CSV导入：'+note[:120]}
    if len(dates)!=1:
        raise ValueError('一个文件只能包含一个交易日的保证金参数')
    return dates.pop(),params


def load_margin(directory: Path, date: str) -> dict[str,dict]:
    path=directory/('dce_margin_'+date+'.csv')
    if not path.exists(): return {}
    found, data=parse_margin_csv(path.read_bytes())
    return data if found==date else {}


def parse_daily_csv(raw: bytes) -> tuple[str,list[dict]]:
    rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    needed={'trade_date','contract','settlement','open_interest','volume'}
    if not rows or not needed.issubset(set(rows[0])):
        raise ValueError('缺少字段：trade_date,contract,settlement,open_interest,volume')
    from dce_provider import from_daily
    transformed=[]
    for r in rows:
        transformed.append({'trade_date':r['trade_date'],'ts_code':r['contract'],
                            'settle':r['settlement'],'oi':r['open_interest'],'vol':r['volume']})
    dates={valid_day(x['trade_date']) for x in transformed}
    if len(dates)!=1: raise ValueError('只能导入一个交易日')
    date=dates.pop()
    result=from_daily(transformed,date)
    if len(result)!=len(rows):
        raise ValueError('存在非具体期货合约、空结算价或日期不匹配的数据行')
    return date,result


def load_daily(directory: Path, date: str) -> list[dict]:
    path=directory/('dce_daily_'+date+'.csv')
    if not path.exists(): return []
    found,data=parse_daily_csv(path.read_bytes())
    return data if found==date else []
