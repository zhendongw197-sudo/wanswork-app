# -*- coding: utf-8 -*-
"""营销工单助手主界面（tkinter + ttk）。

依赖模块：store（数据）、worktime（时限）、export（导出/汇总）、
gen_call / gen_sms（截图）、gen_docs（Word 材料）、
supply / gen_supply（供方单）。
"""

import os
import shutil
import sys
import tkinter as tk
from datetime import date, datetime
from tkinter import filedialog, messagebox, ttk

from . import export, gen_call, gen_docs, gen_sms, gen_supply, store as store_mod
from . import supply, worktime

# 主表格列定义：(字段键, 列标题, 列宽)
COLUMNS = [
    ('flow_id', '流程编号', 150),
    ('flow_type', '流程类型', 100),
    ('account_no', '户号', 140),
    ('account_name', '户名', 140),
    ('manager', '客户经理', 90),
    ('start_time', '流程开始日期', 160),
    ('visit_deadline', '上门服务截止日', 160),
    ('full_deadline', '全流程截止日', 160),
    ('remaining', '剩余时间', 120),
    ('address', '地址', 200),
    ('in_group', '是否建群', 80),
    ('status', '状态', 70),
]

# 模板配置七个键：(配置键, 中文标签)
CONFIG_KEYS = [
    ('gas_company', '燃气公司'),
    ('builder_name', '施工单位'),
    ('builder_leader', '施工负责人'),
    ('builder_phone', '施工电话'),
    ('org_name', '落款单位'),
    ('company_short', '公司简称'),
    ('dig_depth_cm', '开挖深度'),
]

# 状态颜色等级（越小越靠前）
_STATUS_RANK = {'overdue': 0, 'warn': 1, 'normal': 2, 'none': 2}

# 终结状态集合：不再考核任何截止日、剩余时间显示 '-'、无标色、排序沉底
# （'已办结' 为旧数据兼容，视同 '流程办结'）
TERMINAL = {'流程办结', '终止', '已办结'}


def progress_options(flow_type: str) -> list:
    """按流程类型返回进度编辑可选项。

    '上门服务办结' 仅对低压充电桩* / 低压非居民* 出现
    （flow_type 不含'居民'或含'非居民'）；低压居民* 不显示该选项。
    """
    options = ['已建群', '流程办结', '终止']
    if '居民' not in flow_type or '非居民' in flow_type:
        options.insert(1, '上门服务办结')
    return options

_AUTO_REFRESH_MS = 60 * 1000  # 每 60 秒自动刷新

# 台账中文表头 -> record 键（SUPPLY_HEADERS 为纯中文表头时的兜底映射；
# 材料列表头由 supply.MATERIAL_COLUMNS 动态映射）
_SUPPLY_HEADER_TO_KEY = {
    '流程编号': 'flow_id',
    '客户经理': 'manager',
    '是否归档': 'archived',
    '户号': 'account_no',
    '户名': 'account_name',
    '地址': 'address',
    '流程开始日期': 'start_time',
    '流程开始时间': 'start_time',
    '开始时间': 'start_time',
    '方案推送时间': 'push_time',
    '推送时间': 'push_time',
    '流程超期时间': 'overdue_time',
    '超期时间': 'overdue_time',
    '当前进度（营销部反馈）': 'progress_marketing',
    '营销部反馈': 'progress_marketing',
    '设备部进度（是否发料）': 'progress_equipment',
    '设备部进度': 'progress_equipment',
    '备注': 'remark',
    '配套单位': 'contractor',
    '现场勘察方案及工作量': 'work_desc',
    '施工内容': 'work_desc',
    '工作内容': 'work_desc',
}

# 台账列宽（默认 90，范围 90~140）
_SUPPLY_COL_WIDTHS = {
    'flow_id': 140,
    'account_no': 120,
    'account_name': 120,
    'address': 140,
    'start_time': 130,
    'push_time': 130,
    'overdue_time': 130,
    'progress_marketing': 110,
    'progress_equipment': 110,
    'remark': 110,
    'work_desc': 140,
}


def _fmt_dt(dt) -> str:
    """datetime -> 'YYYY-MM-DD HH:MM:SS'；None -> '-'。"""
    if dt is None:
        return '-'
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def _fmt_date_cn(d: date) -> str:
    """date -> '2026年7月7日' 式（月日不补零）。"""
    return f'{d.year}年{d.month}月{d.day}日'


def _parse_date_lines(text: str) -> set:
    """解析文本区里每行一个 YYYY-MM-DD 日期，非法行跳过。"""
    result = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            result.add(date.fromisoformat(line))
        except ValueError:
            continue
    return result


def _asset(name: str) -> str:
    """定位 assets 目录资源（与 gen_call 相同机制，兼容 PyInstaller 打包）。"""
    base = getattr(sys, '_MEIPASS',
                   os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, 'assets', name)


def _base_dir() -> str:
    """软件所在目录：打包时取 exe 所在目录，源码运行时取项目根目录。

    与 main.py 的 BASE_DIR 口径一致：paths.json 存放于此，
    路径配置中的相对路径也基于该目录解析。
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _supply_columns() -> list:
    """把 export.SUPPLY_HEADERS 归一化为 [(数据键, 列标题), ...]。

    兼容两种契约形态：(key, header) 元组列表，或纯中文表头字符串列表
    （字符串按 _SUPPLY_HEADER_TO_KEY 与材料表头映射回数据键，未识别时以
    表头本身作键，取值为空）。
    """
    header_to_mat_key = {header: key for key, header in supply.MATERIAL_COLUMNS}
    columns = []
    for item in export.SUPPLY_HEADERS:
        if isinstance(item, (tuple, list)):
            columns.append((str(item[0]), str(item[1])))
        else:
            title = str(item)
            key = _SUPPLY_HEADER_TO_KEY.get(title) or header_to_mat_key.get(title) or title
            columns.append((key, title))
    return columns


def _supply_cell(record: dict, key: str) -> str:
    """取台账单元格显示值：先查 record 顶层键，再查 materials。"""
    value = record.get(key, None)
    if value is None:
        value = (record.get('materials') or {}).get(key, '')
    return '' if value is None else str(value)


# ---------------------------------------------------------------------------
# 通用弹窗基类
# ---------------------------------------------------------------------------
class _Dialog(tk.Toplevel):
    """模态弹窗基类：居中、抓取焦点、等待关闭。"""

    def __init__(self, parent, title: str, width: int = 460):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result = None
        self.transient(parent.winfo_toplevel())
        self.body = ttk.Frame(self, padding=14)
        self.body.pack(fill='both', expand=True)
        self.update_idletasks()
        # 居中于父窗口
        pw = parent.winfo_toplevel()
        px = pw.winfo_rootx() + max(0, (pw.winfo_width() - width) // 2)
        py = pw.winfo_rooty() + 80
        self.geometry(f'{width}x10+{px}+{py}')
        self.grab_set()
        self.protocol('WM_DELETE_WINDOW', self._on_cancel)

    def _on_ok(self):
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()

    def _add_row(self, r: int, label: str) -> None:
        ttk.Label(self.body, text=label).grid(row=r, column=0, sticky='e', padx=(0, 8), pady=5)

    def show_modal(self):
        """调整高度并进入模态等待，返回 self.result。"""
        self.update_idletasks()
        w = max(self.winfo_reqwidth(), 460)
        h = self.winfo_reqheight()
        x = self.winfo_x()
        y = self.winfo_y()
        self.geometry(f'{w}x{h}+{x}+{y}')
        self.wait_window(self)
        return self.result


# ---------------------------------------------------------------------------
# 新增 / 修改工单弹窗
# ---------------------------------------------------------------------------
class OrderDialog(_Dialog):
    """工单录入弹窗。edit_order 为 None 表示新增，否则为修改（流程编号置灰）。"""

    def __init__(self, parent, store, edit_order: dict | None = None):
        self.store = store
        self.edit_order = edit_order
        super().__init__(parent, '修改工单' if edit_order else '新增工单')

        managers = [m['name'] for m in store.list_managers()]
        flow_types = list(worktime.FLOW_TYPES.keys())

        self.vars = {}
        fields = [
            ('flow_id', '流程编号'),
            ('flow_type', '流程类型'),
            ('account_no', '户号'),
            ('account_name', '户名'),
            ('manager', '客户经理'),
            ('phone', '客户手机号'),
            ('address', '地址'),
            ('start_time', '流程开始日期'),
        ]
        for r, (key, label) in enumerate(fields):
            self._add_row(r, label)
            if key == 'address':
                # 地址支持多行：3 行 Text，自动换行
                self.address_text = tk.Text(self.body, width=40, height=3, wrap='word')
                self.address_text.grid(row=r, column=1, sticky='w', pady=5)
                continue
            var = tk.StringVar()
            self.vars[key] = var
            if key == 'flow_type':
                w = ttk.Combobox(self.body, textvariable=var, values=flow_types,
                                 state='readonly', width=37)
            elif key == 'manager':
                w = ttk.Combobox(self.body, textvariable=var, values=managers,
                                 state='readonly', width=37)
            else:
                w = ttk.Entry(self.body, textvariable=var, width=40)
            w.grid(row=r, column=1, sticky='w', pady=5)
            if key == 'flow_id' and edit_order:
                w.configure(state='disabled')
            if key == 'start_time':
                ttk.Label(self.body, text='格式：YYYY-MM-DD HH:MM:SS',
                          foreground='#888888').grid(row=r, column=2, sticky='w', padx=(8, 0))

        # 初值
        if edit_order:
            for key in self.vars:
                var_value = edit_order.get(key, '')
                self.vars[key].set('' if var_value is None else str(var_value))
            addr_value = edit_order.get('address', '')
            self.address_text.insert('1.0', '' if addr_value is None else str(addr_value))
        else:
            self.vars['flow_type'].set(flow_types[0])
            if managers:
                self.vars['manager'].set(managers[0])
            self.vars['start_time'].set(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

        btns = ttk.Frame(self.body)
        btns.grid(row=len(fields), column=0, columnspan=3, pady=(12, 0))
        ttk.Button(btns, text='确定', command=self._on_ok).pack(side='left', padx=8)
        ttk.Button(btns, text='取消', command=self._on_cancel).pack(side='left', padx=8)

    def _on_ok(self):
        order = {key: var.get().strip() for key, var in self.vars.items()}
        order['address'] = self.address_text.get('1.0', 'end-1c').strip()
        if self.edit_order:
            order['flow_id'] = self.edit_order['flow_id']
            order['status'] = self.edit_order.get('status', '在办')
            order['in_group'] = self.edit_order.get('in_group', '')
            try:
                self.store.update_order(order['flow_id'], order)
            except (ValueError, KeyError) as exc:
                messagebox.showerror('错误', str(exc), parent=self)
                return
        else:
            order['status'] = '在办'
            try:
                self.store.add_order(order)
            except ValueError as exc:
                messagebox.showerror('错误', str(exc), parent=self)
                return
        self.result = order
        self.destroy()


# ---------------------------------------------------------------------------
# 工单进度编辑弹窗
# ---------------------------------------------------------------------------
class ProgressDialog(_Dialog):
    """工单进度编辑：单选 '已建群' / '上门服务办结' / '流程办结' / '终止'。

    '上门服务办结' 仅对低压充电桩* / 低压非居民* 出现（progress_options 控制）。
    result 为选中的状态字符串；取消为 None。
    """

    def __init__(self, parent, order: dict):
        super().__init__(parent, f'进度编辑 - {order["flow_id"]}')
        current = order.get('status', '在办')
        if current == '已办结':  # 旧数据兼容：视同 '流程办结'
            current = '流程办结'
        options = progress_options(order.get('flow_type', ''))

        ttk.Label(self.body,
                  text=f"当前进度：{order.get('status', '在办')}"
                       f"    是否建群：{order.get('in_group', '') or '否'}").grid(
            row=0, column=0, columnspan=2, sticky='w', pady=(0, 8))

        self.choice = tk.StringVar(value=current if current in options else options[0])
        for r, text in enumerate(options, start=1):
            ttk.Radiobutton(self.body, text=text, value=text,
                            variable=self.choice).grid(
                row=r, column=0, columnspan=2, sticky='w', pady=3)

        btns = ttk.Frame(self.body)
        btns.grid(row=len(options) + 1, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btns, text='保存', command=self._on_ok).pack(side='left', padx=8)
        ttk.Button(btns, text='取消', command=self._on_cancel).pack(side='left', padx=8)

    def _on_ok(self):
        self.result = self.choice.get()
        self.destroy()


# ---------------------------------------------------------------------------
# 生成终止材料弹窗
# ---------------------------------------------------------------------------
class TerminationDialog(_Dialog):
    def __init__(self, parent, order: dict):
        super().__init__(parent, f'生成终止材料 - {order["flow_id"]}')
        self.vars = {}
        fields = [
            ('phone', '客户手机号', order.get('phone', '')),
            ('address', '地址', order.get('address', '')),
            ('reason', '终止原因', ''),
            ('duration', '通话时长（秒）', '10'),
            ('battery', '电量（%）', '79'),
        ]
        for r, (key, label, default) in enumerate(fields):
            self._add_row(r, label)
            var = tk.StringVar(value=str(default))
            self.vars[key] = var
            ttk.Entry(self.body, textvariable=var, width=40).grid(
                row=r, column=1, sticky='w', pady=5)
        btns = ttk.Frame(self.body)
        btns.grid(row=len(fields), column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btns, text='生成', command=self._on_ok).pack(side='left', padx=8)
        ttk.Button(btns, text='取消', command=self._on_cancel).pack(side='left', padx=8)

    def _on_ok(self):
        self.result = {key: var.get().strip() for key, var in self.vars.items()}
        self.destroy()


# ---------------------------------------------------------------------------
# 生成四方交底材料弹窗
# ---------------------------------------------------------------------------
class JiaodiDialog(_Dialog):
    def __init__(self, parent, order: dict, store):
        super().__init__(parent, f'生成四方交底材料 - {order["flow_id"]}', width=500)
        today = _fmt_date_cn(date.today())
        managers = [m['name'] for m in store.list_managers()]
        self.vars = {}
        fields = [
            ('phone', '客户手机号', order.get('phone', '')),
            ('address', '地址', order.get('address', '')),
            ('street', '街道', ''),
            ('distance_m', '开挖距离（米）', ''),
            ('jiaodi_date', '交底日期', today),
        ]
        r = 0
        for key, label, default in fields:
            self._add_row(r, label)
            var = tk.StringVar(value=str(default))
            self.vars[key] = var
            ttk.Entry(self.body, textvariable=var, width=40).grid(
                row=r, column=1, sticky='w', pady=5)
            if key == 'jiaodi_date':
                ttk.Label(self.body, text='格式：YYYY年M月D日',
                          foreground='#888888').grid(row=r, column=2, sticky='w', padx=(8, 0))
            r += 1
        self._add_row(r, '客户经理')
        var = tk.StringVar(value=order.get('manager', ''))
        self.vars['manager'] = var
        ttk.Combobox(self.body, textvariable=var, values=managers,
                     state='readonly', width=37).grid(row=r, column=1, sticky='w', pady=5)
        r += 1
        btns = ttk.Frame(self.body)
        btns.grid(row=r, column=0, columnspan=3, pady=(12, 0))
        ttk.Button(btns, text='生成', command=self._on_ok).pack(side='left', padx=8)
        ttk.Button(btns, text='取消', command=self._on_cancel).pack(side='left', padx=8)

    def _on_ok(self):
        self.result = {key: var.get().strip() for key, var in self.vars.items()}
        self.destroy()


# ---------------------------------------------------------------------------
# 供方单录入弹窗
# ---------------------------------------------------------------------------
class SupplyDialog(_Dialog):
    """供方单录入弹窗：基本信息 + 表箱 + 材料明细（17 项）。

    result 形如 {'supply': {...}, 'phone': str, 'address': str}；
    supply 键与共享契约一致，materials 值 strip 后保留字符串（空为 ''）。
    """

    # 基本信息区字段：(字段键, 中文标签)
    _BASIC_FIELDS = [
        ('voltage', '供电电压'),
        ('capacity', '批准容量'),
        ('line', '线路'),
        ('transformer', '变压器名称'),
        ('contract_capacity', '合同容量'),
        ('last_year_load', '去年负荷'),
        ('connection', '接户方式'),
        ('meter_current', '电表电流型号'),
        ('price', '电价'),
        ('industry', '行业分类'),
        ('phone', '客户手机号'),
        ('address', '地址'),
    ]

    def __init__(self, parent, order: dict):
        super().__init__(parent, f'生成供方单 - {order["flow_id"]}', width=720)
        defaults = supply.default_supply(order)
        self.vars = {}
        self.mat_vars = {}
        self._build_basic(order, defaults)
        self._build_box(defaults)
        self._build_materials(defaults)
        btns = ttk.Frame(self.body)
        btns.pack(pady=(12, 0))
        ttk.Button(btns, text='确定', command=self._on_ok).pack(side='left', padx=8)
        ttk.Button(btns, text='取消', command=self._on_cancel).pack(side='left', padx=8)

    def _build_basic(self, order: dict, defaults: dict):
        frame = ttk.LabelFrame(self.body, text='基本信息', padding=8)
        frame.pack(fill='x', pady=(0, 8))
        for i, (key, label) in enumerate(self._BASIC_FIELDS):
            r, c = divmod(i, 2)
            ttk.Label(frame, text=label).grid(row=r, column=c * 2, sticky='e',
                                              padx=(0, 6), pady=4)
            if key == 'phone':
                default = order.get('phone', '')
            elif key == 'address':
                default = order.get('address', '')
            else:
                default = defaults.get(key, '')
            var = tk.StringVar(value='' if default is None else str(default))
            self.vars[key] = var
            if key == 'voltage':
                w = ttk.Combobox(frame, textvariable=var, values=['220', '380'],
                                 state='readonly', width=18)
            else:
                # 行业分类等其余字段均为手填 Entry
                w = ttk.Entry(frame, textvariable=var, width=20)
            w.grid(row=r, column=c * 2 + 1, sticky='w', padx=(0, 16), pady=4)

    def _build_box(self, defaults: dict):
        frame = ttk.LabelFrame(self.body, text='表箱', padding=8)
        frame.pack(fill='x', pady=(0, 8))
        box_fields = [
            ('box_phase', '单相/三相', supply.BOX_PHASES),
            ('box_positions', '表位', supply.BOX_POSITIONS),
            ('box_mount', '悬挂式/落地式', supply.BOX_MOUNTS),
        ]
        for c, (key, label, values) in enumerate(box_fields):
            ttk.Label(frame, text=label).grid(row=0, column=c * 2, sticky='e',
                                              padx=(0, 6), pady=4)
            default = defaults.get(key, '')
            var = tk.StringVar(value='' if default is None else str(default))
            self.vars[key] = var
            ttk.Combobox(frame, textvariable=var, values=values,
                         state='readonly', width=14).grid(
                row=0, column=c * 2 + 1, sticky='w', padx=(0, 16), pady=4)

    def _build_materials(self, defaults: dict):
        frame = ttk.LabelFrame(self.body, text='材料明细（无则留空）', padding=8)
        frame.pack(fill='x')
        mat_defaults = defaults.get('materials') or {}
        for i, (key, header) in enumerate(supply.MATERIAL_COLUMNS):
            r, c = divmod(i, 3)
            ttk.Label(frame, text=header).grid(row=r, column=c * 2, sticky='e',
                                               padx=(0, 6), pady=3)
            default = mat_defaults.get(key, '')
            var = tk.StringVar(value='' if default is None else str(default))
            self.mat_vars[key] = var
            ttk.Entry(frame, textvariable=var, width=8).grid(
                row=r, column=c * 2 + 1, sticky='w', padx=(0, 12), pady=3)

    def _on_ok(self):
        data = {key: var.get().strip() for key, var in self.vars.items()}
        phone = data.pop('phone')
        address = data.pop('address')
        data['materials'] = {key: var.get().strip()
                             for key, var in self.mat_vars.items()}
        self.result = {'supply': data, 'phone': phone, 'address': address}
        self.destroy()


# ---------------------------------------------------------------------------
# 设置窗口
# ---------------------------------------------------------------------------
class SettingsWindow(tk.Toplevel):
    """设置：客户经理 / 节假日与调休 / 模板配置 / 路径配置 四个页签。

    current_paths 为当前生效的 {'data_dir', 'output_dir'}（绝对路径），
    由主窗口传入；路径保存成功后回调 on_paths_saved(data_dir, output_dir)。
    """

    def __init__(self, parent, store, on_saved=None,
                 current_paths: dict | None = None, on_paths_saved=None):
        super().__init__(parent)
        self.store = store
        self.on_saved = on_saved
        # 当前生效的数据/输出绝对路径；缺省按 store 推导数据路径
        self.current_paths = dict(current_paths or {})
        self.current_paths.setdefault('data_dir', getattr(store, 'data_dir', ''))
        self.current_paths.setdefault('output_dir', '')
        self.on_paths_saved = on_paths_saved
        self.title('设置')
        self.geometry('680x480')
        self.transient(parent.winfo_toplevel())

        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=8, pady=8)
        self._build_managers_tab(nb)
        self._build_calendar_tab(nb)
        self._build_config_tab(nb)
        self._build_paths_tab(nb)

    # ----- 页签1：客户经理 -----
    def _build_managers_tab(self, nb):
        frame = ttk.Frame(nb, padding=10)
        nb.add(frame, text='客户经理')

        self.mgr_list = tk.Listbox(frame, height=12)
        self.mgr_list.pack(side='left', fill='both', expand=True)
        sb = ttk.Scrollbar(frame, orient='vertical', command=self.mgr_list.yview)
        sb.pack(side='left', fill='y')
        self.mgr_list.configure(yscrollcommand=sb.set)
        self.mgr_list.bind('<<ListboxSelect>>', self._on_mgr_select)

        right = ttk.Frame(frame, padding=(12, 0))
        right.pack(side='left', fill='y')
        ttk.Label(right, text='姓名').grid(row=0, column=0, sticky='e', pady=4)
        self.mgr_name = tk.StringVar()
        ttk.Entry(right, textvariable=self.mgr_name, width=22).grid(row=0, column=1, pady=4)
        ttk.Label(right, text='手机号').grid(row=1, column=0, sticky='e', pady=4)
        self.mgr_phone = tk.StringVar()
        ttk.Entry(right, textvariable=self.mgr_phone, width=22).grid(row=1, column=1, pady=4)
        ttk.Button(right, text='新增', command=self._mgr_add).grid(
            row=2, column=0, columnspan=2, sticky='ew', pady=(10, 2))
        ttk.Button(right, text='修改', command=self._mgr_update).grid(
            row=3, column=0, columnspan=2, sticky='ew', pady=2)
        ttk.Button(right, text='删除', command=self._mgr_delete).grid(
            row=4, column=0, columnspan=2, sticky='ew', pady=2)

        self._reload_managers()

    def _reload_managers(self):
        self.mgr_list.delete(0, 'end')
        for m in self.store.list_managers():
            self.mgr_list.insert('end', f"{m['name']}    {m['phone']}")

    def _selected_mgr_name(self):
        sel = self.mgr_list.curselection()
        if not sel:
            return None
        return self.mgr_list.get(sel[0]).split()[0]

    def _on_mgr_select(self, _event=None):
        name = self._selected_mgr_name()
        if name:
            self.mgr_name.set(name)
            self.mgr_phone.set(self.store.get_manager_phone(name))

    def _mgr_add(self):
        name = self.mgr_name.get().strip()
        if not name:
            messagebox.showwarning('提示', '请输入姓名', parent=self)
            return
        try:
            self.store.add_manager(name, self.mgr_phone.get().strip())
        except ValueError as exc:
            messagebox.showerror('错误', str(exc), parent=self)
            return
        self._reload_managers()
        self._notify_saved()

    def _mgr_update(self):
        name = self.mgr_name.get().strip()
        if not name:
            messagebox.showwarning('提示', '请输入姓名', parent=self)
            return
        self.store.update_manager(name, self.mgr_phone.get().strip())
        self._reload_managers()
        self._notify_saved()

    def _mgr_delete(self):
        name = self._selected_mgr_name()
        if not name:
            messagebox.showwarning('提示', '请先在列表中选择要删除的客户经理', parent=self)
            return
        if not messagebox.askyesno('确认删除', f'确定删除客户经理「{name}」吗？', parent=self):
            return
        self.store.delete_manager(name)
        self.mgr_name.set('')
        self.mgr_phone.set('')
        self._reload_managers()
        self._notify_saved()

    # ----- 页签2：节假日与调休 -----
    def _build_calendar_tab(self, nb):
        frame = ttk.Frame(nb, padding=10)
        nb.add(frame, text='节假日与调休')

        ttk.Label(frame, text='节假日每行一个日期；调休上班日（周末上班）填右侧').pack(
            anchor='w', pady=(0, 6))

        areas = ttk.Frame(frame)
        areas.pack(fill='both', expand=True)
        left = ttk.Frame(areas)
        left.pack(side='left', fill='both', expand=True, padx=(0, 6))
        ttk.Label(left, text='节假日（YYYY-MM-DD，每行一个）').pack(anchor='w')
        self.holiday_text = tk.Text(left, width=26, height=16)
        self.holiday_text.pack(fill='both', expand=True)

        right = ttk.Frame(areas)
        right.pack(side='left', fill='both', expand=True, padx=(6, 0))
        ttk.Label(right, text='调休上班日（YYYY-MM-DD，每行一个）').pack(anchor='w')
        self.extra_text = tk.Text(right, width=26, height=16)
        self.extra_text.pack(fill='both', expand=True)

        for d in sorted(self.store.get_holidays()):
            self.holiday_text.insert('end', d.isoformat() + '\n')
        for d in sorted(self.store.get_extra_workdays()):
            self.extra_text.insert('end', d.isoformat() + '\n')

        ttk.Button(frame, text='保存', command=self._save_calendar).pack(pady=(8, 0))

    def _save_calendar(self):
        holidays = _parse_date_lines(self.holiday_text.get('1.0', 'end'))
        extra = _parse_date_lines(self.extra_text.get('1.0', 'end'))
        self.store.set_holidays(holidays)
        self.store.set_extra_workdays(extra)
        messagebox.showinfo('提示', '节假日与调休已保存', parent=self)
        self._notify_saved()

    # ----- 页签3：模板配置 -----
    def _build_config_tab(self, nb):
        frame = ttk.Frame(nb, padding=10)
        nb.add(frame, text='模板配置')

        self.config_vars = {}
        for r, (key, label) in enumerate(CONFIG_KEYS):
            ttk.Label(frame, text=label).grid(row=r, column=0, sticky='e', padx=(0, 8), pady=6)
            var = tk.StringVar(value=str(self.store.get_config(key, '')))
            self.config_vars[key] = var
            ttk.Entry(frame, textvariable=var, width=48).grid(row=r, column=1, sticky='w', pady=6)

        ttk.Button(frame, text='保存', command=self._save_config).grid(
            row=len(CONFIG_KEYS), column=0, columnspan=2, pady=(14, 0))

    def _save_config(self):
        for key, var in self.config_vars.items():
            self.store.set_config(key, var.get().strip())
        messagebox.showinfo('提示', '模板配置已保存', parent=self)
        self._notify_saved()

    # ----- 页签4：路径配置 -----
    def _build_paths_tab(self, nb):
        frame = ttk.Frame(nb, padding=10)
        nb.add(frame, text='路径配置')

        self.path_vars = {}
        rows = [
            ('data_dir', '数据路径（store.json 所在目录）'),
            ('output_dir', '输出路径（生成材料保存目录）'),
        ]
        for r, (key, label) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=r, column=0, sticky='e',
                                              padx=(0, 8), pady=6)
            var = tk.StringVar(value=self.current_paths.get(key, ''))
            self.path_vars[key] = var
            ttk.Entry(frame, textvariable=var, width=46).grid(
                row=r, column=1, sticky='w', pady=6)
            ttk.Button(frame, text='浏览…',
                       command=lambda k=key: self._browse_path(k)).grid(
                row=r, column=2, sticky='w', padx=(8, 0), pady=6)

        ttk.Label(frame,
                  text='支持服务器共享路径，如 \\\\服务器\\共享\\工单数据；'
                       '相对路径基于软件所在目录。',
                  foreground='#888888', wraplength=600, justify='left').grid(
            row=len(rows), column=0, columnspan=3, sticky='w', pady=(4, 0))

        ttk.Button(frame, text='保存', command=self._save_paths).grid(
            row=len(rows) + 1, column=0, columnspan=3, pady=(14, 0))

    def _browse_path(self, key: str):
        """弹目录选择框，选中后写入对应 Entry。"""
        current = self.path_vars[key].get().strip()
        initial = current if current and os.path.isdir(current) else _base_dir()
        path = filedialog.askdirectory(parent=self, title='选择目录',
                                       initialdir=initial)
        if path:
            self.path_vars[key].set(path)

    def _save_paths(self):
        """保存路径配置：非空校验→目录确认/创建→可选迁移数据→写 paths.json→回调。"""
        from . import paths as paths_mod  # 延迟导入：paths 模块由并行开发提供

        base_dir = _base_dir()
        raw_data = self.path_vars['data_dir'].get().strip()
        raw_output = self.path_vars['output_dir'].get().strip()
        if not raw_data or not raw_output:
            messagebox.showwarning('提示', '数据路径与输出路径均不能为空', parent=self)
            return
        data_dir = paths_mod.resolve(base_dir, raw_data)
        output_dir = paths_mod.resolve(base_dir, raw_output)

        # 目录不存在时询问是否创建
        for label, path in (('数据路径', data_dir), ('输出路径', output_dir)):
            if not os.path.isdir(path):
                if not messagebox.askyesno(
                        '目录不存在',
                        f'{label}目录不存在：\n{path}\n\n是否创建？', parent=self):
                    return
                try:
                    os.makedirs(path, exist_ok=True)
                except OSError as exc:
                    messagebox.showerror('错误', f'创建目录失败：\n{exc}', parent=self)
                    return

        # 数据路径变更且新目录下无 store.json：询问是否迁移现有数据
        old_data_dir = self.current_paths.get('data_dir', '')
        data_changed = (old_data_dir
                        and os.path.normcase(os.path.abspath(data_dir))
                        != os.path.normcase(os.path.abspath(old_data_dir)))
        if data_changed and not os.path.exists(os.path.join(data_dir, 'store.json')):
            old_store = os.path.join(old_data_dir, 'store.json')
            if os.path.exists(old_store) and messagebox.askyesno(
                    '数据迁移',
                    '新数据路径下没有 store.json。\n是否把现有数据复制到新路径？',
                    parent=self):
                try:
                    shutil.copy2(old_store, os.path.join(data_dir, 'store.json'))
                except OSError as exc:
                    messagebox.showerror('错误', f'复制数据失败：\n{exc}', parent=self)
                    return

        try:
            paths_mod.save_paths(base_dir, data_dir, output_dir)
        except OSError as exc:
            messagebox.showerror('错误', f'写入 paths.json 失败：\n{exc}', parent=self)
            return
        self.current_paths = {'data_dir': data_dir, 'output_dir': output_dir}
        if callable(self.on_paths_saved):
            try:
                self.on_paths_saved(data_dir, output_dir)
            except Exception as exc:
                messagebox.showerror('错误', f'应用新路径时出错：\n{exc}', parent=self)
        else:
            messagebox.showinfo('提示', '路径配置已保存', parent=self)

    def _notify_saved(self):
        if callable(self.on_saved):
            self.on_saved()


# ---------------------------------------------------------------------------
# 供方单进度编辑弹窗
# ---------------------------------------------------------------------------
class SupplyProgressDialog(_Dialog):
    """编辑供方单台账 5 个手工字段。result 为 {字段键: 值}。"""

    _FIELDS = [
        ('archived', '是否归档'),
        ('progress_marketing', '当前进度（营销部反馈）'),
        ('progress_equipment', '设备部进度（是否发料）'),
        ('remark', '备注'),
        ('contractor', '配套单位'),
    ]

    def __init__(self, parent, record: dict):
        super().__init__(parent, f'编辑进度 - {record["flow_id"]}')
        self.vars = {}
        for r, (key, label) in enumerate(self._FIELDS):
            self._add_row(r, label)
            value = record.get(key, '')
            var = tk.StringVar(value='' if value is None else str(value))
            self.vars[key] = var
            if key == 'archived':
                w = ttk.Combobox(self.body, textvariable=var,
                                 values=['是', '否', '终止'], state='readonly',
                                 width=37)
            else:
                w = ttk.Entry(self.body, textvariable=var, width=40)
            w.grid(row=r, column=1, sticky='w', pady=5)
        btns = ttk.Frame(self.body)
        btns.grid(row=len(self._FIELDS), column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btns, text='保存', command=self._on_ok).pack(side='left', padx=8)
        ttk.Button(btns, text='取消', command=self._on_cancel).pack(side='left', padx=8)

    def _on_ok(self):
        self.result = {key: var.get().strip() for key, var in self.vars.items()}
        self.destroy()


# ---------------------------------------------------------------------------
# 供方单台账窗口
# ---------------------------------------------------------------------------
class SupplyListWindow(tk.Toplevel):
    """供方单台账：查看 / 编辑进度 / 删除 / 导出 Excel。"""

    def __init__(self, parent, store):
        super().__init__(parent)
        self.store = store
        self.title('已推送供方单')
        self.geometry('1500x600')
        self.columns = _supply_columns()
        self._build_toolbar()
        self._build_table()
        self.refresh()

    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        bar.pack(side='top', fill='x')
        buttons = [
            ('刷新', self.refresh),
            ('编辑进度', self.edit_progress),
            ('删除', self.delete_record),
            ('导出Excel', self.export_excel),
            ('关闭', self.destroy),
        ]
        for text, cmd in buttons:
            ttk.Button(bar, text=text, command=cmd).pack(side='left', padx=3)

    def _build_table(self):
        wrap = ttk.Frame(self, padding=(8, 0, 8, 8))
        wrap.pack(side='top', fill='both', expand=True)

        col_ids = [key for key, _header in self.columns]
        self.tree = ttk.Treeview(wrap, columns=col_ids, show='headings')
        for key, header in self.columns:
            self.tree.heading(key, text=header)
            width = _SUPPLY_COL_WIDTHS.get(key, 90)
            self.tree.column(key, width=width, anchor='center', stretch=False)

        vsb = ttk.Scrollbar(wrap, orient='vertical', command=self.tree.yview)
        hsb = ttk.Scrollbar(wrap, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        self.tree.bind('<Double-1>', lambda _e: self.edit_progress())

    def refresh(self):
        """重载台账数据。"""
        self.tree.delete(*self.tree.get_children())
        for record in self.store.list_supply_orders():
            self.tree.insert('', 'end', iid=record['flow_id'],
                             values=[_supply_cell(record, key)
                                     for key, _header in self.columns])

    def _selected_flow_id(self, action: str):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning('提示', f'请先在表格中选中一行再{action}', parent=self)
            return None
        return sel[0]

    def edit_progress(self):
        flow_id = self._selected_flow_id('编辑进度')
        if not flow_id:
            return
        record = self.store.get_supply_order(flow_id)
        if not record:
            messagebox.showerror('错误', f'供方单不存在：{flow_id}', parent=self)
            return
        dlg = SupplyProgressDialog(self, record)
        vals = dlg.show_modal()
        if not vals:
            return
        record.update(vals)
        try:
            self.store.update_supply_order(flow_id, record)
        except (ValueError, KeyError) as exc:
            messagebox.showerror('错误', str(exc), parent=self)
            return
        self.refresh()

    def delete_record(self):
        flow_id = self._selected_flow_id('删除')
        if not flow_id:
            return
        if not messagebox.askyesno('确认删除', f'确定删除供方单「{flow_id}」吗？',
                                   parent=self):
            return
        self.store.delete_supply_order(flow_id)
        self.refresh()

    def export_excel(self):
        records = self.store.list_supply_orders()
        if not records:
            messagebox.showwarning('提示', '当前没有供方单可导出', parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self, title='导出Excel', defaultextension='.xlsx',
            initialfile='供方单台账.xlsx',
            filetypes=[('Excel 文件', '*.xlsx')])
        if not path:
            return
        try:
            export.export_supply_orders(path, records)
        except Exception as exc:
            messagebox.showerror('导出失败', f'导出 Excel 时出错：\n{exc}', parent=self)
            return
        messagebox.showinfo('完成', f'已导出：\n{path}', parent=self)


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------
class MainWindow:
    """营销工单助手主窗口。"""

    def __init__(self, root: tk.Tk, store, output_dir: str):
        self.root = root
        self.store = store
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self._settings_window = None  # 当前打开的设置窗口（用于路径热切换时同步）

        root.title('营销工单助手')
        root.geometry('1280x720')

        self._build_toolbar()
        self._build_table()
        self.refresh()

        # 每 60 秒自动刷新剩余时间与标色
        self.root.after(_AUTO_REFRESH_MS, self._auto_refresh)

    # ----- 界面搭建 -----
    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        bar.pack(side='top', fill='x')
        buttons = [
            ('新增工单', self.add_order),
            ('修改', self.edit_order),
            ('删除', self.delete_order),
            ('进度编辑', self.edit_progress),
            ('生成终止材料', self.gen_termination),
            ('生成四方交底材料', self.gen_jiaodi),
            ('生成供方单', self.gen_supply),
            ('供方单台账', self.open_supply_window),
            ('导出Excel', self.export_excel),
            ('汇总', self.show_summary),
            ('设置', self.open_settings),
            ('刷新', self.refresh),
        ]
        for text, cmd in buttons:
            ttk.Button(bar, text=text, command=cmd).pack(side='left', padx=3)

    def _build_table(self):
        wrap = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        wrap.pack(side='top', fill='both', expand=True)

        col_ids = [c[0] for c in COLUMNS]
        self.tree = ttk.Treeview(wrap, columns=col_ids, show='headings')
        for key, title, width in COLUMNS:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width,
                             anchor=('w' if key == 'address' else 'center'),
                             stretch=(key in ('address',)))
        # 标色 tag
        self.tree.tag_configure('overdue', background='#F4CCCC')  # 红色背景
        self.tree.tag_configure('warn', background='#FFF2CC')    # 黄色背景

        vsb = ttk.Scrollbar(wrap, orient='vertical', command=self.tree.yview)
        hsb = ttk.Scrollbar(wrap, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        self.tree.bind('<Double-1>', lambda _e: self.edit_order())

    # ----- 数据计算 -----
    def _compute_rows(self) -> list:
        """把 store 工单 + worktime 实时计算结果组装成表格行，并按紧急程度排序。

        考核规则（共享契约）：
        - 终结状态（流程办结/终止/已办结）不再考核，剩余时间 '-'、无标色、沉底；
        - '上门服务办结' 只考核全流程截止日（忽略上门服务截止日）；
        - 其余状态（在办/已建群）维持双截止日考核。
        """
        holidays = self.store.get_holidays()
        extra = self.store.get_extra_workdays()
        now = datetime.now()
        rows = []
        for order in self.store.list_orders():
            row = dict(order)
            visit_dl = full_dl = None
            status = 'none'
            remain_seconds = float('inf')
            order_status = order.get('status', '')
            try:
                start = datetime.strptime(order.get('start_time', ''), '%Y-%m-%d %H:%M:%S')
                visit_dl, full_dl = worktime.compute_deadlines(
                    order.get('flow_type', ''), start, holidays, extra)
                if order_status not in TERMINAL:
                    if order_status == '上门服务办结':
                        # 只考核全流程截止日，上门服务截止日不参与颜色/剩余时间
                        deltas = [full_dl] if full_dl is not None else []
                    else:
                        deltas = [d for d in (visit_dl, full_dl) if d is not None]
                    colors = [worktime.status_color(now, d, holidays, extra)
                              for d in deltas]
                    status = 'overdue' if 'overdue' in colors else (
                        'warn' if 'warn' in colors else 'normal')
                    if deltas:
                        remain_seconds = min((d - now).total_seconds() for d in deltas)
            except (ValueError, KeyError):
                # 开始时间或流程类型异常：按无时限处理
                pass
            row['visit_deadline'] = _fmt_dt(visit_dl)
            row['full_deadline'] = _fmt_dt(full_dl)
            if order_status in TERMINAL:
                row['remaining'] = '-'
            elif order_status == '上门服务办结':
                row['remaining'] = worktime.remaining_text(now, full_dl)
            else:
                # 剩余时间取更早的截止日
                earlier = None
                for d in (visit_dl, full_dl):
                    if d is not None and (earlier is None or d < earlier):
                        earlier = d
                row['remaining'] = worktime.remaining_text(now, earlier)
            row['_status'] = status
            row['_remain_seconds'] = remain_seconds
            row['in_group'] = order.get('in_group', '')  # 缺省归一为空串
            rows.append(row)

        def sort_key(r):
            if r.get('status') in TERMINAL:
                return (1, 0, 0)
            return (0, _STATUS_RANK.get(r['_status'], 2), r['_remain_seconds'])

        rows.sort(key=sort_key)
        return rows

    def refresh(self):
        """重载表格数据并重新标色。"""
        self.tree.delete(*self.tree.get_children())
        for row in self._compute_rows():
            tags = ()
            if row.get('status') not in TERMINAL:
                if row['_status'] == 'overdue':
                    tags = ('overdue',)
                elif row['_status'] == 'warn':
                    tags = ('warn',)
            self.tree.insert('', 'end', iid=row['flow_id'],
                             values=[row.get(c[0], '') for c in COLUMNS], tags=tags)

    def _auto_refresh(self):
        self.refresh()
        self.root.after(_AUTO_REFRESH_MS, self._auto_refresh)

    # ----- 工单操作 -----
    def _selected_flow_id(self, action: str):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning('提示', f'请先在表格中选中一行工单再{action}', parent=self.root)
            return None
        return sel[0]

    def add_order(self):
        dlg = OrderDialog(self.root, self.store)
        if dlg.show_modal():
            self.refresh()

    def edit_order(self):
        flow_id = self._selected_flow_id('修改')
        if not flow_id:
            return
        order = self.store.get_order(flow_id)
        if not order:
            messagebox.showerror('错误', f'工单不存在：{flow_id}', parent=self.root)
            return
        dlg = OrderDialog(self.root, self.store, edit_order=order)
        if dlg.show_modal():
            self.refresh()

    def delete_order(self):
        flow_id = self._selected_flow_id('删除')
        if not flow_id:
            return
        if not messagebox.askyesno('确认删除', f'确定删除工单「{flow_id}」吗？', parent=self.root):
            return
        self.store.delete_order(flow_id)
        self.refresh()

    def edit_progress(self):
        """进度编辑：四选一更新 status 与 in_group 并落盘。"""
        flow_id = self._selected_flow_id('进度编辑')
        if not flow_id:
            return
        order = self.store.get_order(flow_id)
        if not order:
            messagebox.showerror('错误', f'工单不存在：{flow_id}', parent=self.root)
            return
        dlg = ProgressDialog(self.root, order)
        choice = dlg.show_modal()
        if not choice:
            return
        order['status'] = choice
        if choice != '终止':
            # '已建群' / '上门服务办结' / '流程办结' 均视为已建群；'终止' 保留原值
            order['in_group'] = '是'
        try:
            self.store.update_order(flow_id, order)
        except (ValueError, KeyError) as exc:
            messagebox.showerror('错误', str(exc), parent=self.root)
            return
        self.refresh()

    # ----- 材料生成 -----
    def _full_order(self, flow_id: str) -> dict | None:
        """取工单并补齐 manager_phone 键。"""
        order = self.store.get_order(flow_id)
        if not order:
            return None
        order['manager_phone'] = self.store.get_manager_phone(order.get('manager', ''))
        return order

    def gen_termination(self):
        flow_id = self._selected_flow_id('生成终止材料')
        if not flow_id:
            return
        order = self._full_order(flow_id)
        if not order:
            return
        dlg = TerminationDialog(self.root, order)
        vals = dlg.show_modal()
        if not vals:
            return
        out_dir = os.path.join(self.output_dir, f'终止材料_{flow_id}')
        os.makedirs(out_dir, exist_ok=True)
        try:
            duration = int(vals['duration'] or 10)
            battery = int(vals['battery'] or 79)
            apply_date = _fmt_date_cn(
                datetime.strptime(order['start_time'], '%Y-%m-%d %H:%M:%S').date())
            gen_call.gen_call_screenshot(
                vals['phone'], os.path.join(out_dir, '材料1-通话记录截图.png'),
                duration_sec=duration, battery=battery)
            # 短信截图中的公司简称取自模板配置（不改 gen_sms 接口签名，运行时覆盖常量）
            company_short = self.store.get_config('company_short', '')
            if company_short:
                gen_sms.COMPANY = company_short
            gen_sms.gen_sms_screenshot(
                customer_name=order.get('account_name', ''),
                manager_name=order.get('manager', ''),
                apply_date=apply_date,
                address=vals['address'],
                flow_type=order.get('flow_type', ''),
                flow_id=flow_id,
                reason=vals['reason'],
                manager_phone=order['manager_phone'],
                out_path=os.path.join(out_dir, '材料2-短信确认截图.png'),
                battery=battery, customer_phone=vals['phone'])
            doc_order = dict(order, phone=vals['phone'], address=vals['address'])
            gen_docs.gen_termination_note(
                doc_order, vals['reason'],
                os.path.join(out_dir, '材料4-终止白名单情况说明.docx'))
        except Exception as exc:
            messagebox.showerror('生成失败', f'生成终止材料时出错：\n{exc}', parent=self.root)
            return
        # 手机号 / 地址回写到工单
        order['phone'] = vals['phone']
        order['address'] = vals['address']
        order.pop('manager_phone', None)
        self.store.update_order(flow_id, order)
        self.refresh()
        messagebox.showinfo('完成', f'终止材料已生成，保存目录：\n{out_dir}', parent=self.root)

    def gen_jiaodi(self):
        flow_id = self._selected_flow_id('生成四方交底材料')
        if not flow_id:
            return
        order = self._full_order(flow_id)
        if not order:
            return
        dlg = JiaodiDialog(self.root, order, self.store)
        vals = dlg.show_modal()
        if not vals:
            return
        out_dir = os.path.join(self.output_dir, f'四方交底_{flow_id}')
        os.makedirs(out_dir, exist_ok=True)
        config = {key: self.store.get_config(key, '') for key, _label in CONFIG_KEYS}
        # 开挖深度转为数字（模板里做厘米展示）
        try:
            config['dig_depth_cm'] = int(config['dig_depth_cm'])
        except (TypeError, ValueError):
            pass
        try:
            doc_order = dict(order, phone=vals['phone'], address=vals['address'],
                             manager=vals['manager'])
            doc_order['manager_phone'] = self.store.get_manager_phone(vals['manager'])
            gen_docs.gen_jiaodi_apply(
                doc_order, vals['street'], vals['distance_m'], vals['jiaodi_date'],
                os.path.join(out_dir, '交底申请书.docx'), config)
            gen_docs.gen_construct_plan(
                doc_order, vals['distance_m'],
                os.path.join(out_dir, '施工方案.docx'), config)
            gen_docs.gen_supervision_note(
                doc_order, os.path.join(out_dir, '监理情况说明.docx'))
        except Exception as exc:
            messagebox.showerror('生成失败', f'生成四方交底材料时出错：\n{exc}', parent=self.root)
            return
        messagebox.showinfo('完成', f'四方交底材料已生成，保存目录：\n{out_dir}', parent=self.root)

    def gen_supply(self):
        flow_id = self._selected_flow_id('生成供方单')
        if not flow_id:
            return
        order = self._full_order(flow_id)
        if not order:
            return
        dlg = SupplyDialog(self.root, order)
        vals = dlg.show_modal()
        if not vals:
            return
        supply_data = vals['supply']
        out_dir = os.path.join(self.output_dir, f'供方单_{flow_id}')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, '供电方案确认单.docx')
        try:
            unmatched = gen_supply.gen_supply_form(
                order, supply_data, _asset('供电方案确认单.docx'), out_path)
        except Exception as exc:
            messagebox.showerror('生成失败', f'生成供方单时出错：\n{exc}', parent=self.root)
            return
        # 全流程截止日作为台账超期时间（异常则为空）
        overdue_time = ''
        try:
            start = datetime.strptime(order.get('start_time', ''), '%Y-%m-%d %H:%M:%S')
            _visit_dl, full_dl = worktime.compute_deadlines(
                order.get('flow_type', ''), start,
                self.store.get_holidays(), self.store.get_extra_workdays())
            if full_dl is not None:
                overdue_time = full_dl.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, KeyError):
            overdue_time = ''
        # 台账记录：手工字段留空，supply / materials 存快照
        record = {
            'flow_id': flow_id,
            'manager': order.get('manager', ''),
            'archived': '',
            'account_no': order.get('account_no', ''),
            'account_name': order.get('account_name', ''),
            'address': vals['address'],
            'start_time': order.get('start_time', ''),
            'push_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'overdue_time': overdue_time,
            'progress_marketing': '',
            'progress_equipment': '',
            'remark': '',
            'contractor': '',
            'work_desc': supply.compose_materials_text(supply_data['materials']),
            'materials': dict(supply_data['materials']),
            'supply': dict(supply_data),
        }
        try:
            self.store.upsert_supply_order(record)
        except Exception as exc:
            messagebox.showerror('错误', f'写入供方单台账时出错：\n{exc}', parent=self.root)
            return
        # 手机号 / 地址回写到工单
        order['phone'] = vals['phone']
        order['address'] = vals['address']
        order.pop('manager_phone', None)
        self.store.update_order(flow_id, order)
        self.refresh()
        if unmatched:
            messagebox.showwarning(
                '提示', '供方单已生成，但以下模板红字占位未匹配替换：\n'
                + '、'.join(unmatched), parent=self.root)
        messagebox.showinfo('完成', f'供方单已生成：\n{out_path}', parent=self.root)

    def open_supply_window(self):
        SupplyListWindow(self.root, self.store)

    # ----- 导出与汇总 -----
    def export_excel(self):
        rows = self._compute_rows()
        if not rows:
            messagebox.showwarning('提示', '当前没有工单可导出', parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, title='导出Excel', defaultextension='.xlsx',
            initialfile='工单列表.xlsx',
            filetypes=[('Excel 文件', '*.xlsx')])
        if not path:
            return
        try:
            export.export_orders(path, rows)
        except Exception as exc:
            messagebox.showerror('导出失败', f'导出 Excel 时出错：\n{exc}', parent=self.root)
            return
        messagebox.showinfo('完成', f'已导出：\n{path}', parent=self.root)

    def show_summary(self):
        rows = self._compute_rows()
        s = export.summary(rows)
        lines = [f"工单总数：{s['total']}", '', '按流程类型：']
        lines += [f'  {k}：{v}' for k, v in s['by_type'].items()] or ['  （无）']
        lines.append('')
        lines.append('按状态：')
        lines += [f'  {k}：{v}' for k, v in s['by_status'].items()] or ['  （无）']
        messagebox.showinfo('汇总', '\n'.join(lines), parent=self.root)

    # ----- 设置 -----
    def open_settings(self):
        win = SettingsWindow(
            self.root, self.store, on_saved=self.refresh,
            current_paths={'data_dir': self.store.data_dir,
                           'output_dir': self.output_dir},
            on_paths_saved=self.apply_paths)
        self._settings_window = win
        win.bind('<Destroy>', self._on_settings_destroyed)

    def _on_settings_destroyed(self, event):
        """设置窗口关闭后清掉引用（Destroy 事件会冒泡到子控件，需比对 widget）。"""
        if event.widget is self._settings_window:
            self._settings_window = None

    def apply_paths(self, data_dir: str, output_dir: str) -> None:
        """热切换数据/输出路径：重建 Store、更新输出目录并刷新，无需重启。

        由设置窗口「路径配置」页签保存成功后回调触发。
        """
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)
        self.store = store_mod.Store(data_dir)
        self.output_dir = output_dir
        # 设置窗口仍打开时同步其 store 与当前路径引用
        win = self._settings_window
        if win is not None:
            try:
                if win.winfo_exists():
                    win.store = self.store
                    win.current_paths = {'data_dir': data_dir,
                                         'output_dir': output_dir}
            except tk.TclError:
                self._settings_window = None
        self.refresh()
        messagebox.showinfo('提示', '路径配置已生效', parent=self.root)
