"""Strict exchange-fee unit, contract, provenance and broker spread regression."""
from pathlib import Path
import sys
import csv
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from exchange_fee_provider import (normalize_reference_rows, amount_for_side, compare_exchange_vs_broker,
   load_snapshot, write_snapshot, refresh_from_akshare, variety_catalog)


def fake(ex='大连商品交易所', sym='j2701',rate=1,flat=0, ct_rate=1.4,updated='2026-11-10 22:00:00'):
    return {'交易所名称':ex,'合约代码':sym,
        '手续费标准-开仓-万分之':rate,'手续费标准-开仓-元':flat,
        '手续费标准-平昨-万分之':rate,'手续费标准-平昨-元':flat,
        '手续费标准-平今-万分之':ct_rate,'手续费标准-平今-元':flat,
        '手续费更新时间':updated}


def test_j_192750_notional_ratio_is_one_ten_thousandth_not_percent():
    rows=normalize_reference_rows([fake()]);assert len(rows)==1
    r=compare_exchange_vs_broker(rows,'DCE','j2701','20261110',192750,134.925)
    assert r['exchange_fee_reference_open']==19.275
    assert r['exchange_fee_reference_close_today']==26.985
    assert r['broker_minus_exchange_open']==115.65
    assert r['broker_over_exchange_multiple']==7.0
    assert '仅毛差' in r['broker_minus_exchange_display']
    assert r['exchange_fee_reference_status'].startswith('第三方参考 2026-11-10')


def test_fixed_a_vs_broker_and_explicit_free_close_today():
    rows=normalize_reference_rows([fake(sym='a2701',rate=0,flat=2,ct_rate=0)])
    r=compare_exchange_vs_broker(rows,'DCE','a2701','20261110',51830,10)
    assert r['exchange_fee_reference_open']==2
    assert r['exchange_fee_reference_close_today']==2
    assert r['broker_minus_exchange_open']==8
    assert r['broker_over_exchange_multiple']==5
    shfe=normalize_reference_rows([fake(ex='上海期货交易所',sym='ad2701',rate=.5,flat=0,ct_rate=0)])
    x=compare_exchange_vs_broker(shfe,'SHFE','ad2701','20261110',222400,55.6)
    assert x['exchange_fee_reference_open']==11.12
    assert x['exchange_fee_reference_close_today']==0
    assert x['broker_minus_exchange_open']==44.48


def test_missing_close_today_stays_missing_and_zero_fee_base_ratio_undefined():
    raw=fake(sym='m2701',rate=0,flat=0,ct_rate=None)
    raw['手续费标准-平今-元']=None
    rows=normalize_reference_rows([raw])
    r=compare_exchange_vs_broker(rows,'DCE','m2701','20261110',31000,7.5)
    assert r['exchange_fee_reference_open']==0
    assert r['exchange_fee_reference_close_today'] is None
    assert r['broker_over_exchange_multiple'] is None
    assert '交易所参考值为0' in r['broker_over_exchange_display']


def test_exact_contract_only_no_dangerous_rollover():
    rows=normalize_reference_rows([fake(sym='j2701')])
    x=compare_exchange_vs_broker(rows,'DCE','j2705','20261110',180000,126)
    assert x['exchange_fee_reference_open'] is None
    assert x['broker_minus_exchange_open'] is None
    assert x['exchange_fee_reference_display'].startswith('待核')


def test_czce_three_digits_can_match_same_four_digit_contract():
    rows=normalize_reference_rows([fake(ex='郑州商品交易所',sym='MA701',rate=1,ct_rate=1)])
    x=compare_exchange_vs_broker(rows,'CZCE','ma2701','20261110',31100,15.55)
    assert x['exchange_fee_reference_open']==3.11
    assert x['exchange_fee_reference_status'].startswith('第三方参考')
    y=compare_exchange_vs_broker(rows,'CZCE','ma2801','20261110',31100,15.55)
    assert y['exchange_fee_reference_open'] is None


def test_snapshot_persistence_and_guard_on_failure(tmp_path):
    path=tmp_path/'reference.csv'
    rows=normalize_reference_rows([fake()])
    write_snapshot(path,rows)
    assert len(load_snapshot(path))==1
    before=path.read_bytes()
    try:
        refresh_from_akshare(path,loader=lambda:[fake()],min_contracts=100,min_markets=5)
    except RuntimeError:pass
    else:raise AssertionError('should reject too small dataset')
    assert path.read_bytes()==before


def test_index_for_every_broker_variety_even_when_reference_missing():
    rows=normalize_reference_rows([fake(sym='a2701',rate=0,flat=2,ct_rate=0)])
    bro=[{'exchange':'DCE','variety':'a','variety_name':'豆一','open_fee_type':'FIXED','open_fee_value':10,'effective_from':'2026-11-02'},
         {'exchange':'DCE','variety':'m','variety_name':'豆粕','open_fee_type':'FIXED','open_fee_value':7.5,'effective_from':'2026-11-02'}]
    data=variety_catalog(rows,bro)
    assert len(data)==2
    assert data[0]['exchange_open_rule']=='2元/手'
    assert data[1]['exchange_open_rule']=='待核'


def test_daily_core_compares_exact_j_and_ad_contracts_without_touching_broker_account(monkeypatch):
    import core
    from datetime import datetime
    from zoneinfo import ZoneInfo
    class API:
        def get_futures_daily(self,start_date,end_date,market):
            if market=='DCE':
                return [{'symbol':'j2701','date':'20261110','variety':'j','settle':1927.5,'open_interest':2500,'volume':500}]
            if market=='SHFE':
                return [{'symbol':'ad2701','date':'20261110','variety':'ad','settle':22240,'open_interest':2500,'volume':500}]
            return []
        def futures_settle(self,date,market):return []
    from exchange_fee_provider import normalize_reference_rows
    sample=normalize_reference_rows([
        fake(sym='j2701',rate=1,ct_rate=1.4),
        fake(ex='上海期货交易所',sym='ad2701',rate=.5,ct_rate=0)])
    monkeypatch.setattr('exchange_fee_provider.load_snapshot',lambda p:sample)
    report=core.generate(API(),now=datetime(2026,11,11,10,20,tzinfo=ZoneInfo('Asia/Shanghai')))
    j=next(x for x in report['main_records'] if x['contract']=='j2701')
    ad=next(x for x in report['main_records'] if x['contract']=='ad2701')
    assert j['company_default_fee_amount']==134.925
    assert j['exchange_fee_reference_open']==19.275
    assert j['exchange_fee_reference_close_today']==26.985
    assert j['broker_minus_exchange_open']==115.65
    assert ad['company_default_fee_amount']==55.6
    assert ad['exchange_fee_reference_open']==11.12
    assert ad['exchange_fee_reference_close_today']==0
    assert ad['broker_minus_exchange_open']==44.48
    # A third-party exchange reference must not become the customer account fee.
    assert j['company_fee_close_today'] is None
    html=core._html_report(report).decode('utf-8')
    assert html.index('交易所开仓/手（第三方参考）')<html.index('★先锋默认手续费/手（PDF）')
    assert '¥19.27/手' in html or '¥19.28/手' in html
    assert '¥115.65' in html
    raw=core._csv_bytes(report['main_records']).decode('utf-8-sig')
    assert '交易所开仓参考费/手(元)' in raw
    assert '先锋默认减交易所开仓参考毛差/手(元)' in raw

def test_stale_source_date_is_explicitly_labeled():
    one=normalize_reference_rows([fake(updated='2026-10-22 08:00:00')])
    ref=compare_exchange_vs_broker(one,'DCE','j2701','20261110',192750,134.925)
    assert '早于报告日' in ref['exchange_fee_reference_status']
    newer=normalize_reference_rows([fake(updated='2026-11-12 08:00:00')])
    ref=compare_exchange_vs_broker(newer,'DCE','j2701','20261110',192750,134.925)
    assert '晚于报告日' in ref['exchange_fee_reference_status']


def test_dated_public_seed_is_not_misrepresented_as_live():
    data=Path(__file__).resolve().parents[1]/'data'
    rows=load_snapshot(data/'exchange_fee_reference.csv')
    assert len(rows)>=32
    j=compare_exchange_vs_broker(rows,'DCE','j2701','20261111',192750,134.925)
    assert j['exchange_fee_reference_open']==19.275
    assert j['exchange_fee_reference_status'].startswith('第三方参考 2026-11-10')
    ad=compare_exchange_vs_broker(rows,'SHFE','ad2701','20261111',222400,55.6)
    assert ad['exchange_fee_reference_open']==11.12
    assert ad['exchange_fee_reference_close_today']==0
    assert sum(r['exchange']=='CFFEX' for r in rows)>=8


def test_streamlit_primary_columns_and_local_refresh_control_exist():
    app=(Path(__file__).resolve().parents[1]/'app.py').read_text(encoding='utf-8')
    assert "('exchange_fee_reference_display','交易所开仓/手（第三方参考）')" in app
    assert "('company_default_fee_display','★先锋默认手续费/手（PDF）')" in app
    assert app.index("('exchange_fee_reference_display','交易所开仓/手（第三方参考）')") < app.index("('company_default_fee_display','★先锋默认手续费/手（PDF）')")
    assert '更新六市场交易所手续费参考（联网）' in app
