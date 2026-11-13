"""SO launch coverage: accurate initial instrument, fees, references, no broker guesses."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import csv
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core
from exchange_fee_provider import compare_exchange_vs_broker, variety_catalog
from so_listing import (INITIAL_CONTRACTS, FIRST_DAY_REFERENCE_PRICE, MULTIPLIER,
                        EXCHANGE_INITIAL_MARGIN_PCT, EXCHANGE_FEE_PERMYRIAD,
                        is_initial_so_contract, listing_contract_rows)


class SoleSoMarket:
    def __init__(self,trade_date='20261112', oi=850):
        self.trade_date=trade_date
        self.oi=oi
    def get_futures_daily(self,start_date,end_date,market):
        if market=='CZCE':
            return [{'symbol':'SO2705', 'date':self.trade_date,
                     'variety':'SO', 'settle':10150.0,
                     'open_interest':self.oi,'volume':320}]
        return []
    def futures_settle(self,date,market): return []


def test_four_initial_so_contracts_and_specification():
    assert INITIAL_CONTRACTS==('so2705','so2707','so2709','so2711')
    assert len(listing_contract_rows())==4
    assert all(r['multiplier']==20 and r['tick_size']==1 and
               r['value_per_tick']==20 for r in listing_contract_rows())
    assert all(r['exchange_margin_listing_pct']==8 for r in listing_contract_rows())
    contracts=core._load_csv(Path(__file__).resolve().parents[1]/'data'/'contracts.csv')
    so=[r for r in contracts if r['exchange']=='CZCE' and r['variety']=='so']
    assert len(so)==1
    assert float(so[0]['multiplier'])==20
    assert float(so[0]['tick_size'])==1


def test_so_effective_date_and_contract_ids_are_restricted():
    assert is_initial_so_contract('CZCE','SO2705','20261112')
    assert is_initial_so_contract('CZCE','so2711','2026-11-13')
    assert not is_initial_so_contract('CZCE','so2705','20261111')
    assert not is_initial_so_contract('CZCE','so2701','20261113')
    assert not is_initial_so_contract('DCE','so2705','20261113')


def test_exchange_fee_is_from_official_announcement_not_third_party():
    report=core.generate(SoleSoMarket(),now=datetime(2026,11,13,9,0,tzinfo=ZoneInfo('Asia/Shanghai')))
    so=next(r for r in report['main_records'] if r['contract']=='so2705')
    assert so['variety_name']=='葵花籽油'
    assert so['notional']==203000.0
    assert so['exchange_fee_reference_open']==20.3
    assert so['exchange_fee_reference_close_yesterday']==20.3
    assert so['exchange_fee_reference_close_today']==20.3
    assert '郑商所挂牌' in so['exchange_fee_reference_status']
    assert '44faa39' in so['exchange_fee_reference_source']
    assert so['company_default_fee_amount'] is None
    assert so['company_default_fee_rule']=='待核'
    assert so['company_default_fee_version']=='待核'
    assert so['company_fee_open'] is None
    assert so['company_fee_close_today'] is None
    assert so['broker_minus_exchange_open'] is None
    assert so['exchange_margin_long_pct'] is None
    assert so['exchange_margin_reference_long_pct']==8.0
    assert so['exchange_margin_reference_short_pct']==8.0
    assert so['display_exchange_margin_long_pct'].startswith('8%')
    assert so['display_exchange_margin_one_lot'].startswith('16,240.00')
    assert so['display_company_margin_long_pct'].startswith('待核')
    html=core._html_report(report).decode('utf-8')
    assert '葵花籽油' in html and 'so2705' in html
    assert '¥20.30' in html
    assert '先锋默认' in html
    csv_text=core._csv_bytes(report['main_records']).decode('utf-8-sig')
    assert 'so2705' in csv_text and '20.3' in csv_text


def test_so_fee_not_backdated_to_prelisting_day():
    result=compare_exchange_vs_broker([],'CZCE','so2705','20261111',200000,None)
    assert result['exchange_fee_reference_open'] is None
    result2=compare_exchange_vs_broker([],'CZCE','so2701','20261113',200000,None)
    assert result2['exchange_fee_reference_open'] is None


def test_missing_open_interest_is_not_an_invented_so_main():
    result=core.generate(SoleSoMarket(oi=None),now=datetime(2026,11,13,9,0,tzinfo=ZoneInfo('Asia/Shanghai')))
    assert not any(r['variety']=='so' for r in result['main_records'])
    assert any(r['variety']=='so' for r in result['records'])


def test_so_never_pretends_to_be_in_the_20261102_pioneer_pdf():
    fees=core._load_csv(Path(__file__).resolve().parents[1]/'data'/'company_fees.csv')
    assert len(fees)==88
    assert not any(r['exchange']=='CZCE' and r['variety']=='so' for r in fees)
    from exchange_fee_provider import variety_catalog
    broker_rows=list(fees)+[{'exchange':'CZCE','variety':'so','variety_name':'葵花籽油',
                           'open_fee_type':'','open_fee_value':'','effective_from':'待核'}]
    catalog=variety_catalog([],broker_rows)
    item=next(r for r in catalog if r['variety']=='so' and r['exchange']=='CZCE')
    assert '万分之1' in item['exchange_open_rule']
    assert item['broker_default_type']==''
    assert item['reference_contracts']==4


def test_listing_price_used_only_as_explicit_illustration():
    assert FIRST_DAY_REFERENCE_PRICE==10000.0
    assert FIRST_DAY_REFERENCE_PRICE*MULTIPLIER*EXCHANGE_FEE_PERMYRIAD/10000==20.0
    assert FIRST_DAY_REFERENCE_PRICE*MULTIPLIER*EXCHANGE_INITIAL_MARGIN_PCT/100==16000.0


def test_so_online_snapshot_cannot_overwrite_official_listing_rule():
    # The official announcement is the starting point; live source may require
    # manual revision for later amendments, never let an unrelated quote replace it.
    from exchange_fee_provider import normalize_reference_rows
    fake=normalize_reference_rows([{
        '交易所名称':'郑州商品交易所','合约代码':'SO2705',
        '手续费标准-开仓-万分之':2.3,'手续费标准-开仓-元':0,
        '手续费更新时间':'2026-11-12'
    }])
    out=compare_exchange_vs_broker(fake,'CZCE','so2705','20261112',200000,None)
    assert out['exchange_fee_reference_open']==20.0
    assert '郑商所挂牌' in out['exchange_fee_reference_status']
