"""Dated reference records never claim to be verified current margin."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from historical_margin import historical_exchange_reference, historical_company_reference


def test_all_prior_futures_varieties_have_historical_baselines():
    d=Path(__file__).resolve().parents[1] / 'data'
    import csv
    with (d/'historical_exchange_margin.csv').open(encoding='utf-8') as f:
        rows=list(csv.DictReader(f))
    assert len(rows)>=600
    pairs={(x['exchange'],x['variety']) for x in rows}
    assert len(pairs)>=85
    for ex,v in pairs:
        a=historical_exchange_reference(ex,v,'unknown2801',d)
        b=historical_company_reference(ex,v,d)
        assert 0 < a['long'] <= 100
        assert 0 < b['long'] <= 100
        assert a['as_of'] < '2026-11-01'
        assert b['as_of'] < '2026-11-01'


def test_dce_variety_only_record_does_not_pretend_exact_contract():
    ref=historical_exchange_reference('DCE','m','m2701')
    assert ref['scope']=='VARIETY_BASE'
    assert ref['long']==7
    company=historical_company_reference('DCE','m')
    assert company['long']==10
    assert company['as_of']=='2026-03-20'


def test_czce_old_three_digit_contract_is_normalized_with_source_date():
    ref=historical_exchange_reference('CZCE','ap','ap2701')
    assert ref['scope']=='ARCHIVE_CONTRACT'
    assert ref['original_contract']=='ap701'
    assert ref['as_of']=='2026-07-31'


def test_non_matching_czce_contract_gets_labelled_mode_not_fake_contract():
    ref=historical_exchange_reference('CZCE','ma','ma2812')
    assert ref['scope']=='VARIETY_MODE'
    assert ref['long']==7
    assert ref['long_range'][1] >= ref['long']


def test_no_source_returns_none_not_zerorate():
    assert historical_exchange_reference('DCE','unknown','xx2701')=={}
    assert historical_company_reference('DCE','unknown')=={}


def test_report_populates_historical_but_not_verified_dce_fields():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import core
    class FakeAPI:
        def get_futures_daily(self, start_date, end_date, market):
            if market == 'DCE':
                return [{'symbol':'m2701','variety':'m','date':'20261106',
                         'settle':3100,'open_interest':1200,'volume':300}]
            return []
        def futures_settle(self, date, market):
            return []
    report = core.generate(FakeAPI(),now=datetime(2026,11,9,9,0,tzinfo=ZoneInfo('Asia/Shanghai')))
    m = next(x for x in report['main_records'] if x['contract']=='m2701')
    assert m['historical_exchange_long_pct']==7
    assert m['historical_company_long_pct']==10
    assert m['historical_exchange_one_lot'] == round(3100*10*0.07,2)
    assert m['historical_company_one_lot'] == round(3100*10*0.1,2)
    assert m['exchange_margin_long_pct'] is None
    assert m['company_margin_long_pct'] is None
    assert '2026-08-03' in m['historical_exchange_basis']
    assert '2026-03-20' in m['historical_company_basis']
    assert m['data_status']=='待核'