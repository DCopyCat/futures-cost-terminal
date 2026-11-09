import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import MARKETS, _today_cutoff, generate, package_report

class MockAPI:
    def get_futures_daily(self,start_date,end_date,market):
        symbol = {'SHFE':'rb2701','INE':'sc2701','CZCE':'SH701','DCE':'m2701','CFFEX':'IF2612','GFEX':'lc2701'}[market]
        variety = {'SHFE':'rb','INE':'sc','CZCE':'SH','DCE':'m','CFFEX':'IF','GFEX':'lc'}[market]
        settle = {'SHFE':3040,'INE':690,'CZCE':1486,'DCE':3200,'CFFEX':4049,'GFEX':95280}[market]
        rows=[dict(symbol=symbol,date='20261106',variety=variety,settle=settle,open_interest=56000,volume=20000)]
        if market=='SHFE':
            rows.append(dict(symbol='rb2705',date='20261106',variety='rb',settle=3200,open_interest=30000,volume=10000))
            rows.append(dict(symbol='rb99',date='20261106',variety='rb',settle=3200,open_interest=90000,volume=10000))
        return rows
    def futures_settle(self, date,market):
        symbol = {'SHFE':'rb2701','INE':'sc2701','CZCE':'SH701','CFFEX':'IF2612','GFEX':'lc2701'}[market]
        return [dict(symbol=symbol,date='20261106',spec_long_margin_ratio=.12,spec_short_margin_ratio=.13,trade_fee_ratio=.0002,close_today_fee_ratio=.0004)]


def test_morning_report_and_flags():
    assert _today_cutoff(datetime(2026,11,9,8,30,tzinfo=ZoneInfo('Asia/Shanghai'))).isoformat()=='2026-11-08'
    report=generate(MockAPI(),now=datetime(2026,11,9,8,30,tzinfo=ZoneInfo('Asia/Shanghai')))
    assert report['price_date']=='2026-11-06'
    assert report['status'].startswith('六市场同日覆盖')
    assert len(report['records'])==7
    assert len(report['main_records'])==6
    rb=next(r for r in report['records'] if r['contract']=='rb2701')
    assert rb['notional']==30400
    assert abs(rb['company_fee_open']-15.2)<.0001
    assert rb['exchange_margin_one_lot']==3648
    assert rb['company_margin_one_lot'] is None
    assert '账户/公司保证金待确认' in rb['issue']
    assert rb['exchange_fee_raw_open'] != ''
    m=next(r for r in report['records'] if r['contract']=='m2701')
    assert m['company_fee_open']==7.5
    assert '大商所合约保证金参数待核验' in m['issue']
    zipped,parts=package_report(report)
    assert zipped.startswith(b'PK') and len(parts)==6
    assert 'futures_cost_20261106_main.csv' in parts
    return report

if __name__=='__main__':
    r=test_morning_report_and_flags()
    print('OK: six markets, price day, main contract, company fees, missing rates, audit zip')
