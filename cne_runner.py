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


def ensure_config(include_dce: bool=True) -> list[dict]:
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
    fut['exchanges']=['SHF','CZC','GFE','CFE']+(['DCE'] if include_dce else [])
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


def lake_snapshot(start:date,end:date) -> dict:
    """Inspect locally published futures bars only; never makes network requests."""
    if not CNE_CONFIG.exists():
        return {'available':False,'by_exchange':{},'error':'独立期货湖尚未初始化'}
    try:
        from cne_provider import CNEquityFuturesAPI
        api=CNEquityFuturesAPI(CNE_CONFIG)
        counts={}
        for local in ('SHFE','INE','DCE','CZCE','CFFEX','GFEX'):
            bars=api.get_futures_daily(start.strftime('%Y%m%d'),end.strftime('%Y%m%d'),local)
            days={str(r['date']) for r in bars}
            counts[local]={'rows':len(bars),'last_day':max(days) if days else None}
        return {'available':any(v['rows'] for v in counts.values()),
                'by_exchange':counts,'quality':api.quality}
    except Exception as exc:
        return {'available':False,'by_exchange':{},
                'error':f'{type(exc).__name__}: {str(exc)[:180]}'}


def refresh_daily(now:datetime|None=None,days:int=8,include_dce:bool=True,progress=None,
                  force_backfill:bool=False) -> dict:
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
        existing = lake_snapshot(start,cutoff)
        history.extend(ensure_config(include_dce=include_dce))
        # First run: backfill a small window, not the A-share universe.
        # Subsequent runs: use CNE's incremental derivative schedule to avoid
        # hundreds of repeated DCE Sina contract-history requests each morning.
        mode = 'small_backfill' if force_backfill or not existing.get('available') else 'incremental_daily'
        if mode=='incremental_daily':
            if progress:progress('已有本地期货湖，执行衍生品增量日更，避免重复全窗口抓取。')
            args=['run','daily','--group','derivatives','--config',str(CNE_CONFIG)]
            step=invoke(args,timeout=900 if include_dce else 360)
            history.append(step)
        else:
            jobs=[(['SHF','CZC','GFE','CFE'],300)]
            if include_dce:
                jobs.append((['DCE'],900))
            for exchanges,timeout in jobs:
                if progress:progress(('大商所：首次/人工修复短窗口逐合约采集……' if exchanges==['DCE'] else '首次/人工修复交易所短窗口行情……'))
                args=['backfill','futures_bars','--config',str(CNE_CONFIG),
                      '--start',start.isoformat(),'--end',cutoff.isoformat()]
                for ex in exchanges:args.extend(['--exchange',ex])
                step=invoke(args,timeout=timeout)
                history.append(step)
                if progress:progress(f'已完成 {",".join(exchanges)} 采集步骤，退出码 {step["exit_code"]}。')
        after = lake_snapshot(start,cutoff)
        capture_codes=[h['exit_code'] for h in history if h['args'] and h['args'][0] in ('backfill','run')]
        status='采集步骤成功（完整性仍需单独核验）' if capture_codes and all(code==0 for code in capture_codes) else '部分失败/元数据降级（检查已落盘行情）'
        # Separate the optional quality gate from the actual market capture. CNEquity
        # may return 1 for a degraded GFE contract-reference followup even when
        # futures_bars have been committed; exit 2 from status means unverified.
        if progress:progress('正在核查衍生品数据完整性（不会重新抓取）……')
        quality=invoke(['status','--config',str(CNE_CONFIG),'--datasets','--groups','derivatives','--all-columns'],timeout=60)
        quality['kind']='quality_gate'
        history.append(quality)
        if quality['exit_code']!=0:
            status += '；数据完整性待核'

    except Exception as exc:
        status='配置/更新失败'
        history.append({'args':['setup'], 'exit_code':125, 'output':str(exc)})
    LOG_DIR.mkdir(exist_ok=True)
    outcome={'status':status,'date_window':[start.isoformat(),cutoff.isoformat()],
             'config_path':str(CNE_CONFIG),'data_root':str(CNE_DATA),'included_dce':include_dce,
             'capture_mode':locals().get('mode','setup_failed'),
             'lake_before':locals().get('existing',{}), 'lake_after':locals().get('after',{}),
             'capture_exit_codes':[h['exit_code'] for h in history if h['args'] and h['args'][0] in ('backfill','run')],
             'quality_gate_exit_code':next((h['exit_code'] for h in history if h.get('kind')=='quality_gate'),None),
             'steps':history}
    (LOG_DIR/'cne_last_run.json').write_text(json.dumps(outcome,ensure_ascii=False,indent=2),encoding='utf-8')
    return outcome
