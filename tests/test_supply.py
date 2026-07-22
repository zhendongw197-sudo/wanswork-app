# -*- coding: utf-8 -*-
"""supply 供方单业务逻辑测试。

覆盖：材料拼句（空值/多材料组合/顺序）、meter_voltage、表箱型号、
build_field_map 全部键、default_supply 三种流程类型。
"""

import os
import sys

# 保证可以 import app 包（项目根目录加入 sys.path）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.supply import (
    BOX_MOUNTS,
    BOX_PHASES,
    BOX_POSITIONS,
    MATERIAL_COLUMNS,
    MATERIAL_KEYS,
    build_field_map,
    compose_box_model,
    compose_materials_text,
    default_supply,
    meter_voltage,
)


def _empty_materials() -> dict:
    return {key: '' for key in MATERIAL_KEYS}


def test_material_columns_contract():
    """17 键及表头与共享契约一致，顺序固定。"""
    assert len(MATERIAL_COLUMNS) == 17
    assert MATERIAL_COLUMNS[0] == ('cable_2x16', '2*16')
    assert MATERIAL_COLUMNS[6] == ('box_wall', '分支箱（挂壁）')
    assert MATERIAL_COLUMNS[8] == ('mpp100', 'MPP100管子')
    assert MATERIAL_COLUMNS[-1] == ('overhead', '架空导线')
    assert len(MATERIAL_KEYS) == 17 and MATERIAL_KEYS[3] == 'cable_4x70'
    assert BOX_PHASES == ['单相', '三相']
    assert BOX_POSITIONS[0] == '一表位' and len(BOX_POSITIONS) == 6
    assert BOX_MOUNTS == ['悬挂式', '落地式']


def test_compose_materials_text_single():
    m = _empty_materials()
    m['cable_4x150'] = 185
    assert compose_materials_text(m) == '4*150电缆185米'
    m = _empty_materials()
    m['box_wall'] = 1
    assert compose_materials_text(m) == '挂壁式分支箱1个'
    m = _empty_materials()
    m['box_floor'] = '1'
    assert compose_materials_text(m) == '落地式分支箱1个'
    m = _empty_materials()
    m['mpp100'] = 160
    assert compose_materials_text(m) == '两孔100MPP加筋排管160米'
    m = _empty_materials()
    m['tray_200x100'] = 30
    assert compose_materials_text(m) == '200*100桥架30米'
    m = _empty_materials()
    m['tray_300x150'] = 30
    assert compose_materials_text(m) == '300*150桥架30米'
    m = _empty_materials()
    m['term_240'] = 2
    assert compose_materials_text(m) == '240冷缩终端2套'
    m = _empty_materials()
    m['overhead'] = 50
    assert compose_materials_text(m) == '架空导线50米'


def test_compose_materials_text_empty():
    """空 dict / 全空 / 0 值均返回 ''。"""
    assert compose_materials_text({}) == ''
    assert compose_materials_text(_empty_materials()) == ''
    m = _empty_materials()
    m['cable_4x16'] = 0
    m['mpp100'] = '0'
    m['term_16'] = '  '
    assert compose_materials_text(m) == ''


def test_compose_materials_text_multi_and_order():
    """多材料组合按 MATERIAL_COLUMNS 顺序拼接，'，' 连接。"""
    m = _empty_materials()
    m['overhead'] = 50
    m['cable_4x150'] = '185'   # str 数字容错
    m['term_240'] = 2
    m['box_wall'] = 1
    # 契约顺序：cable_4x150(第5) < box_wall(第7) < term_240(第16) < overhead(第17)
    assert compose_materials_text(m) == '4*150电缆185米，挂壁式分支箱1个，240冷缩终端2套，架空导线50米'


def test_compose_materials_text_tolerant():
    """float 整数显示为整数，非法值跳过。"""
    m = _empty_materials()
    m['cable_2x16'] = 30.0
    m['cable_4x35'] = 'abc'
    assert compose_materials_text(m) == '2*16电缆30米'


def test_meter_voltage():
    assert meter_voltage('220') == '220'
    assert meter_voltage('380') == '3×220/380'
    assert meter_voltage('') == '220'


def test_compose_box_model():
    assert compose_box_model('400A', '三相', '一表位', '落地式') == '400A三相一表位落地式表箱'
    # 电流为空时不带前缀
    assert compose_box_model('', '单相', '一表位', '悬挂式') == '单相一表位悬挂式表箱'
    assert compose_box_model('100A', '单相', '两表位', '悬挂式') == '100A单相两表位悬挂式表箱'


def _sample_order() -> dict:
    return {
        'flow_id': '202401010001',
        'flow_type': '低压非居民新装',
        'account_name': '张三商店',
        'account_no': '3300123456',
        'address': '某某路 1 号',
        'phone': '13800000000',
    }


def _sample_supply() -> dict:
    s = default_supply(_sample_order())
    s.update({
        'capacity': '100',
        'line': '10kV城东线',
        'transformer': '城东1号变',
        'contract_capacity': '80',
        'last_year_load': '60',
        'connection': '电缆',
        'meter_current': '400A',
        'price': '0.8',
    })
    return s


def test_build_field_map_all_keys():
    """全部 21 个红字占位键精确存在且取值正确。"""
    order = _sample_order()
    supply = _sample_supply()
    supply['materials']['cable_4x150'] = 185
    supply['materials']['term_240'] = 2
    fmap = build_field_map(order, supply)

    expected_keys = {
        '流程编号', '工单类型', '户名', '户号', '地址', '用户电话',
        '行业分类', '供电电压', '批准容量', '线路', '变压器名称',
        '和同容量', '合同容量', '去年负荷', '接户方式', '施工规格',
        '表箱型号', '电表电压型号', '电表电流型号', '电价', '线路 变压器名称',
    }
    assert set(fmap.keys()) == expected_keys

    assert fmap['流程编号'] == '202401010001'
    assert fmap['工单类型'] == '低压非居民新装'
    assert fmap['户名'] == '张三商店'
    assert fmap['户号'] == '3300123456'
    assert fmap['地址'] == '某某路 1 号'
    assert fmap['用户电话'] == '13800000000'
    assert fmap['行业分类'] == '商业'
    assert fmap['供电电压'] == '380'
    assert fmap['批准容量'] == '100'
    assert fmap['线路'] == '10kV城东线'
    assert fmap['变压器名称'] == '城东1号变'
    # 模板笔误兼容：两个键都映射到合同容量
    assert fmap['和同容量'] == '80'
    assert fmap['合同容量'] == '80'
    assert fmap['去年负荷'] == '60'
    assert fmap['接户方式'] == '电缆'
    assert fmap['施工规格'] == '4*150电缆185米，240冷缩终端2套'
    assert fmap['表箱型号'] == '400A三相一表位悬挂式表箱'
    assert fmap['电表电压型号'] == '3×220/380'
    assert fmap['电表电流型号'] == '400A'
    assert fmap['电价'] == '0.8'
    assert fmap['线路 变压器名称'] == '10kV城东线 城东1号变'


def test_default_supply_resident():
    """低压居民新装/增容（含'居民'不含'非居民'）→ 220V / 单相 / 居民生活用电。"""
    for flow_type in ('低压居民新装', '低压居民增容'):
        s = default_supply({'flow_type': flow_type})
        assert s['voltage'] == '220'
        assert s['box_phase'] == '单相'
        assert s['industry'] == '居民生活用电'
        assert s['box_positions'] == '一表位'
        assert s['box_mount'] == '悬挂式'
        assert all(v == '' for v in s['materials'].values())
        assert set(s['materials'].keys()) == set(MATERIAL_KEYS)


def test_default_supply_non_resident():
    """低压非居民新装/增容 → 380V / 三相 / 商业。"""
    for flow_type in ('低压非居民新装', '低压非居民增容'):
        s = default_supply({'flow_type': flow_type})
        assert s['voltage'] == '380'
        assert s['box_phase'] == '三相'
        assert s['industry'] == '商业'


def test_default_supply_charging_pile():
    """低压充电桩新装/增容 → 380V / 三相 / 电动汽车充电。"""
    for flow_type in ('低压充电桩新装', '低压充电桩增容'):
        s = default_supply({'flow_type': flow_type})
        assert s['voltage'] == '380'
        assert s['box_phase'] == '三相'
        assert s['industry'] == '电动汽车充电'
    # 未知类型兜底：380V，行业为空
    s2 = default_supply({'flow_type': '未知类型'})
    assert s2['voltage'] == '380' and s2['industry'] == ''


if __name__ == '__main__':
    # pytest 不可用时可直接 python tests/test_supply.py 运行
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
