"""Offline safeguards for dated reference margins and broker notice arithmetic."""
from __future__ import annotations
from pathlib import Path
import csv
import io
import pytest
from margin_reference import _pct, fetch_czce_reference, fetch_dce_reference, published_addon_points
from parameter_import import parse_company_margin_csv, install_company_margin_csv, load_company_margin


class PublicCZCE:
    def futures_contract_info_czce(self, date):
        assert date == '20261109'
        return [
            {'合约代码':'MA701', '交易保证金率':'10%'},
            {'合约代码':'SH701', '交易保证金率':'0.12'},
            {'合约代码':'SR701', '交易保证金率':'无效'},
        ]

class PublicDCE:
    def futures_comm_js(self, date):
        assert date == '20261109'
        return [
            {'交易所':'大连商品交易所','日期':'2026-11-09','合约代码':'m2701','保证金/买开':'8%','保证金/卖开':'9%'},
            {'交易所':'大连商品交易所','日期':'2026-11-08','合约代码':'i2701','保证金/买开':'12%','保证金/卖开':'12%'},
            {'交易所':'郑州商品交易所','日期':'2026-11-09','合约代码':'MA701','保证金/买开':'10%','保证金/卖开':'10%'},
        ]

def test_margin_ref_sources_do_not_become_authoritative():
    cz = fetch_czce_reference('20261109',PublicCZCE())
    assert cz['ma701']['long'] == 10
    assert cz['sh701']['long'] == 12
    assert 'sr701' not in cz
    assert all(v['reference_only'] for v in cz.values())
    dce = fetch_dce_reference('20261109',PublicDCE())
    assert list(dce)==['m2701']
    assert dce['m2701']['long']==8 and dce['m2701']['short']==9
    assert dce['m2701']['reference_only']
    assert _pct('3-7%') is None
    assert _pct('8%')==8 and _pct(.08)==8


def test_announcement_is_not_silent_company_rate():
    assert published_addon_points('DCE','m','20261109')==3
    assert published_addon_points('CZCE','ma','20261109')==5
    assert published_addon_points('DCE','c','20261109') is None
    assert published_addon_points('DCE','m','20260201') is None


def to_csv(rows):
    columns=['trade_date','exchange','contract','company_long_margin_pct','company_short_margin_pct','source_note']
    f=io.StringIO();w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(rows)
    return f.getvalue().encode('utf-8')


def test_company_margin_import_exact_day(tmp_path):
    raw=to_csv([{'trade_date':'2026-11-09','exchange':'CZCE','contract':'ma701',
                 'company_long_margin_pct':'15','company_short_margin_pct':'16',
                 'source_note':'已核实公司当日默认保证金表'}])
    assert parse_company_margin_csv(raw)[0]=='20261109'
    d,n=install_company_margin_csv(raw,tmp_path)
    assert (d,n)==('20261109',1)
    assert load_company_margin(tmp_path,'20261109')['CZCE']['ma701']['long']==15
    assert load_company_margin(tmp_path,'20261110')=={}
    with pytest.raises(ValueError):
        parse_company_margin_csv(to_csv([
            {'trade_date':'2026-11-09','exchange':'CZCE','contract':'ma701','company_long_margin_pct':'15','company_short_margin_pct':'16','source_note':'已核实'},
            {'trade_date':'2026-11-10','exchange':'DCE','contract':'m2701','company_long_margin_pct':'10','company_short_margin_pct':'10','source_note':'已核实'}]))
    with pytest.raises(ValueError):
        parse_company_margin_csv(to_csv([{'trade_date':'2026-11-09','exchange':'DCE','contract':'m2701','company_long_margin_pct':'10','company_short_margin_pct':'','source_note':''}]))