"""Run documented CNEquity CLI for *futures only*, preserving output diagnostics.

No stock market cne init; first capture is a short futures_bars window.
Never tries to evade 403/412/captcha, and never treats exit code 1 as fresh data.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import json
import os
import subprocess
import sys
import tomlkit

from core import BASE, TZ, _today_cutoff

CNE_DIR=BASE/'cn_equity_lake'
CNE_CONFIG=CNE_DIR/'cnequity.futures.toml'
CNE_DATA=CNE_DIR/'data'
LOG_DIR=BASE/'logs'


def cne_bin() -> str:
    exe=Path(sys.executable).parent/('cne.exe' if os.name=='nt' else 'cne')
    if not exe.exists():
        raise RuntimeError('未安装 cnequity 或虚拟环境不完整，请重新运行启动工作台.bat 安装依赖')
    return str(exe)


def invoke(args: list[str],timeout:int=150) -> dict:
    """Subprocess runs synchronously, captures bounded tail and never uses shell."""
    cmd=[cne_bin(),*args]
    try:
        proc=subprocess.run(cmd,cwd=str(BASE),text=True,encoding='utf-8',errors='replace',
                            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout,
                            env={**os.environ,'PYTHONUTF8':'1'})
        return {'args':args,'exit_code':proc.returncode,'output':proc.stdout[-28000:]}
    except subprocess.TimeoutExpired as e:
        output=e.stdout or b''
        if isinstance(output,bytes):output=output.decode('utf-8','replace')
        return {'args':args,'exit_code':124,'output':output[-16000:]+'\n达到本次采集超时限制，可能已有部分交易所写入。'}
    except Exception as e:
        return {'args':args,'exit_code':125,'output':f'{type(e).__name__}: {e}'}


def ensure_config() -> list[dict]:
    CNE_DIR.mkdir(parents=True,exist_ok=True)
    history=[]
    if not CNE_CONFIG.exists():
        result=invoke(['config','create','--config',str(CNE_CONFIG),'--data-root',str(CNE_DATA)],timeout=70)
        history.append(result)
        if result['exit_code']!=0 or not CNE_CONFIG.exists():
            raise RuntimeError('CNEquity 配置创建失败: '+result['output'][-1400:])
    doc=tomlkit.parse(CNE_CONFIG.read_text(encoding='utf-8'))
    if 'futures' not in doc: doc['futures']=tomlkit.table()
    fut=doc['futures']
    fut['enabled']=True
    # INE is included in SHF route by CNEquity; SIX actual exchange markets.
    fut['exchanges']=['SHF','CZC','GFE','CFE','DCE']
    fut['options']=False
    fut['dce_route']='sina'  # Free but unverified for zero-trade DCE contracts.
    fut['minute_enabled']=False
    if 'sources' not in doc:doc['sources']=tomlkit.table()
    if 'futures_exchange' not in doc['sources']:doc['sources']['futures_exchange']=tomlkit.table()
    doc['sources']['futures_exchange']['enabled']=True
    doc['sources']['futures_exchange']['min_interval_seconds']=1.0
    CNE_CONFIG.write_text(tomlkit.dumps(doc),encoding='utf-8')
    result=invoke(['config','validate','--config',str(CNE_CONFIG)],timeout=45)
    history.append(result)
    if result['exit_code']!=0:
        raise RuntimeError('CNEquity 期货配置校验失败: '+result['output'][-2000:])
    return history


def refresh_daily(now:datetime|None=None,days:int=8,include_dce:bool=True,progress=None) -> dict:
    """First/regular click: short-window source capture, then read local lake.

    An exit code 1 may mean metadata degraded despite some published daily bars.
    Exact upstream status and log is still exposed to the user.
    """
    now=now or datetime.now(TZ)
    cutoff=_today_cutoff(now)
    start=cutoff-timedelta(days=days)
    history=[]
    try:
        if progress:progress('正在创建/验证独立期货湖配置……')
        history.extend(ensure_config())
        # We explicitly backfill a narrow window: no need to initialise all A stocks.
        # SHF route also contains INE; DCE Sina route is run separately so it cannot
        # block the five official-file markets. Don't spam a blocked origin.
        jobs=[(['SHF','CZC','GFE','CFE'],300)]
        if include_dce:
            jobs.append((['DCE'],900))  # Sina may enumerate hundreds of DCE contract histories.
        for exchanges,timeout in jobs:
            if progress:progress(('大商所：正在逐合约采集（免费新浪数据，上游请求较多）……' if exchanges==['DCE'] else '正在采集上期所/能源/郑商所/广期所/中金所……'))
            args=['backfill','futures_bars','--config',str(CNE_CONFIG),
                  '--start',start.isoformat(),'--end',cutoff.isoformat()]
            for ex in exchanges: args.extend(['--exchange',ex])
            step=invoke(args,timeout=timeout)
            history.append(step)
            if progress:progress(f'已完成 {",".join(exchanges)} 采集步骤，退出码 {step["exit_code"]}。')
        status='完成' if all(h['exit_code']==0 for h in history) else '部分失败/需核验'
    except Exception as exc:
        status='配置/更新失败'
        history.append({'args':['setup'], 'exit_code':125, 'output':str(exc)})
    LOG_DIR.mkdir(exist_ok=True)
    outcome={'status':status,'date_window':[start.isoformat(),cutoff.isoformat()],
             'config_path':str(CNE_CONFIG),'data_root':str(CNE_DATA),'included_dce':include_dce,'steps':history}
    (LOG_DIR/'cne_last_run.json').write_text(json.dumps(outcome,ensure_ascii=False,indent=2),encoding='utf-8')
    return outcome
