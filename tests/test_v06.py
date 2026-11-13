"""New audit controls: no stale margins, no unaudited close-today fee, source coverage."""
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo
import csv
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
import core
from core import generate
from parameter_import import (parse_exchange_margin_csv, install_exchange_margin_csv,
                              parse_company_close_today_csv, merge_company_close_today_csv)
from cne_provider import parse_bars
from tests.test_v05 import LocalAPI, make_data, NOW


def _margin_file(day='20261106'):
    return (f'trade_date,exchange,contract,long_margin_pct,short_margin_pct,source_note\n'
            f'{day},DCE,m2701,12,13,交易所人工核对\n'
            f'{day},SHFE,rb2701,10,,上期所结算参数核对\n').encode()


def test_market_margin_import_and_exact_day(tmp_path,monkeypatch):
    make_data(tmp_path)
    monkeypatch.setattr(core,'DATA',tmp_path)
    day,n=install_exchange_margin_csv(_margin_file(),tmp_path)
    assert day=='20261106' and n==2
    rep=generate(LocalAPI(),now=NOW)
    rb=next(x for x in rep['main_records'] if x['contract']=='rb2701')
    m=next(x for x in rep['main_records'] if x['contract']=='m2701')
    assert rb['exchange_margin_long_pct']==10
    assert rb['exchange_margin_short_pct'] is None
    assert m['exchange_margin_short_pct']==13
    assert '人工核验' in m['margin_source']
    assert m['exchange_margin_one_lot']==3840
    assert 'DCE' not in rep['params_errors']
    # One-day file must not substitute for a different day.\n
    (tmp_path/'exchange_margin_20261106.csv').rename(tmp_path/'exchange_margin_20261105.csv')
    rep2=generate(LocalAPI(),now=NOW)
    mm=next(x for x in rep2['main_records'] if x['contract']=='m2701')
    assert mm['exchange_margin_long_pct'] is None


def test_reject_cross_day_fake_margin():
    with pytest.raises(ValueError,match='同一交易日'):
        parse_exchange_margin_csv(_margin_file()+b'20261105,DCE,m2705,10,10,Source\n')
    with pytest.raises(ValueError,match='无效日期'):
        parse_exchange_margin_csv(_margin_file('20261340'))
    with pytest.raises(ValueError,match='重复'):
        parse_exchange_margin_csv(_margin_file()+b'20261106,DCE,m2701,12,12,source\n')
    with pytest.raises(ValueError,match='零保证金率'):
        parse_exchange_margin_csv(b'trade_date,exchange,contract,long_margin_pct,short_margin_pct,source_note\n20261106,DCE,m2701,0,,source\n')


def test_verified_bulk_close_today_and_zero(tmp_path,monkeypatch):
    make_data(tmp_path)
    monkeypatch.setattr(core,'DATA',tmp_path)
    body=('exchange,variety,contract,close_today_fee_type,close_today_fee_value,effective_from,verified_at,source_note\n'
          'SHFE,rb,rb2701,FIXED,0,2026-11-02,2026-11-06,测试来源（非真实费率）\n').encode()
    rows=parse_company_close_today_csv(body)
    assert rows[0]['close_today_fee_value']=='0.0'
    assert merge_company_close_today_csv(body,tmp_path)==1
    rb=next(x for x in generate(LocalAPI(),now=NOW)['main_records'] if x['contract']=='rb2701')
    assert rb['company_fee_close_today']==0
    assert rb['day_round_trip_fee']==15.2
    assert '有来源记录' in rb['fee_status']
    assert rb['company_close_today_fee_rule']=='0.0'


def test_unverified_fee_cannot_leak_into_calculator(tmp_path,monkeypatch):
    make_data(tmp_path,[{'exchange':'SHFE','variety':'rb','contract':'rb2701',
                         'close_today_fee_type':'RATE','close_today_fee_value':'0.001',
                         'effective_from':'2026-11-02','source_note':'没有核验日期'}])
    monkeypatch.setattr(core,'DATA',tmp_path)
    rb=next(x for x in generate(LocalAPI(),now=NOW)['main_records'] if x['contract']=='rb2701')
    assert rb['company_fee_close_today'] is None
    assert rb['company_close_today_fee_type']==''
    assert rb['company_close_today_fee_rule']==''
    assert rb['day_round_trip_fee'] is None
    assert '待核' in rb['company_close_today_verified']


def test_cne_coverage_by_market_day():
    d=date(2026,11,6)
    bars=[{'symbol':'M2701.DCE','exchange':'DCE','trade_date':d,'settle':3200,
           'open_interest':1000,'volume':200,'source':'sina'}]
    parsed,diag=parse_bars(bars,'20261103','20261107')
    assert diag['latest_dates']['DCE']=='20261106'
    assert diag['by_exchange_day']['DCE:20261106']==1
    assert diag['limitations']
