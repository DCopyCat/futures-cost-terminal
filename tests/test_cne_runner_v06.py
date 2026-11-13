from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cne_runner


def test_quality_gate_is_independent_of_capture(tmp_path,monkeypatch):
    monkeypatch.setattr(cne_runner,'LOG_DIR',tmp_path)
    monkeypatch.setattr(cne_runner,'CNE_CONFIG',tmp_path/'cnequity.futures.toml')
    monkeypatch.setattr(cne_runner,'CNE_DATA',tmp_path/'data')
    monkeypatch.setattr(cne_runner,'ensure_config',lambda include_dce=True:[{'args':['config','validate'],'exit_code':0,'output':'OK'}])
    commands=[]
    def fake_invoke(args,timeout=150):
        commands.append(args)
        if args[0]=='status':
            return {'args':args,'exit_code':2,'output':'UNVERIFIED (official reference unavailable)'}
        if args[0]=='backfill':
            return {'args':args,'exit_code':1,'output':'followup degraded; bars committed'}
        raise AssertionError(args)
    monkeypatch.setattr(cne_runner,'invoke',fake_invoke)
    monkeypatch.setattr(cne_runner,'lake_snapshot',lambda start,end:{'available':False,'by_exchange':{}})
    now=datetime(2026,11,9,9,tzinfo=ZoneInfo('Asia/Shanghai'))
    result=cne_runner.refresh_daily(now=now,include_dce=False)
    assert result['capture_exit_codes']==[1]
    assert result['quality_gate_exit_code']==2
    assert '完整性待核' in result['status']
    assert len([c for c in commands if c[0]=='backfill'])==1
    assert any(c[0]=='status' and 'derivatives' in c for c in commands)
    assert (tmp_path/'cne_last_run.json').exists()


def test_incremental_daily_avoids_backfill_on_existing_lake(tmp_path,monkeypatch):
    monkeypatch.setattr(cne_runner,'LOG_DIR',tmp_path)
    monkeypatch.setattr(cne_runner,'ensure_config',lambda include_dce=True:[{'args':['config','validate'],'exit_code':0,'output':'OK'}])
    monkeypatch.setattr(cne_runner,'lake_snapshot',lambda start,end:{'available':True,'by_exchange':{'DCE':{'rows':1,'last_day':'20261106'}}})
    commands=[]
    def fake(args,timeout=150):
        commands.append(args)
        return {'args':args,'exit_code':0,'output':'ok'}
    monkeypatch.setattr(cne_runner,'invoke',fake)
    now=datetime(2026,11,9,9,tzinfo=ZoneInfo('Asia/Shanghai'))
    result=cne_runner.refresh_daily(now=now)
    assert result['capture_mode']=='incremental_daily'
    assert result['capture_exit_codes']==[0]
    assert any(cmd[:4]==['run','daily','--group','derivatives'] for cmd in commands)
    assert all(cmd[0]!='backfill' for cmd in commands)
