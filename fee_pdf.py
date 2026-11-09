"""严格解析先锋期货五列表格式的开户默认手续费 PDF。

仅支持已核验的「交易所/品种/代码/费用方式/交易手续费」表格版式。
不能将 PDF 的“更新日期”误认为每一账户的法定生效日。
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date
from pathlib import Path

EXCHANGES = {
    '上海交易所': 'SHFE',
    '大连交易所': 'DCE',
    '郑州交易所': 'CZCE',
    '广州交易所': 'GFEX',
    '金融交易所': 'CFFEX',
    '能源交易中心': 'INE',
}
FIELDS = ('exchange', 'variety', 'variety_name', 'open_fee_type',
          'open_fee_value', 'effective_from', 'source_note')
MIN_ROWS = 80  # 不允许 PDF 不完整时把旧版88条标准整体覆盖


def parse_company_fee_pdf(raw: bytes) -> tuple[str, list[dict]]:
    """返回 (PDF更新日期 YYYY-MM-DD, 收费表)，严格校验，避免静默错行。"""
    import fitz

    doc = fitz.open(stream=raw, filetype='pdf')
    try:
        text = '\n'.join(page.get_text() for page in doc)
        match = re.search(r'更新日期\s*[:：]\s*(20\d{6})', text)
        if not match:
            raise ValueError('PDF中没有找到“更新日期：YYYYMMDD”，拒绝覆盖基准')
        stamp = match.group(1)
        update_date = date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:])).isoformat()
        rows = []
        for page_num, page in enumerate(doc, start=1):
            lines = [line.strip() for line in page.get_text().splitlines() if line.strip()]
            indices = [i for i, s in enumerate(lines) if s in EXCHANGES]
            if not indices:
                continue
            i = indices[0]
            while i < len(lines):
                if len(lines) - i < 5 or lines[i] not in EXCHANGES:
                    raise ValueError(f'第{page_num}页表格结构异常（位置{i}），拒绝导入')
                exch, name, code, rule, amount = lines[i:i+5]
                if not re.fullmatch(r'[A-Za-z]{1,3}', code):
                    raise ValueError(f'第{page_num}页代码异常：{code!r}')
                if rule not in ('固定金额(元/手)', '成交金额比例'):
                    raise ValueError(f'第{page_num}页收费方式异常：{rule!r}')
                if not re.fullmatch(r'\d+(?:\.\d+)?', amount):
                    raise ValueError(f'第{page_num}页费率数值异常：{amount!r}')
                if rule == '成交金额比例' and float(amount) > 0.1:
                    raise ValueError(f'第{page_num}页比例费率异常：{amount!r}')
                if rule == '固定金额(元/手)' and float(amount) > 10000:
                    raise ValueError(f'第{page_num}页固定费异常：{amount!r}')
                rows.append({
                    'exchange': EXCHANGES[exch], 'variety': code.lower(),
                    'variety_name': name,
                    'open_fee_type': 'FIXED' if rule.startswith('固定') else 'RATE',
                    'open_fee_value': amount, 'effective_from': update_date,
                    'source_note': f'先锋期货开户默认手续费PDF，更新日期{update_date}；非账户级费率；平今需另行确认',
                })
                i += 5
        keys = [(r['exchange'], r['variety']) for r in rows]
        if len(rows) < MIN_ROWS or len(set(keys)) != len(keys) or set(r['exchange'] for r in rows) != set(EXCHANGES.values()):
            raise ValueError('收费表数量不足、品种重复或未覆盖六交易所；拒绝覆盖基准')
        return update_date, sorted(rows, key=lambda r: (r['exchange'], r['variety']))
    finally:
        doc.close()


def csv_bytes(rows: list[dict]) -> bytes:
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return ('\ufeff' + stream.getvalue()).encode('utf-8')


def fee_diff(old: list[dict], new: list[dict]) -> list[dict]:
    by_old = {(r['exchange'], r['variety'].lower()): r for r in old}
    by_new = {(r['exchange'], r['variety'].lower()): r for r in new}
    differences = []
    for key in sorted(by_old.keys() | by_new.keys()):
        before, after = by_old.get(key), by_new.get(key)
        oldval = None if not before else (before['open_fee_type'], float(before['open_fee_value']))
        newval = None if not after else (after['open_fee_type'], float(after['open_fee_value']))
        if oldval != newval:
            differences.append({'交易所': key[0], '品种代码': key[1], '旧标准': oldval, '新标准': newval})
    return differences


def install_fee_pdf(raw: bytes, folder: Path) -> dict:
    """验证并安装新版：先备份当前配置；版本倒退则拒绝。"""
    from core import _load_csv

    version, new = parse_company_fee_pdf(raw)
    path = folder / 'company_fees.csv'
    old = _load_csv(path)
    versions = [r.get('effective_from', '') for r in old if r.get('effective_from')]
    latest_old = max(versions) if versions else None
    if latest_old and version < latest_old:
        raise ValueError(f'导入PDF版本{version}早于当前{latest_old}，拒绝覆盖')
    changes = fee_diff(old, new)
    history = folder / 'history'
    history.mkdir(parents=True, exist_ok=True)
    if old:
        backup = history / f'company_fees_{latest_old.replace("-", "") if latest_old else "legacy"}.csv'
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
    target = history / f'company_fees_{version.replace("-", "")}.csv'
    content = csv_bytes(new)
    target.write_bytes(content)
    path.write_bytes(content)
    return {'version': version, 'rows': len(new), 'changed_rates': changes}
