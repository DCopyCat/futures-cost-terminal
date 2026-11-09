from __future__ import annotations
import sys
from pathlib import Path
from datetime import date,datetime
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from cne_provider import CNEquityFuturesAPI, parse_bars
from core import generate, package_report

D=date(2026,11,6)
NOW=datetime(2026,11,9,9,0,tzinfo=ZoneInfo('Asia/Shanghai'))
RECORDS=[
 {'symbol':'RB2701.SHF','exchange':'SHF','exchange_code':'rb2701','product':'RB','trade_date':D,'settle':3200,'open_interest':500,'volume':2000,'source':'shfe'},
 {'symbol':'RB2705.SHF','exchange':'SHF','exchange_code':'rb2705','product':'RB','trade_date':D,'settle':3100,'open_interest':400,'volume':2500,'source':'shfe'},
 {'symbol':'SC2701.INE','exchange':'INE','product':'SC','trade_date':D,'settle':515,'open_interest':100,'volume':100,'source':'ine'},
 {'symbol':'M2701.DCE','exchange':'DCE','product':'M','trade_date':D,'settle':3100,'open_interest':2500,'volume':1200,'source':'sina'},
 {'symbol':'M2705.DCE','exchange':'DCE','product':'M','trade_date':D,'settle':3050,'open_interest':1000,'volume':2000,'source':'sina'},
 {'symbol':'TA2701.CZC','exchange':'CZC','product':'TA','trade_date':D,'settle':5600,'open_interest':500,'volume':800,'source':'czce'},
 {'symbol':'IF2612.CFE','exchange':'CFE','product':'IF','trade_date':D,'settle':4030,'open_interest':1500,'volume':100,'source':'cffex'},
 {'symbol':'LC2701.GFE','exchange':'GFE','product':'LC','trade_date':D,'settle':89500,'open_interest':390,'volume':1200,'source':'gfex'},
]
class FakeMargin:
 def futures_settle(self,date,market):
  return [{'symbol':'rb2701','date':date,'spec_long_margin_ratio':'12%', 'spec_short_margin_ratio':'12%'}] if market=='SHFE' else []


def test_cne_parse():
 data,diag=parse_bars(RECORDS,'20261101','20261108')
 assert sum(map(len,data.values()))==8
 assert len(data['SHFE'])==2 and len(data['DCE'])==2 and len(data['INE'])==1
 assert data['CZCE'][0]['symbol']=='ta2701'
 assert data['DCE'][0]['origin'].startswith('CNEquity')
 assert diag['upstream']['DCE:sina']==2
 # Reject spoofed exchange and bad/negative settlement and old days
 extra=RECORDS+[{'symbol':'RB2701.SHF','exchange':'DCE','trade_date':D,'settle':1},
             {'symbol':'IF2612.CFE','exchange':'CFE','trade_date':date(2026,10,28),'settle':500}]
 _,diag=parse_bars(extra,'20261101','20261108')
 assert diag['rejected']['非法合约/交易日/交易所']==2


def test_free_price_and_main_selection():
 loader=lambda start,end:RECORDS
 api=CNEquityFuturesAPI(Path('mock'),loader=loader,margin_api=FakeMargin())
 report=generate(api,now=NOW)
 assert not report['missing_markets']
 assert report['price_date']=='2026-11-06'
 assert report['cn_equity_source_quality']['accepted']==8
 assert len(report['main_records'])==6
 rb=next(r for r in report['main_records'] if r['variety']=='rb')
 assert rb['contract']=='rb2701' and rb['is_main']=='是'
 assert rb['notional']==32000 and rb['company_fee_open']==16
 assert rb['exchange_margin_long_pct']==12
 m=next(r for r in report['main_records'] if r['variety']=='m')
 assert m['contract']=='m2701' and m['company_fee_open']==7.5
 assert 'sina' in m['data_source']
 assert m['exchange_margin_long_pct'] is None
 assert m['company_margin_one_lot'] is None
 assert '待核' in m['data_status']
 archive,_=package_report(report)
 assert archive.startswith(b'PK')


def test_no_phantom_prices():
 api=CNEquityFuturesAPI(Path('mock'),loader=lambda start,end:[])
 try:
  generate(api,now=NOW)
 except RuntimeError as exc:
  assert '未取得有效日行情' in str(exc)
 else:
  raise AssertionError('Empty CNEquity lake must not silently generate real report')


def test_no_future_no_outdated_day():
 rows=[{**RECORDS[0], 'trade_date':date(2026,10,15)}]
 api=CNEquityFuturesAPI(Path('mock'),loader=lambda start,end:rows)
 try:
  generate(api,now=NOW)
 except RuntimeError:
  pass
 else:
  raise AssertionError('Stale month data should not be silently used')

if __name__=='__main__':
 test_cne_parse(); test_free_price_and_main_selection(); test_no_phantom_prices();test_no_future_no_outdated_day()
 print('PASS CNEquity 6 markets / actual contracts / settlement / open interest / main selection / missing DCE margin / empty no report')


def test_cne_config_creation_with_stub(tmp_path,monkeypatch):
 import cne_runner as run
 import tomlkit
 path=tmp_path/'lake'/'futures.toml'
 root=tmp_path/'data'
 monkeypatch.setattr(run,'CNE_DIR',tmp_path/'lake')
 monkeypatch.setattr(run,'CNE_CONFIG',path)
 monkeypatch.setattr(run,'CNE_DATA',root)
 def fake_cmd(args,timeout=150):
  if args[:2]==['config','create']:
   path.write_text('extends = "builtin"\n\n[data]\nroot = "'+str(root).replace('\\','/')+'"\n',encoding='utf-8')
  return {'args':args,'exit_code':0,'output':'OK'}
 monkeypatch.setattr(run,'invoke',fake_cmd)
 out=run.ensure_config()
 assert len(out)==2 and path.exists()
 cfg=tomlkit.parse(path.read_text(encoding='utf-8'))
 assert cfg['futures']['enabled'] is True
 assert cfg['futures']['dce_route']=='sina'
 assert cfg['futures']['exchanges']==['SHF','CZC','GFE','CFE','DCE']
 assert cfg['sources']['futures_exchange']['enabled'] is True
