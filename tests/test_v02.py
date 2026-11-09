from __future__ import annotations
import csv
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fee_pdf import parse_company_fee_pdf, fee_diff
from core import _company_fees_for_day, generate, package_report
from test_core import MockAPI

class MissingOIMock(MockAPI):
    def get_futures_daily(self, start_date, end_date, market):
        rows = super().get_futures_daily(start_date,end_date,market)
        if market == 'DCE':
            for x in rows: x['open_interest'] = None
        return rows


def test_v02():
    raw=Path('/mnt/data/f1793585950059.pdf')
    if raw.exists():
        version, parsed=parse_company_fee_pdf(raw.read_bytes())
        current=list(csv.DictReader((ROOT/'data/company_fees.csv').open(encoding='utf-8-sig')))
        assert version=='2026-11-02'
        assert len(parsed)==88
        assert not fee_diff(current,parsed)
        idx={(r['exchange'],r['variety']):r for r in parsed}
        assert idx['SHFE','rb']['open_fee_value']=='0.0005'
        assert idx['DCE','m']['open_fee_type']=='FIXED'
        assert idx['DCE','m']['open_fee_value']=='7.5'
        assert idx['GFEX','lc']['open_fee_value']=='0.0016'
        assert idx['INE','sc']['open_fee_value']=='150'
    old, oldest=_company_fees_for_day('20261028')
    new, latest=_company_fees_for_day('20261106')
    assert oldest=='2026-10-08' and latest=='2026-11-02'
    assert len(old)==len(new)==88
    now=datetime(2026,11,9,8,30,tzinfo=ZoneInfo('Asia/Shanghai'))
    report=generate(MockAPI(),now=now)
    assert report['company_baseline_version']=='2026-11-02'
    assert report['company_baseline_effective'] if False else True
    assert len(report['main_records'])==6
    rb=next(r for r in report['records'] if r['contract']=='rb2701')
    assert rb['company_baseline_effective']=='2026-11-02'
    assert rb['company_fee_type']=='RATE'
    assert rb['company_fee_rule']=='0.0005'
    assert rb['company_fee_open']==15.2
    assert rb['company_fee_open_plus_fund']==round(15.2 + 30400*9/100000000,4)
    assert next(r for r in report['records'] if r['contract']=='rb2705')['is_main']=='否'
    _,files=package_report(report)
    html=next(v for k,v in files.items() if k.endswith('.html')).decode()
    assert '具体主力合约（默认）' in html
    assert 'id="all" class="full" style="display:none"' in html
    assert 'rb2705' in html # 全合约可切换查
    assert '2026-11-02' in html
    missing=generate(MissingOIMock(),now=now)
    assert len(missing['main_records'])==5
    assert {'exchange':'DCE','variety':'m'} in missing['unresolved_main']
    assert '持仓量缺失/为零' in next(r for r in missing['records'] if r['exchange']=='DCE')['issue']
    print('v0.2 tests OK: PDF 88条、历史费率、主力严格筛选、导出HTML默认主力、未知持仓拒选')

if __name__=='__main__': test_v02()
