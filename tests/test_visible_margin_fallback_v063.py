"""Display fallback regression: historical values visible in FIRST main table columns.

Raw verified rates remain None when only historical snapshots exist.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from margin_display import enrich_margin_display


def example():
    return dict(notional=51830, exchange_margin_long_pct=None, exchange_margin_short_pct=None,
                company_margin_long_pct=None, company_margin_short_pct=None,
                historical_exchange_long_pct=7, historical_exchange_short_pct=7,
                historical_exchange_basis='2026-08-03 品种级旧档',
                historical_company_long_pct=10, historical_company_short_pct=10,
                historical_company_basis='2026-03-20 先锋历史品种基准')


def test_fallback_into_earliest_display_columns_without_mutating_verified_rates():
    before = example()
    after = enrich_margin_display(before)
    assert after['display_exchange_margin_long_pct'] == '7%（历史 2026-08-03）'
    assert after['display_exchange_margin_one_lot'] == '3,628.10 元（历史 2026-08-03）'
    assert after['display_company_margin_long_pct'] == '10%（历史 2026-03-20）'
    assert after['display_company_margin_one_lot'] == '5,183.00 元（历史 2026-03-20）'
    assert before['exchange_margin_long_pct'] is None
    assert before['company_margin_long_pct'] is None


def test_current_source_wins_historical_and_changes_amount():
    record = example()
    record.update(exchange_margin_long_pct=9, exchange_margin_short_pct=9,
                  company_margin_long_pct=12, company_margin_short_pct=12,
                  margin_source='结算参数经AKShare获取', company_margin_source='20261109已核验CSV')
    out = enrich_margin_display(record)
    assert '9%（当前接口/核验值）' == out['display_exchange_margin_long_pct']
    assert '4,664.70 元' in out['display_exchange_margin_one_lot']
    assert '12%（公司录入待账户核验）' == out['display_company_margin_long_pct']
    assert '6,219.60 元' in out['display_company_margin_one_lot']


def test_public_reference_priority_and_legacy_broker_warning():
    record = example()
    record.update(exchange_margin_reference_long_pct=8, margin_reference_source='第三方仅供参考',
                  company_margin_long_pct=11, company_margin_source='旧公司覆盖项（未按报告交易日复核）')
    out = enrich_margin_display(record)
    assert out['display_exchange_margin_long_pct'] == '8%（公开参考）'
    assert out['display_exchange_margin_short_pct'].startswith('7%（历史')
    assert '旧手工值待核' in out['display_company_margin_long_pct']


def test_missing_display_never_invents_zero():
    out = enrich_margin_display({'notional': 10000})
    assert out['display_exchange_margin_long_pct'] == '待核（无历史资料）'
    assert out['display_company_margin_one_lot'] == '待核（无可用参数）'


def test_real_report_html_visible_fallback_and_original_verified_fields_empty():
    import core
    class API:
        def get_futures_daily(self, start_date, end_date, market):
            if market == 'DCE':
                return [{'symbol':'a2701', 'date':'20261109', 'variety':'a',
                         'settle':5183, 'open_interest':1234, 'volume':350}]
            return []
        def futures_settle(self, date, market):
            return []
    report = core.generate(API(), now=datetime(2026,11,10,11,20,tzinfo=ZoneInfo('Asia/Shanghai')))
    rec = next(x for x in report['main_records'] if x['contract']=='a2701')
    assert rec['exchange_margin_long_pct'] is None
    assert rec['company_margin_long_pct'] is None
    assert rec['display_exchange_margin_long_pct'].startswith('7%（历史')
    assert rec['display_company_margin_long_pct'].startswith('10%（历史')
    assert '3,628.10' in rec['display_exchange_margin_one_lot']
    assert '5,183.00' in rec['display_company_margin_one_lot']
    html = core._html_report(report).decode('utf-8')
    assert '展示交易所保证金率' in html
    assert '展示公司一手保证金' in html
    assert '3,628.10 元（历史' in html
    assert '5,183.00 元（历史' in html
    version = (Path(__file__).resolve().parents[1] / 'VERSION').read_text(encoding='utf-8').strip()
    assert version in html
    csv_text = core._csv_bytes(report['main_records']).decode('utf-8-sig')
    assert '展示交易所保证金率' in csv_text
    assert '3,628.10 元（历史' in csv_text