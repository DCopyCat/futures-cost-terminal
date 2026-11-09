from __future__ import annotations
import io
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dce_provider import from_daily, from_fut_settle, from_dce_trade_param, margin_for_date
from dce_import import parse_margin_csv, parse_daily_csv
from core import generate, package_report
from test_core import MockAPI

NOW=datetime(2026,11,9,8,30,tzinfo=ZoneInfo('Asia/Shanghai'))

class BlockedDCE(MockAPI):
    def get_futures_daily(self, start_date, end_date, market):
        if market=='DCE': raise RuntimeError('HTTP 412')
        return super().get_futures_daily(start_date,end_date,market)

class FakeTushare:
    def fut_daily(self, trade_date, exchange):
        assert exchange=='DCE'
        return [{'ts_code':'M2701.DCE','trade_date':trade_date,'settle':3200,
                 'oi':12345,'vol':7654},
                {'ts_code':'M2705.DCE','trade_date':trade_date,'settle':3150,
                 'oi':1000,'vol':765}]
    def fut_settle(self, trade_date, exchange):
        assert exchange=='DCE'
        return [{'ts_code':'M2701.DCE','trade_date':trade_date,'long_margin_rate':0.12,
                 'short_margin_rate':0.13},
                {'ts_code':'M2705.DCE','trade_date':trade_date,'long_margin_rate':0.10,
                 'short_margin_rate':0.10}]
    def fut_trade_param_dce(self, trade_date):
        raise AssertionError('Not needed')


def test_dce_api_and_report():
    assert from_daily([{'ts_code':'M2701.DCE','trade_date':'20261106','settle':3200,'oi':11,'vol':9}], '20261106')[0]['contract']=='m2701'
    assert not from_daily([{'ts_code':'M2701.DCE','trade_date':'20261105','settle':3200}], '20261106')
    p=from_fut_settle([{'ts_code':'M2701.DCE','trade_date':'20261106','long_margin_rate':0.12,'short_margin_rate':0.13}], '20261106')
    assert p['m2701']['long']==12 and p['m2701']['short']==13
    assert from_fut_settle([{'ts_code':'M2701.DCE','trade_date':'20261105','long_margin_rate':0.12}], '20261106')=={}
    p=from_dce_trade_param([{'ts_code':'M2701.DCE','trade_date':'20261106','trade_type':'期货','spec_buy_rate':9}], '20261106')
    assert p['m2701']['long']==9 and p['m2701']['short'] is None
    assert margin_for_date('fake','20261106',client=FakeTushare())[0]['m2701']['short']==13
    report=generate(BlockedDCE(),now=NOW,tushare_token='fake',tushare_client=FakeTushare())
    assert not report['missing_markets']
    assert report['dce_daily_source'].startswith('Tushare')
    assert report['dce_margin_source'].startswith('Tushare fut_settle')
    m=next(r for r in report['records'] if r['contract']=='m2701')
    assert m['is_main']=='是' and m['exchange_margin_long_pct']==12
    assert m['exchange_margin_short_pct']==13
    assert m['exchange_margin_one_lot']==3840
    assert m['company_fee_open']==7.5
    assert 'Tushare fut_settle' in m['data_source']
    assert m['company_margin_one_lot'] is None
    assert '大商所合约保证金参数待核' not in m['issue']
    pack,_=package_report(report)
    assert pack.startswith(b'PK')
    missing=generate(BlockedDCE(),now=NOW)
    assert 'DCE' in missing['missing_markets']
    assert len(missing['main_records'])==5
    print('PASS: DCE HTTP412 → Tushare daily+settlement, day check, units, main contract, no phantom broker margin')


def test_dce_manual_csv():
    raw=b'trade_date,contract,long_margin_pct,short_margin_pct,source_note\n20261106,m2701,12,13,Internal verified official export\n'
    date,params=parse_margin_csv(raw)
    assert date=='20261106' and params['m2701']['long']==12
    raw=b'trade_date,contract,settlement,open_interest,volume\n20261106,m2701,3200,12345,789\n'
    date,rows=parse_daily_csv(raw)
    assert date=='20261106' and rows[0]['open_interest']==12345
    try:
        parse_margin_csv(b'trade_date,contract,long_margin_pct,short_margin_pct,source_note\n20261105,m2701,12,13,A\n20261106,m2705,12,13,A\n')
    except ValueError:
        pass
    else:
        raise AssertionError('Mixed date import accepted')
    print('PASS: CSV import schema/date and no cross-day contamination')

if __name__=='__main__':
    test_dce_api_and_report()
    test_dce_manual_csv()
