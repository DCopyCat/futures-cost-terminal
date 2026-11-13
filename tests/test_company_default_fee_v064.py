"""Visible 2026-11-02 brokerage defaults: PDF tariff must be near the front of HTML."""
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import csv
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core
from company_fee_view import format_company_fee_rule, make_company_default_fee_display

class FakeFutures:
    def get_futures_daily(self,start_date,end_date,market):
        if market == 'SHFE':
            return [{'symbol':'rb2701','variety':'rb','date':'20261110','settle':3040,'open_interest':1000,'volume':100}]
        if market == 'DCE':
            return [{'symbol':'a2701','variety':'a','date':'20261110','settle':5183,'open_interest':1000,'volume':100},
                    {'symbol':'m2701','variety':'m','date':'20261110','settle':3100,'open_interest':1000,'volume':100}]
        return []
    def futures_settle(self,date,market): return []

def test_20261102_pdf_baseline_is_present_and_accurate():
    with (Path(__file__).resolve().parents[1]/'data'/'company_fees.csv').open(encoding='utf-8-sig') as f:
        fees=list(csv.DictReader(f))
    assert len(fees) == 88
    assert {r['effective_from'] for r in fees} == {'2026-11-02'}
    named={(r['exchange'],r['variety']):r for r in fees}
    assert float(named[('DCE','a')]['open_fee_value']) == 10
    assert float(named[('DCE','m')]['open_fee_value']) == 7.5
    assert named[('SHFE','rb')]['open_fee_type']=='RATE'
    assert float(named[('SHFE','rb')]['open_fee_value'])==0.0005

def test_tariff_labels():
    assert format_company_fee_rule('RATE','0.0005')=='成交金额万分之5'
    assert format_company_fee_rule('RATE','0.00046')=='成交金额万分之4.6'
    assert format_company_fee_rule('FIXED','10')=='固定10元/手'
    assert format_company_fee_rule('FIXED','')=='待核'
    assert make_company_default_fee_display(None,'固定10元/手','2026-11-02').startswith('待核')

def test_new_fee_column_visible_in_html_and_csv():
    r=core.generate(FakeFutures(),now=datetime(2026,11,11,9,30,tzinfo=ZoneInfo('Asia/Shanghai')))
    d={x['contract']:x for x in r['main_records']}
    assert set(d)>={'a2701','m2701','rb2701'}
    assert d['a2701']['company_default_fee_amount']==10
    assert d['m2701']['company_default_fee_amount']==7.5
    assert d['rb2701']['company_default_fee_amount']==15.2
    assert d['rb2701']['company_default_fee_rule']=='成交金额万分之5'
    assert d['a2701']['company_default_fee_display']=='¥10.00/手（PDF 2026-11-02）'
    assert d['a2701']['company_default_fee_version']=='2026-11-02'
    assert d['a2701']['company_fee_close_today'] is None
    html=core._html_report(r).decode('utf-8')
    assert '★先锋默认手续费/手（PDF）' in html
    assert html.index('★先锋默认手续费/手（PDF）')<html.index('展示交易所保证金率（含历史）')
    assert '¥10.00/手（PDF 2026-11-02）' in html
    assert '软件版本：' in html
    csv=core._csv_bytes(r['main_records']).decode('utf-8-sig')
    assert '★先锋开户默认手续费/手（PDF）' in csv
    assert '先锋PDF更新日期' in csv
