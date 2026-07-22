# -*- coding: utf-8 -*-
"""数据存储模块：JSON 文件持久化。

存储内容：工单、客户经理、节假日/调休上班日、模板配置。
数据文件为 data_dir 下的 store.json，目录与文件自动创建。
"""

import json
import os
from datetime import date

# 模板配置默认值（供导出报告、单据统计等界面功能使用）
DEFAULT_CONFIG = {
    'gas_company': '南京滨海燃气公司',
    'builder_name': '南京力诺建设有限公司',
    'builder_leader': '张礼安',
    'builder_phone': '18761614484',
    'org_name': '国网江苏省电力有限公司南京市溧水区供电分公司',
    'company_short': '溧水区供电公司',
    'dig_depth_cm': 40,
}


class Store:
    """工单助手的本地 JSON 存储。"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self._path = os.path.join(data_dir, 'store.json')
        if os.path.exists(self._path):
            with open(self._path, 'r', encoding='utf-8') as f:
                self._data = json.load(f)
        else:
            self._data = {}
        # 补齐顶层结构，兼容旧文件
        self._data.setdefault('orders', {})
        self._data.setdefault('managers', {})
        self._data.setdefault('supply_orders', {})
        self._data.setdefault('holidays', [])
        self._data.setdefault('extra_workdays', [])
        # 配置：默认值打底，已存值覆盖
        cfg = dict(DEFAULT_CONFIG)
        cfg.update(self._data.get('config', {}))
        self._data['config'] = cfg
        self._save()

    # ---------- 内部 ----------

    def _save(self) -> None:
        with open(self._path, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    # ---------- 工单 ----------

    def add_order(self, order: dict) -> None:
        """新增工单；flow_id 重复时抛 ValueError。"""
        flow_id = order.get('flow_id')
        if not flow_id:
            raise ValueError('工单缺少 flow_id')
        if flow_id in self._data['orders']:
            raise ValueError(f'流程编号已存在：{flow_id}')
        self._data['orders'][flow_id] = dict(order)
        self._save()

    def update_order(self, flow_id: str, order: dict) -> None:
        """按 flow_id 更新工单（整体替换字段，flow_id 保持不变）。"""
        if flow_id not in self._data['orders']:
            raise KeyError(f'工单不存在：{flow_id}')
        new_order = dict(order)
        new_order['flow_id'] = flow_id
        self._data['orders'][flow_id] = new_order
        self._save()

    def delete_order(self, flow_id: str) -> None:
        """删除工单。"""
        self._data['orders'].pop(flow_id, None)
        self._save()

    def get_order(self, flow_id: str) -> dict | None:
        """按 flow_id 取工单，不存在返回 None。"""
        order = self._data['orders'].get(flow_id)
        return dict(order) if order is not None else None

    def list_orders(self) -> list:
        """返回全部工单列表。"""
        return [dict(o) for o in self._data['orders'].values()]

    def finish_order(self, flow_id: str) -> None:
        """将工单状态置为 '已办结'。"""
        if flow_id not in self._data['orders']:
            raise KeyError(f'工单不存在：{flow_id}')
        self._data['orders'][flow_id]['status'] = '已办结'
        self._save()

    # ---------- 供方单台账 ----------

    # 供方单生成类字段：upsert 时可被刷新
    _SUPPLY_GEN_KEYS = (
        'manager', 'account_no', 'account_name', 'address',
        'start_time', 'push_time', 'overdue_time',
        'work_desc', 'materials', 'supply',
    )
    # 供方单手工字段：upsert 时保留已存值，新插入时缺省补 ''
    _SUPPLY_MANUAL_KEYS = (
        'archived', 'progress_marketing', 'progress_equipment',
        'remark', 'contractor',
    )

    def add_supply_order(self, record: dict) -> None:
        """新增供方单台账记录；flow_id 重复时抛 ValueError。"""
        flow_id = record.get('flow_id')
        if not flow_id:
            raise ValueError('供方单缺少 flow_id')
        if flow_id in self._data['supply_orders']:
            raise ValueError(f'供方单流程编号已存在：{flow_id}')
        self._data['supply_orders'][flow_id] = self._normalize_supply(record)
        self._save()

    def upsert_supply_order(self, record: dict) -> None:
        """按 flow_id 新增或更新供方单。

        已存在时只刷新生成类字段（_SUPPLY_GEN_KEYS），保留手工字段；
        不存在则整条插入，手工字段缺省补 ''。
        """
        flow_id = record.get('flow_id')
        if not flow_id:
            raise ValueError('供方单缺少 flow_id')
        if flow_id in self._data['supply_orders']:
            old = self._data['supply_orders'][flow_id]
            new = self._normalize_supply(record)
            # 保留已存的手工字段
            for key in self._SUPPLY_MANUAL_KEYS:
                new[key] = old.get(key, '')
            self._data['supply_orders'][flow_id] = new
        else:
            self._data['supply_orders'][flow_id] = self._normalize_supply(record)
        self._save()

    def get_supply_order(self, flow_id: str) -> dict | None:
        """按 flow_id 取供方单记录，不存在返回 None。"""
        record = self._data['supply_orders'].get(flow_id)
        return dict(record) if record is not None else None

    def list_supply_orders(self) -> list:
        """返回全部供方单台账记录列表。"""
        return [dict(r) for r in self._data['supply_orders'].values()]

    def update_supply_order(self, flow_id: str, record: dict) -> None:
        """按 flow_id 更新供方单（整体替换字段），不存在抛 KeyError。"""
        if flow_id not in self._data['supply_orders']:
            raise KeyError(f'供方单不存在：{flow_id}')
        new_record = self._normalize_supply(record)
        new_record['flow_id'] = flow_id
        self._data['supply_orders'][flow_id] = new_record
        self._save()

    def delete_supply_order(self, flow_id: str) -> None:
        """删除供方单台账记录。"""
        self._data['supply_orders'].pop(flow_id, None)
        self._save()

    @classmethod
    def _normalize_supply(cls, record: dict) -> dict:
        """规整供方单记录：拷贝一份并给手工字段缺省补 ''。"""
        new = dict(record)
        for key in cls._SUPPLY_MANUAL_KEYS:
            new.setdefault(key, '')
        return new

    # ---------- 客户经理 ----------

    def list_managers(self) -> list:
        """返回客户经理列表，元素为 {'name', 'phone'}。"""
        return [dict(m) for m in self._data['managers'].values()]

    def add_manager(self, name: str, phone: str) -> None:
        """新增客户经理；姓名重复时抛 ValueError。"""
        if name in self._data['managers']:
            raise ValueError(f'客户经理已存在：{name}')
        self._data['managers'][name] = {'name': name, 'phone': phone}
        self._save()

    def update_manager(self, name: str, phone: str) -> None:
        """更新客户经理手机号（不存在则按新增处理）。"""
        self._data['managers'][name] = {'name': name, 'phone': phone}
        self._save()

    def delete_manager(self, name: str) -> None:
        """删除客户经理。"""
        self._data['managers'].pop(name, None)
        self._save()

    def get_manager_phone(self, name: str) -> str:
        """按姓名取客户经理手机号，不存在返回空字符串。"""
        m = self._data['managers'].get(name)
        return m['phone'] if m else ''

    # ---------- 节假日与调休 ----------

    def get_holidays(self) -> set:
        """返回节假日集合 set[date]。"""
        return {date.fromisoformat(s) for s in self._data['holidays']}

    def set_holidays(self, dates: set) -> None:
        """设置节假日集合，元素可为 date 或 ISO 日期字符串。"""
        self._data['holidays'] = sorted(self._to_iso(d) for d in dates)
        self._save()

    def get_extra_workdays(self) -> set:
        """返回调休上班日集合 set[date]。"""
        return {date.fromisoformat(s) for s in self._data['extra_workdays']}

    def set_extra_workdays(self, dates: set) -> None:
        """设置调休上班日集合，元素可为 date 或 ISO 日期字符串。"""
        self._data['extra_workdays'] = sorted(self._to_iso(d) for d in dates)
        self._save()

    @staticmethod
    def _to_iso(d) -> str:
        """把 date 或字符串统一转为 ISO 日期字符串。"""
        if isinstance(d, date):
            return d.isoformat()
        return str(d)

    # ---------- 模板配置 ----------

    def get_config(self, key: str, default=None):
        """读取配置项；未设置时返回默认值（内置默认键优先）。"""
        if key in self._data['config']:
            return self._data['config'][key]
        return DEFAULT_CONFIG.get(key, default)

    def set_config(self, key: str, value) -> None:
        """写入配置项。"""
        self._data['config'][key] = value
        self._save()
