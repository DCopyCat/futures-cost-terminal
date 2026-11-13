"""Regression tests: no unverified 平今, use PDF default fee as reference on 平昨."""
from __future__ import annotations
import csv
import io
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core
from core import _csv_bytes, _html_report, generate, package_report, _fee_value

NOW = datetime(2026,11,9,8,30,tzinfo=ZoneInfo('Asia/Shanghai'))
class LocalAPI:
    def get_futures_daily(self, start_date, end_date, market):
        if market == 'SHFE':
            return [{'symbol':'rb2701','date':'20261106','variety':'rb','settle':3040,'open_interest':1000,'volume':100}]
        if market == 'DCE':
            return [{'symbol':'m2701','date':'20261106','variety':'m','settle':3200,'open_interest':1000,'volume':100}]
        return []
    def futures_settle(self,date,market): return []

def make_data(tmp_path, overrides=None):
    origin=Path(__file__).resolve().parents[1]/'data'
    for name in ('contracts.csv','company_fees.csv','exchange_overrides.csv'):
        source = origin/name
        if name == 'exchange_overrides.csv' and not source.exists():
            source = origin.parent/'templates'/'exchange_overrides.example.csv'
        (tmp_path/name).write_bytes(source.read_bytes())
    header=['exchange','variety','contract','open_fee_type','open_fee_value',
            'close_yesterday_fee_type','close_yesterday_fee_value',
            'close_today_fee_type','close_today_fee_value','margin_long_pct','margin_short_pct',
            'effective_from','verified_at','source_note']
    with (tmp_path/'company_overrides.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=header);writer.writeheader()
        for row in (overrides or []):writer.writerow(row)

def test_default_fee_all_segments(tmp_path,monkeypatch):
    make_data(tmp_path)
    monkeypatch.setattr(core,'DATA',tmp_path)
    report=generate(LocalAPI(),now=NOW)
    assert len(report['main_records'])==2
    rb=next(r for r in report['main_records'] if r['variety']=='rb')
    assert rb['company_fee_open']==15.2
    assert rb['company_fee_close_yesterday']==15.2
    assert rb['company_fee_close_today'] is None
    assert rb['overnight_round_trip_fee']==30.4
    assert rb['day_round_trip_fee'] is None
    assert rb['day_round_trip_plus_fund'] is None
    assert rb['fund_open']==.002736
    assert rb['overnight_round_trip_plus_fund']==30.4055
    assert '仅按默认单边费率试算平昨' in rb['fee_status']
    assert '平今无公司确认费率' in rb['fee_status']
    m=next(r for r in report['main_records'] if r['variety']=='m')
    assert m['company_fee_open']==m['company_fee_close_yesterday']==7.5
    assert m['overnight_round_trip_fee']==15
    assert m['company_fee_close_today'] is None
    csv_text=_csv_bytes(report['main_records']).decode('utf-8-sig')
    assert '客户平昨参考手续费/手' in csv_text
    assert '隔夜一开一平含双边基金' in csv_text
    assert '日内一开一平含双边基金' in csv_text
    html=_html_report(report).decode('utf-8')
    assert '平昨费/手' in html and '平今费/手' in html
    assert '隔夜开平双边含基金' in html
    z,files=package_report(report)
    assert z.startswith(b'PK') and 'futures_cost_20261106_main.csv' in files

def test_verified_overrides_and_zero_close_today(tmp_path,monkeypatch):
    make_data(tmp_path,[{'exchange':'SHFE','variety':'rb','contract':'rb2701',
                          'close_yesterday_fee_type':'FIXED','close_yesterday_fee_value':'20',
                          'close_today_fee_type':'RATE','close_today_fee_value':'0.001',
                          'effective_from':'2026-11-02','verified_at':'2026-11-06','source_note':'测试手工填入'}])
    monkeypatch.setattr(core,'DATA',tmp_path)
    rb=next(r for r in generate(LocalAPI(),now=NOW)['main_records'] if r['variety']=='rb')
    assert rb['company_fee_close_yesterday']==20
    assert rb['company_fee_close_today']==30.4
    assert rb['overnight_round_trip_fee']==35.2
    assert rb['day_round_trip_fee']==45.6
    assert rb['day_round_trip_plus_fund']==45.6055
    assert '已填写平昨覆盖参数' in rb['fee_status']
    # Explicit free 平今 is valid only when it was deliberately entered.
    make_data(tmp_path,[{'exchange':'SHFE','variety':'rb','contract':'rb2701',
                          'close_today_fee_type':'FIXED','close_today_fee_value':'0',
                          'effective_from':'2026-11-02','verified_at':'2026-11-06','source_note':'测试来源'}])
    rb=next(r for r in generate(LocalAPI(),now=NOW)['main_records'] if r['variety']=='rb')
    assert rb['company_fee_close_today']==0
    assert rb['day_round_trip_fee']==15.2
    assert rb['day_round_trip_plus_fund']==15.2055

def test_fee_formula_units_and_incomplete_override(tmp_path,monkeypatch):
    assert _fee_value('RATE','0.0005',30400)==15.2
    assert _fee_value('FIXED','15',None)==15
    assert _fee_value('RATE','0.0005',None) is None
    make_data(tmp_path,[{'exchange':'SHFE','variety':'rb','contract':'rb2701',
                          'close_yesterday_fee_type':'FIXED',
                          'effective_from':'2026-11-02'}])
    monkeypatch.setattr(core,'DATA',tmp_path)
    rb=next(r for r in generate(LocalAPI(),now=NOW)['main_records'] if r['variety']=='rb')
    assert rb['company_fee_close_yesterday'] is None
    assert rb['overnight_round_trip_plus_fund'] is None
