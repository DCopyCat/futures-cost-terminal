"""Strict, local-only, user-reviewed day-specific exchange and broker fee inputs.

No anonymous free site is assumed to be an authoritative exchange margin schedule.
Importers validate format and scope; they cannot verify the truth of user-provided source notes.
"""
from __future__ import annotations

import csv
import io
import os
import re
import tempfile
from datetime import date
from pathlib import Path

EXCHANGES = {'SHFE','INE','DCE','CZCE','CFFEX','GFEX'}
SYMBOL = re.compile(r'^[a-z]{1,3}\d{3,4}$')
VARIETY = re.compile(r'^[a-z]{1,3}$')


def _day(s: str) -> str:
    text = str(s or '').strip().replace('-', '')
    if not re.fullmatch(r'20\d{6}', text):
        raise ValueError(f'日期格式不合法：{s!r}（需 YYYYMMDD）')
    try:
        date.fromisoformat(f'{text[:4]}-{text[4:6]}-{text[6:]}')
    except ValueError as exc:
        raise ValueError('无效日期：'+text) from exc
    return text


def _decimal(s: str, *, name: str, max_value: float) -> float:
    try:
        x = float(str(s).strip())
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{name} 必须是有效数字') from exc
    if not (0 <= x <= max_value):
        raise ValueError(f'{name} 必须在 0 到 {max_value} 之间')
    return x


def _rows(raw: bytes, required: set[str]):
    try:
        content = raw.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('CSV 请保存为 UTF-8 编码') from exc
    reader = csv.DictReader(io.StringIO(content))
    if not required.issubset(set(reader.fieldnames or [])):
        raise ValueError('CSV 缺少字段：'+','.join(sorted(required-set(reader.fieldnames or []))))
    parsed = list(reader)
    if not parsed:
        raise ValueError('CSV 没有数据行')
    return parsed


def parse_exchange_margin_csv(raw: bytes) -> tuple[str, dict[str, dict[str, dict]]]:
    """Exact trading-day, contract-specific long/short margin in *percent* units.

    Returns day and exchange->contract->params, for all six markets. Blank side is
    acceptable but zero percent is not: missing remains missing rather than 0%.
    """
    needed={'trade_date','exchange','contract','long_margin_pct','short_margin_pct','source_note'}
    rows=_rows(raw,needed)
    seen=set();days=set();result={m:{} for m in EXCHANGES}
    for n,row in enumerate(rows,2):
        day=_day(row['trade_date']); days.add(day)
        exch=str(row['exchange']).strip().upper()
        sym=str(row['contract']).strip().lower()
        note=str(row['source_note'] or '').strip()
        if exch not in EXCHANGES or not SYMBOL.fullmatch(sym) or not note:
            raise ValueError(f'第 {n} 行的交易所、具体合约或来源说明无效')
        if (exch,sym) in seen:
            raise ValueError(f'同一交易所合约重复：{exch}/{sym}')
        seen.add((exch,sym))
        margins=[]
        for side in ('long_margin_pct','short_margin_pct'):
            val=str(row[side] or '').strip()
            margins.append(None if not val else _decimal(val,name=side,max_value=100))
        if all(m is None for m in margins) or any(m==0 for m in margins if m is not None):
            raise ValueError(f'{exch}/{sym} 必须至少给出一侧非零保证金率')
        result[exch][sym]={
            'long':margins[0], 'short':margins[1],
            'raw_open_fee':'', 'raw_close_fee':'',
            'origin':f'人工核验的 {day} 合约保证金 CSV：{note[:120]}'
        }
    if len(days)!=1:
        raise ValueError('每次仅能导入同一交易日参数，不能跨日混合')
    return next(iter(days)),result


def _atomic_write(path: Path, content: bytes):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False,prefix='.stage_',suffix='.tmp') as t:
        t.write(content)
        tmp=Path(t.name)
    try:
        os.replace(tmp,path)
    finally:
        tmp.unlink(missing_ok=True)


def install_exchange_margin_csv(raw: bytes, data_dir: Path) -> tuple[str,int]:
    day,parsed=parse_exchange_margin_csv(raw)
    count=sum(map(len,parsed.values()))
    _atomic_write(data_dir/f'exchange_margin_{day}.csv',raw)
    return day,count


def load_exchange_margin(data_dir: Path, day: str) -> dict[str,dict[str,dict]]:
    path=data_dir/f'exchange_margin_{day}.csv'
    if not path.exists():
        return {}
    actual, rows=parse_exchange_margin_csv(path.read_bytes())
    if actual!=day:
        raise ValueError('保证金 CSV 文件名与内部交易日期不一致')
    return rows


def parse_company_close_today_csv(raw: bytes) -> list[dict]:
    """Only documented, independently checked default-account close-today overrides.

    No per-client fields: account pricing requires the broker settlement system.
    """
    fields={'exchange','variety','contract','close_today_fee_type','close_today_fee_value',
            'effective_from','verified_at','source_note'}
    rows=_rows(raw,fields)
    result=[];seen=set()
    for n,row in enumerate(rows,2):
        exch=str(row['exchange']).strip().upper()
        variety=str(row['variety']).strip().lower()
        contract=str(row['contract'] or '').strip().lower()
        kind=str(row['close_today_fee_type']).strip().upper()
        source=str(row['source_note'] or '').strip()
        effective=_day(row['effective_from']);verified=_day(row['verified_at'])
        if (exch not in EXCHANGES or not VARIETY.fullmatch(variety) or
            (contract and (not SYMBOL.fullmatch(contract) or not contract.startswith(variety))) or
            kind not in {'RATE','FIXED'} or not source):
            raise ValueError(f'第 {n} 行交易所、品种、合约、计费方式或来源说明非法')
        value=_decimal(row['close_today_fee_value'],name='平今费率',max_value=1 if kind=='RATE' else 100000)
        key=(exch,variety,contract,effective)
        if key in seen:raise ValueError(f'重复的平今规则：{key}')
        seen.add(key)
        result.append({
            'exchange':exch,'variety':variety,'contract':contract,
            'close_today_fee_type':kind,'close_today_fee_value':str(value),
            'effective_from':f'{effective[:4]}-{effective[4:6]}-{effective[6:]}',
            'verified_at':f'{verified[:4]}-{verified[4:6]}-{verified[6:]}',
            'source_note':source[:200]
        })
    return result


def merge_company_close_today_csv(raw: bytes, data_dir: Path) -> int:
    """Upsert reviewed fee rows preserving existing broker override columns."""
    new=parse_company_close_today_csv(raw)
    target=data_dir/'company_overrides.csv'
    current=[]
    columns=['exchange','variety','contract','open_fee_type','open_fee_value',
             'close_yesterday_fee_type','close_yesterday_fee_value',
             'close_today_fee_type','close_today_fee_value',
             'margin_long_pct','margin_short_pct','effective_from','verified_at','source_note']
    if target.exists():
        with target.open(encoding='utf-8-sig',newline='') as fp:
            reader=csv.DictReader(fp)
            current=list(reader)
            columns=list(dict.fromkeys([*(reader.fieldnames or []),*columns]))
    def ident(row):
        return (str(row.get('exchange','')).upper(),str(row.get('variety','')).lower(),
                str(row.get('contract','')).lower(),_day(row.get('effective_from','')))
    keys={ident(r):idx for idx,r in enumerate(current) if r.get('effective_from')}
    for item in new:
        key=ident(item)
        if key in keys:
            current[keys[key]].update(item)
        else:
            current.append(item)
    dest=io.StringIO(newline='')
    writer=csv.DictWriter(dest,fieldnames=columns,extrasaction='ignore',lineterminator='\n')
    writer.writeheader();writer.writerows(current)
    _atomic_write(target, ('\ufeff'+dest.getvalue()).encode('utf-8'))
    return len(new)
