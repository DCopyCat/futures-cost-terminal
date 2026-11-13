"""Dated, NON-OFFICIAL exchange-fee references from AKShare futures_comm_info.

The source (9qihuo.com via AKShare) publishes indicative exchange tariffs by
concrete futures contract. Never confuse it with an exchange settlement notice,
account-level broker charges, or an exchange rebate / net profit statement.

Fee rate units are WAN-FEN-ZHI: raw 1.0 == one ten-thousandth (0.0001).
Do not use the source site's spot quote in calculations: compute all RMB/lot
fees using the report's own prior-trading-day settlement notional.
"""
from __future__ import annotations

import csv
import math
import os
import re
import tempfile
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any

SOURCE_URL = 'https://www.9qihuo.com/qihuoshouxufei'
SOURCE_NAME = 'AKShare futures_comm_info / 九期网（第三方交易所费参考）'
SNAPSHOT_NAME = 'exchange_fee_reference.csv'
FIELDS = ['exchange','contract','variety','open_rate_permyriad','open_fixed_yuan',
          'close_yesterday_rate_permyriad','close_yesterday_fixed_yuan',
          'close_today_rate_permyriad','close_today_fixed_yuan',
          'fee_updated_at','source_name','source_url','retrieved_at_utc']
EXCHANGE_NAMES = {
    '上海期货交易所':'SHFE','上海交易所':'SHFE','上期所':'SHFE','SHFE':'SHFE',
    '大连商品交易所':'DCE','大商所':'DCE','DCE':'DCE',
    '郑州商品交易所':'CZCE','郑商所':'CZCE','CZCE':'CZCE','CZC':'CZCE',
    '上海国际能源交易中心':'INE','上海能源交易中心':'INE','能源中心':'INE','INE':'INE',
    '中国金融期货交易所':'CFFEX','中金所':'CFFEX','CFFEX':'CFFEX','CFE':'CFFEX',
    '广州期货交易所':'GFEX','广州交易所':'GFEX','广期所':'GFEX','GFEX':'GFEX',
}
CONTRACT_RE = re.compile(r'^([a-z]{1,3})(\d{3,4})$')


def _number(value: Any) -> float | None:
    if value is None or isinstance(value,bool):return None
    try:
        if isinstance(value,str):
            value = value.strip().replace(',','')
            if not value or value in {'—','--','-','nan','NaN','None','null','/'}:
                return None
            value = re.sub(r'(?:元/手|元)$','',value).strip()
        n = float(value)
    except (TypeError,ValueError,OverflowError):
        return None
    return n if math.isfinite(n) and 0<=n<=1000000 else None


def _rate(value: Any) -> float | None:
    n=_number(value)
    # Rates are in permyriad, NOT fractions or percentages.
    return n if n is not None and n<=100 else None


def _date_of(value: Any) -> str:
    s=str(value or '').strip()
    if re.fullmatch(r'20\d{6}',s):
        s=s[:4]+'-'+s[4:6]+'-'+s[6:]
    m=re.match(r'^(20\d\d)-(\d\d)-(\d\d)',s)
    if not m:return ''
    try:
        date.fromisoformat(m.group(0))
    except ValueError:
        return ''
    return m.group(0)


def _kind(row: dict, side: str) -> tuple[float | None,float | None]:
    if side=='开仓':v='开仓'
    elif side=='平昨':v='平昨'
    elif side=='平今':v='平今'
    else:raise ValueError(side)
    return (_rate(row.get(f'手续费标准-{v}-万分之')),
            _number(row.get(f'手续费标准-{v}-元')))


def normalize_reference_rows(raw_rows: list[dict], *, retrieved_at_utc: str = '') -> list[dict]:
    """Never repair unknown units with guesses or substitute open for close-today."""
    if not retrieved_at_utc:
        retrieved_at_utc=datetime.now(timezone.utc).isoformat(timespec='seconds')
    unique:dict[tuple[str,str],dict|None] = {}
    for raw in raw_rows:
        ex = EXCHANGE_NAMES.get(str(raw.get('交易所名称') or raw.get('交易所') or '').strip())
        sym=str(raw.get('合约代码') or '').strip().lower().replace(' ','')
        m=CONTRACT_RE.fullmatch(sym)
        if not ex or not m:continue
        params=[_kind(raw,s) for s in ('开仓','平昨','平今')]
        if all(rate is None and fixed is None for rate,fixed in params):continue
        if any(rate is not None and rate<0 or fixed is not None and fixed<0 for rate,fixed in params):continue
        record={'exchange':ex,'contract':sym,'variety':m.group(1),
                'open_rate_permyriad':params[0][0],'open_fixed_yuan':params[0][1],
                'close_yesterday_rate_permyriad':params[1][0],'close_yesterday_fixed_yuan':params[1][1],
                'close_today_rate_permyriad':params[2][0],'close_today_fixed_yuan':params[2][1],
                'fee_updated_at':_date_of(raw.get('手续费更新时间')),
                'source_name':SOURCE_NAME,'source_url':SOURCE_URL,'retrieved_at_utc':retrieved_at_utc}
        key=(ex,sym)
        old=unique.get(key,'NOT_SEEN')
        if old=='NOT_SEEN':unique[key]=record
        elif old is None:continue
        elif all(old.get(k)==record.get(k) for k in FIELDS if k not in {'retrieved_at_utc'}):continue
        else:
            # Differing duplicated contracts cannot be assigned a deterministic fee.
            unique[key]=None
    return sorted((x for x in unique.values() if x is not None),key=lambda v:(v['exchange'],v['contract']))


def write_snapshot(path: Path, rows: list[dict]) -> None:
    """Atomic data snapshot; don't destroy the last good cache on failed fetch."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8-sig',newline='',
        dir=path.parent,prefix='.exchange_fee_',suffix='.tmp',delete=False) as t:
        writer=csv.DictWriter(t,fieldnames=FIELDS,extrasaction='ignore',lineterminator='\n')
        writer.writeheader();writer.writerows(rows)
        name=t.name
    try:os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def load_snapshot(path: Path) -> list[dict]:
    path=Path(path)
    if not path.is_file():
        backup=path.parent/'exchange_fee_seed_20261110.csv'
        if not backup.is_file():return []
        path=backup
    try:
        with path.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f)
            if not set(FIELDS).issubset(reader.fieldnames or []):return []
            rows=list(reader)
    except (OSError,UnicodeError,csv.Error):return []
    verified=[]
    for row in rows:
        market=row.get('exchange','')
        code=row.get('contract','')
        if market not in ('DCE','SHFE','INE','CZCE','GFEX','CFFEX') or not CONTRACT_RE.fullmatch(code):continue
        parsed={**row}
        for k in FIELDS:
            if k.endswith(('_rate_permyriad','_fixed_yuan')):
                parsed[k]=_rate(row[k]) if k.endswith('_rate_permyriad') else _number(row[k])
        verified.append(parsed)
    return verified


def refresh_from_akshare(path: Path, *, loader=None, min_contracts:int=80, min_markets:int=5) -> dict:
    """Download full cross-market reference in one call, with strict coverage gate.

    Upstream source is independently sourced and NOT the exchanges' own API.
    This function is called only on an explicit Streamlit refresh, not in core.
    """
    if loader is None:
        import akshare as ak
        loader=lambda:ak.futures_comm_info(symbol='所有')
    frame=loader()
    if hasattr(frame,'to_dict'):rows=frame.to_dict(orient='records')
    else:rows=list(frame)
    parsed=normalize_reference_rows(rows)
    by_market={e:sum(x['exchange']==e for x in parsed) for e in {'SHFE','INE','DCE','CZCE','GFEX','CFFEX'}}
    if len(parsed)<min_contracts or len([x for x in by_market.values() if x])<min_markets:
        raise RuntimeError(f'第三方费率源覆盖不足（{len(parsed)} 合约，{len([x for x in by_market.values() if x])} 市场），未覆盖旧快照')
    write_snapshot(path,parsed)
    days=[r['fee_updated_at'] for r in parsed if r['fee_updated_at']]
    return {'contracts':len(parsed),'varieties':len({(x['exchange'],x['variety']) for x in parsed}),
            'markets':by_market,'source':SOURCE_NAME,
            'updated_min':min(days) if days else '', 'updated_max':max(days) if days else ''}


def _contract_match(rows:list[dict], exchange:str, contract:str)->dict|None:
    exchange=str(exchange).upper();contract=str(contract).lower()
    candidates=[r for r in rows if r.get('exchange')==exchange and r.get('contract')==contract]
    if len(candidates)==1:return candidates[0]
    if candidates:return None
    # Zhengzhou 3-digit exchange codes (MA701) vs 4-digit report contracts (ma2701).
    if exchange=='CZCE' and CONTRACT_RE.fullmatch(contract) and len(CONTRACT_RE.fullmatch(contract).group(2))==4:
        suffix=contract[-3:]
        family=CONTRACT_RE.fullmatch(contract).group(1)
        candidates=[r for r in rows if r.get('exchange')=='CZCE' and r.get('contract')==family+suffix]
        if len(candidates)==1:return candidates[0]
    return None


def amount_for_side(record:dict, side:str, notional:float|None)->float|None:
    p={ 'open':'open','close_yesterday':'close_yesterday','close_today':'close_today' }.get(side)
    if not p:raise ValueError(side)
    fixed=_number(record.get(p+'_fixed_yuan'))
    rate=_rate(record.get(p+'_rate_permyriad'))
    if fixed is None and rate is None:return None
    if rate is not None and notional is None:return None
    amount=(fixed or 0.0)+(notional or 0.0)*(rate or 0.0)/10000
    return round(amount,4)


def _money_text(value:float)->str:
    # Conventional half-up display for customer-facing RMB (base remains 4dp).
    rounded=Decimal(str(value)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
    return f'{rounded:,.2f}'


def _as_money(value:float|None)->str:
    return f'¥{_money_text(value)}/手' if value is not None else '待核'


def _side_rule(record:dict, side:str)->str:
    r=_rate(record.get(side+'_rate_permyriad'))
    fixed=_number(record.get(side+'_fixed_yuan'))
    if r is None and fixed is None:return '待核'
    parts=[]
    if r is not None and r!=0:parts.append(f'万分之{r:g}')
    if fixed is not None and fixed!=0:parts.append(f'{fixed:g}元/手')
    if not parts:return '0元/手（此来源标为免收）'
    return ' + '.join(parts)


def compare_exchange_vs_broker(rows:list[dict], exchange:str, contract:str,
                               report_date:str, notional:float|None,
                               broker_default:float|None)->dict:
    """The *gross difference* is not broker profit, net revenue, nor a customer quote."""
    out={'exchange_fee_reference_open':None,'exchange_fee_reference_close_yesterday':None,
         'exchange_fee_reference_close_today':None,'exchange_fee_reference_display':'待核（无匹配合约第三方数据）',
         'exchange_fee_reference_open_rule':'待核','exchange_fee_reference_close_today_rule':'待核',
         'exchange_fee_reference_updated':'','exchange_fee_reference_status':'同合约参考未获取',
         'exchange_fee_reference_source':'','broker_minus_exchange_open':None,
         'broker_minus_exchange_display':'待核','broker_over_exchange_multiple':None,
         'broker_over_exchange_display':'待核'}
    from so_listing import official_exchange_fee_record, FIRST_LISTED, ANNOUNCEMENT_DATE
    is_so_symbol = (str(exchange).upper()=='CZCE' and str(contract).lower().startswith('so'))
    report_key=str(report_date).replace('-','').replace('/','')[:8]
    # Do not backdate a fee to before listing, nor use the third-party SO quote
    # to supersede the explicit initial CZCE published fee for its four launches.
    if is_so_symbol and report_key < FIRST_LISTED:
        return out
    official = official_exchange_fee_record(exchange, contract, report_date)
    ref = official if official is not None else _contract_match(rows,exchange,contract)
    if ref is None:return out
    date_text=ref.get('fee_updated_at','')
    report_day = _date_of(report_date.replace('/','-'))
    extra=''
    if date_text and report_day:
        try:
            difference=(date.fromisoformat(report_day)-date.fromisoformat(date_text)).days
            if difference>3:extra='；早于报告日'
            if difference<0:extra='；晚于报告日'
        except ValueError:pass
    status=('郑商所挂牌费率公告 '+ANNOUNCEMENT_DATE+'（2026-11-12起；后续变更待核）'
            if official is not None else '第三方参考 '+(date_text or '日期未知')+extra)
    open_amount=amount_for_side(ref,'open',notional)
    close_y=amount_for_side(ref,'close_yesterday',notional)
    close_t=amount_for_side(ref,'close_today',notional)
    out.update(exchange_fee_reference_open=open_amount,
               exchange_fee_reference_close_yesterday=close_y,
               exchange_fee_reference_close_today=close_t,
               exchange_fee_reference_display=(_as_money(open_amount)+
                    ('（郑商所挂牌公告 2026-11-06）' if official is not None
                     else f'（第三方参考{date_text or "日期待核"}）'))
                    if open_amount is not None else '待核（缺金额/结算价）',
               exchange_fee_reference_open_rule=_side_rule(ref,'open'),
               exchange_fee_reference_close_today_rule=_side_rule(ref,'close_today'),
               exchange_fee_reference_updated=date_text,
               exchange_fee_reference_status=status,
               exchange_fee_reference_source=ref.get('source_url',SOURCE_URL))
    if broker_default is not None and open_amount is not None:
        diff=round(broker_default-open_amount,4)
        out['broker_minus_exchange_open']=diff
        out['broker_minus_exchange_display']=f'¥{_money_text(diff)}/手（仅毛差）'
        if open_amount>0:
            mult=round(broker_default/open_amount,4)
            out['broker_over_exchange_multiple']=mult
            out['broker_over_exchange_display']=f'{mult:,.2f}×（参考）'
        else:out['broker_over_exchange_display']='不可计算（交易所参考值为0）'
    return out


def variety_catalog(rows:list[dict], broker_rows:list[dict]) -> list[dict]:
    """One dashboard row per saved broker default, with no invented variety fee."""
    grouped=defaultdict(list)
    for row in rows:grouped[(row['exchange'],row['variety'])].append(row)
    result=[]
    for row in broker_rows:
        ex,var=row.get('exchange'),row.get('variety')
        refs=grouped.get((ex,var),[])
        rule_names={_side_rule(r,'open') for r in refs}
        rule_label=(next(iter(rule_names)) if len(rule_names)==1
                    else '不同合约费率有差异；按合约核验' if refs else '待核')
        latest=max((x['fee_updated_at'] for x in refs if x.get('fee_updated_at')),default='')
        ref_count=len(refs)
        if ex=='CZCE' and var=='so':
            # Published initial CZCE rate, irrespective of third-party coverage.
            from so_listing import EXCHANGE_FEE_PERMYRIAD, ANNOUNCEMENT_DATE, INITIAL_CONTRACTS
            rule_label=f'万分之{EXCHANGE_FEE_PERMYRIAD:g}（郑商所挂牌公告）'
            latest=ANNOUNCEMENT_DATE
            ref_count=len(INITIAL_CONTRACTS)
        result.append({'exchange':ex,'variety':var,'variety_name':row.get('variety_name',''),
                       'exchange_open_rule':rule_label,
                       'exchange_fee_update':latest,
                       'reference_contracts':ref_count,
                       'broker_default_type':row.get('open_fee_type'),
                       'broker_default_value':row.get('open_fee_value'),
                       'broker_date':row.get('effective_from')})
    return result