# -*- coding: utf-8 -*-
"""store 数据存储模块测试：增删改查、flow_id 唯一、配置默认值等。"""

import os
import shutil
import sys
import tempfile
from datetime import date

# 保证可以 import app 包（项目根目录加入 sys.path）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.store import Store


def _make_store():
    """在临时目录中建 Store，返回 (store, 临时目录)。"""
    d = tempfile.mkdtemp(prefix='workorder_test_')
    return Store(d), d


def _sample_order(flow_id='GD20240108001'):
    return {
        'flow_id': flow_id,
        'flow_type': '低压非居民',
        'account_no': '3201240001234567',
        'account_name': '张三五金店',
        'start_time': '2024-01-08 08:30:00',
        'manager': '李四',
        'status': '在办',
        'phone': '13800001111',
        'address': '溧水区永阳街道xx路1号',
    }


def test_store_file_auto_created():
    """data_dir 与 store.json 自动创建。"""
    d = tempfile.mkdtemp(prefix='workorder_test_')
    shutil.rmtree(d)  # 先删掉，验证能自动创建
    Store(os.path.join(d, 'subdir'))
    assert os.path.exists(os.path.join(d, 'subdir', 'store.json'))
    shutil.rmtree(d, ignore_errors=True)


def test_order_crud():
    """工单增删改查。"""
    store, d = _make_store()
    try:
        store.add_order(_sample_order())
        got = store.get_order('GD20240108001')
        assert got is not None and got['account_name'] == '张三五金店'
        assert len(store.list_orders()) == 1

        updated = _sample_order()
        updated['account_name'] = '张三建材店'
        store.update_order('GD20240108001', updated)
        assert store.get_order('GD20240108001')['account_name'] == '张三建材店'

        store.delete_order('GD20240108001')
        assert store.get_order('GD20240108001') is None
        assert store.list_orders() == []
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_flow_id_unique():
    """flow_id 重复时 add_order 抛 ValueError。"""
    store, d = _make_store()
    try:
        store.add_order(_sample_order())
        try:
            store.add_order(_sample_order())
        except ValueError:
            pass
        else:
            raise AssertionError('重复 flow_id 未抛 ValueError')
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_finish_order():
    """办结后状态为 '已办结'。"""
    store, d = _make_store()
    try:
        store.add_order(_sample_order())
        store.finish_order('GD20240108001')
        assert store.get_order('GD20240108001')['status'] == '已办结'
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_manager_crud():
    """客户经理增删改查与按姓名取手机号。"""
    store, d = _make_store()
    try:
        store.add_manager('王五', '13912345678')
        assert store.get_manager_phone('王五') == '13912345678'
        assert store.list_managers() == [{'name': '王五', 'phone': '13912345678'}]

        store.update_manager('王五', '13987654321')
        assert store.get_manager_phone('王五') == '13987654321'

        store.delete_manager('王五')
        assert store.list_managers() == []
        assert store.get_manager_phone('王五') == ''  # 不存在返回空串
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_holidays_roundtrip():
    """节假日与调休集合写入读回一致，且跨实例持久化。"""
    store, d = _make_store()
    try:
        holidays = {date(2024, 1, 8), date(2024, 2, 10)}
        extras = {date(2024, 1, 6)}
        store.set_holidays(holidays)
        store.set_extra_workdays(extras)
        assert store.get_holidays() == holidays
        assert store.get_extra_workdays() == extras

        # 重新打开同一目录，验证持久化
        store2 = Store(d)
        assert store2.get_holidays() == holidays
        assert store2.get_extra_workdays() == extras
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_config_defaults():
    """配置默认值。"""
    store, d = _make_store()
    try:
        assert store.get_config('gas_company') == '南京滨海燃气公司'
        assert store.get_config('builder_name') == '南京力诺建设有限公司'
        assert store.get_config('builder_leader') == '张礼安'
        assert store.get_config('builder_phone') == '18761614484'
        assert store.get_config('org_name') == '国网江苏省电力有限公司南京市溧水区供电分公司'
        assert store.get_config('company_short') == '溧水区供电公司'
        assert store.get_config('dig_depth_cm') == 40
        # 未定义的键返回传入的默认值
        assert store.get_config('不存在的键') is None
        assert store.get_config('不存在的键', '兜底') == '兜底'
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_config_set_get_persist():
    """配置写入后可读回并持久化。"""
    store, d = _make_store()
    try:
        store.set_config('gas_company', '南京某某燃气公司')
        store.set_config('dig_depth_cm', 60)
        assert store.get_config('gas_company') == '南京某某燃气公司'
        assert store.get_config('dig_depth_cm') == 60

        store2 = Store(d)
        assert store2.get_config('gas_company') == '南京某某燃气公司'
        # 改过的键不回退默认值，未改的键仍是默认值
        assert store2.get_config('builder_leader') == '张礼安'
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == '__main__':
    # pytest 不可用时可直接 python tests\test_store.py 运行
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
