# -*- coding: utf-8 -*-
"""gui 主界面模块测试：列定义、进度选项、_compute_rows 考核规则（共享契约）。

不创建 Tk 窗口：MainWindow 用 __new__ 绕过 __init__，仅注入 store。
"""

import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

# 保证可以 import app 包（项目根目录加入 sys.path）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import gui, worktime
from app.gui import COLUMNS, TERMINAL, MainWindow, progress_options
from app.store import Store


def _make_win(orders):
    """临时目录建 Store 并写入工单，返回 (MainWindow 裸实例, 临时目录)。"""
    d = tempfile.mkdtemp(prefix='workorder_gui_test_')
    store = Store(d)
    for order in orders:
        store.add_order(order)
    win = MainWindow.__new__(MainWindow)
    win.store = store
    return win, d


def _order(flow_id, flow_type='低压非居民新装', status='在办', **kw):
    order = {
        'flow_id': flow_id,
        'flow_type': flow_type,
        'account_no': '3201240001234567',
        'account_name': '张三五金店',
        'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'manager': '李四',
        'status': status,
        'phone': '13800001111',
        'address': '溧水区永阳街道xx路1号',
    }
    order.update(kw)
    return order


def test_columns_address_in_group_before_status():
    """COLUMNS：'地址'/'是否建群' 位于 '状态' 之前，宽度 200/80。"""
    keys = [c[0] for c in COLUMNS]
    assert keys.index('address') < keys.index('status')
    assert keys.index('in_group') < keys.index('status')
    assert keys.index('address') == keys.index('status') - 2
    assert keys.index('in_group') == keys.index('status') - 1
    widths = {c[0]: c[2] for c in COLUMNS}
    assert widths['address'] == 200 and widths['in_group'] == 80
    titles = {c[0]: c[1] for c in COLUMNS}
    assert titles['address'] == '地址' and titles['in_group'] == '是否建群'


def test_terminal_set():
    """终结状态集合含 '流程办结'/'终止'/'已办结'（旧数据兼容）。"""
    assert TERMINAL == {'流程办结', '终止', '已办结'}


def test_progress_options_resident_no_visit():
    """低压居民新装/增容 不显示 '上门服务办结'。"""
    for ft in ('低压居民新装', '低压居民增容'):
        opts = progress_options(ft)
        assert '上门服务办结' not in opts
        assert opts == ['已建群', '流程办结', '终止']


def test_progress_options_non_resident_has_visit():
    """低压充电桩*/低压非居民* 显示 '上门服务办结'，且位于第二项。"""
    for ft in ('低压充电桩新装', '低压充电桩增容', '低压非居民新装', '低压非居民增容'):
        opts = progress_options(ft)
        assert opts == ['已建群', '上门服务办结', '流程办结', '终止']


def test_terminal_rows_not_assessed_and_sink():
    """流程办结/终止/已办结：不考核、剩余 '-'、无标色、排序沉底。"""
    orders = [
        _order('GD001', status='流程办结'),
        _order('GD002', status='终止'),
        _order('GD003', status='已办结'),  # 旧数据兼容
        _order('GD004', status='在办',
               start_time='2020-01-06 08:30:00'),  # 必然超期
    ]
    win, d = _make_win(orders)
    try:
        rows = win._compute_rows()
        by_id = {r['flow_id']: r for r in rows}
        for fid in ('GD001', 'GD002', 'GD003'):
            row = by_id[fid]
            assert row['remaining'] == '-'
            assert row['_status'] == 'none'
        # 超期工单排在最前，三个终结状态沉底且保持相对顺序
        assert [r['flow_id'] for r in rows][0] == 'GD004'
        assert [r['flow_id'] for r in rows][1:] == ['GD001', 'GD002', 'GD003']
        assert by_id['GD004']['_status'] == 'overdue'
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_visit_done_only_assesses_full_deadline():
    """上门服务办结：只考核全流程截止日，忽略已超期的上门服务截止日。"""
    # 6 天前开始：上门服务(4 工作日)已超期，全流程(15 工作日)尚远
    start = (datetime.now() - timedelta(days=6)).strftime('%Y-%m-%d %H:%M:%S')
    visit_dl, full_dl = worktime.compute_deadlines(
        '低压非居民新装', datetime.strptime(start, '%Y-%m-%d %H:%M:%S'), set(), set())
    now = datetime.now()
    assert visit_dl < now < full_dl  # 前提：visit 超期、full 未到期
    orders = [
        _order('GD010', status='上门服务办结', start_time=start),
        _order('GD011', status='在办', start_time=start),  # 对照组：双截止日考核
    ]
    win, d = _make_win(orders)
    try:
        rows = win._compute_rows()
        by_id = {r['flow_id']: r for r in rows}
        done = by_id['GD010']
        assert done['_status'] == 'normal'  # 忽略超期的 visit_dl
        assert '剩' in done['remaining']    # 剩余时间只按 full_dl
        assert done['visit_deadline'] != '-'  # 列仍显示计算值
        assert by_id['GD011']['_status'] == 'overdue'  # 在办仍考核 visit_dl
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_in_progress_dual_deadline():
    """已建群/在办：维持双截止日考核（居民类 visit 为 None 不报错）。"""
    orders = [
        _order('GD020', flow_type='低压居民新装', status='已建群'),
        _order('GD021', flow_type='低压充电桩新装', status='在办'),
    ]
    win, d = _make_win(orders)
    try:
        rows = win._compute_rows()
        by_id = {r['flow_id']: r for r in rows}
        assert by_id['GD020']['_status'] == 'normal'
        assert by_id['GD020']['visit_deadline'] == '-'  # 居民类无上门服务截止日
        assert by_id['GD021']['_status'] == 'normal'
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_in_group_and_status_display():
    """in_group 缺省视为 ''；status 原样显示（含旧数据 '已办结'）。"""
    orders = [
        _order('GD030', status='已建群', in_group='是'),
        _order('GD031', status='已办结'),  # 旧数据：无 in_group 键
    ]
    win, d = _make_win(orders)
    try:
        rows = win._compute_rows()
        by_id = {r['flow_id']: r for r in rows}
        assert by_id['GD030'].get('in_group', '') == '是'
        assert by_id['GD031'].get('in_group', '') == ''
        assert by_id['GD031']['status'] == '已办结'  # 原样显示
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == '__main__':
    # pytest 不可用时可直接 python tests\test_gui.py 运行
    funcs = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith('test_') and callable(fn)]
    failed = 0
    for name, fn in funcs:
        try:
            fn()
            print(f'通过: {name}')
        except AssertionError as e:
            failed += 1
            print(f'失败: {name} -> {e}')
    print(f'\n共 {len(funcs)} 项，失败 {failed} 项')
    sys.exit(1 if failed else 0)
