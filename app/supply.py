# -*- coding: utf-8 -*-
"""供方单业务逻辑：材料拼句、表箱型号、红字占位字段映射与默认供方数据。

纯逻辑模块，不读写文件，不依赖其他新增模块。
共享契约：materials 为 17 键 dict（MATERIAL_COLUMNS 顺序固定），值为数字或 ''。
"""

# 材料列定义：(key, 台账表头)，顺序固定，拼句与导出均按此顺序
MATERIAL_COLUMNS = [
    ('cable_2x16', '2*16'),
    ('cable_4x16', '4*16'),
    ('cable_4x35', '4*35'),
    ('cable_4x70', '4*70'),
    ('cable_4x150', '4*150'),
    ('cable_4x240', '4*240'),
    ('box_wall', '分支箱（挂壁）'),
    ('box_floor', '分支箱（落地）'),
    ('mpp100', 'MPP100管子'),
    ('tray_200x100', '桥架（200*100）'),
    ('tray_300x150', '桥架（300*150）'),
    ('term_16', '16冷缩终端'),
    ('term_35', '35冷缩终端'),
    ('term_70', '70冷缩终端'),
    ('term_150', '150冷缩终端'),
    ('term_240', '240冷缩终端'),
    ('overhead', '架空导线'),
]

MATERIAL_KEYS = [key for key, _ in MATERIAL_COLUMNS]

# 表箱可选值
BOX_PHASES = ['单相', '三相']
BOX_POSITIONS = ['一表位', '两表位', '四表位', '六表位', '九表位', '十二表位']
BOX_MOUNTS = ['悬挂式', '落地式']

# 材料拼句模板：key -> 含 {n} 数量占位的句式
_MATERIAL_PHRASES = {
    'cable_2x16': '2*16电缆{n}米',
    'cable_4x16': '4*16电缆{n}米',
    'cable_4x35': '4*35电缆{n}米',
    'cable_4x70': '4*70电缆{n}米',
    'cable_4x150': '4*150电缆{n}米',
    'cable_4x240': '4*240电缆{n}米',
    'box_wall': '挂壁式分支箱{n}个',
    'box_floor': '落地式分支箱{n}个',
    'mpp100': '两孔100MPP加筋排管{n}米',
    'tray_200x100': '200*100桥架{n}米',
    'tray_300x150': '300*150桥架{n}米',
    'term_16': '16冷缩终端{n}套',
    'term_35': '35冷缩终端{n}套',
    'term_70': '70冷缩终端{n}套',
    'term_150': '150冷缩终端{n}套',
    'term_240': '240冷缩终端{n}套',
    'overhead': '架空导线{n}米',
}

# 流程类型默认行业分类
_INDUSTRY_DEFAULTS = {
    '低压居民新装': '居民生活用电',
    '低压居民增容': '居民生活用电',
    '低压充电桩新装': '电动汽车充电',
    '低压充电桩增容': '电动汽车充电',
    '低压非居民新装': '商业',
    '低压非居民增容': '商业',
}


def _format_num(value) -> str:
    """容错地把材料数量转为显示文本；空值/0 返回 ''（跳过）。

    支持 int / float / str 数字；无法识别的返回 ''。
    """
    if value is None:
        return ''
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ''
        try:
            num = float(text)
        except ValueError:
            return ''
    else:
        try:
            num = float(value)
        except (TypeError, ValueError):
            return ''
    if num == 0:
        return ''
    return str(int(num)) if num == int(num) else str(num)


def meter_voltage(voltage: str) -> str:
    """电表电压型号：'220' → '220'，'380' → '3×220/380'。"""
    if voltage == '380':
        return '3×220/380'
    return '220'


def compose_materials_text(materials: dict) -> str:
    """按 MATERIAL_COLUMNS 顺序拼接施工规格，跳过空值/0，用 '，' 连接。"""
    if not materials:
        return ''
    parts = []
    for key, _header in MATERIAL_COLUMNS:
        n = _format_num(materials.get(key, ''))
        if n:
            parts.append(_MATERIAL_PHRASES[key].format(n=n))
    return '，'.join(parts)


def compose_box_model(meter_current: str, box_phase: str,
                      box_positions: str, box_mount: str) -> str:
    """表箱型号：'{电流}{相别}{表位}{安装方式}表箱'，电流为空时不带前缀。"""
    prefix = meter_current.strip() if isinstance(meter_current, str) else ''
    return f'{prefix}{box_phase}{box_positions}{box_mount}表箱'


def build_field_map(order: dict, supply: dict) -> dict:
    """红字占位文本 → 替换值 的映射。

    键必须精确匹配模板中的红字占位名；'和同容量' 与 '合同容量'
    都映射到合同容量（原模板笔误兼容）。
    """
    line = supply.get('line', '')
    transformer = supply.get('transformer', '')
    return {
        '流程编号': order.get('flow_id', ''),
        '工单类型': order.get('flow_type', ''),
        '户名': order.get('account_name', ''),
        '户号': order.get('account_no', ''),
        '地址': order.get('address', ''),
        '用户电话': order.get('phone', ''),
        '行业分类': supply.get('industry', ''),
        '供电电压': supply.get('voltage', ''),
        '批准容量': supply.get('capacity', ''),
        '线路': line,
        '变压器名称': transformer,
        '和同容量': supply.get('contract_capacity', ''),
        '合同容量': supply.get('contract_capacity', ''),
        '去年负荷': supply.get('last_year_load', ''),
        '接户方式': supply.get('connection', ''),
        '施工规格': compose_materials_text(supply.get('materials', {})),
        '表箱型号': compose_box_model(
            supply.get('meter_current', ''),
            supply.get('box_phase', ''),
            supply.get('box_positions', ''),
            supply.get('box_mount', '')),
        '电表电压型号': meter_voltage(supply.get('voltage', '')),
        '电表电流型号': supply.get('meter_current', ''),
        '电价': supply.get('price', ''),
        '线路 变压器名称': f'{line} {transformer}',
    }


def default_supply(order: dict) -> dict:
    """按工单流程类型给出默认供方数据。

    低压居民（含'居民'且不含'非居民'）默认 220V，其余默认 380V；
    表箱相别跟随电压，materials 全部为空。
    """
    flow_type = order.get('flow_type', '')
    is_resident = '居民' in flow_type and '非居民' not in flow_type
    voltage = '220' if is_resident else '380'
    return {
        'voltage': voltage,
        'capacity': '',
        'line': '',
        'transformer': '',
        'contract_capacity': '',
        'last_year_load': '',
        'connection': '',
        'meter_current': '',
        'price': '',
        'industry': _INDUSTRY_DEFAULTS.get(flow_type, ''),
        'box_phase': '单相' if voltage == '220' else '三相',
        'box_positions': '一表位',
        'box_mount': '悬挂式',
        'materials': {key: '' for key in MATERIAL_KEYS},
    }
