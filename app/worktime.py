# -*- coding: utf-8 -*-
"""时限计算引擎：工作日判定、起算调整、工作时限累加与临期提醒。

口径说明：
- 工作日：周一至周五且不在节假日集合中，或属于调休上班日（extra_workdays）。
- 工作时限：24 小时累计制，每个工作日贡献完整 24 小时（午休不扣），非工作日贡献 0。
- 工作时间窗：每日 8:30 - 17:30，仅用于起算时间调整（adjust_start）。
"""

from datetime import date, datetime, time, timedelta

# 每日工作时间窗（仅用于起算调整）
DAY_START = time(8, 30)
DAY_END = time(17, 30)

# 流程类型时限配置（单位：工作日，24 小时累计制）
# full = 全流程时限；visit = 上门服务时限（None 表示该类型无上门服务环节）
FLOW_TYPES = {
    '低压居民新装': {'full': 5, 'visit': None},
    '低压居民增容': {'full': 5, 'visit': None},
    '低压充电桩新装': {'full': 15, 'visit': 3},
    '低压充电桩增容': {'full': 15, 'visit': 3},
    '低压非居民新装': {'full': 15, 'visit': 4},
    '低压非居民增容': {'full': 15, 'visit': 4},
}


def is_workday(d: date, holidays: set, extra_workdays: set) -> bool:
    """判断某天是否为工作日。

    周一至周五且不在 holidays 中，或属于 extra_workdays（调休上班日）。
    """
    if d in extra_workdays:
        return True
    if d in holidays:
        return False
    return d.weekday() < 5  # 周一=0 ... 周五=4


def _next_workday(d: date, holidays: set, extra_workdays: set) -> date:
    """返回 d 之后（不含 d 当天）的第一个工作日。"""
    cur = d + timedelta(days=1)
    while not is_workday(cur, holidays, extra_workdays):
        cur += timedelta(days=1)
    return cur


def adjust_start(dt: datetime, holidays: set, extra_workdays: set) -> datetime:
    """把任意报装时间调整为合法的起算时间。

    规则按 ③①② 顺序综合判断：
    ③ dt 落在周末/节假日 → 假期后第一个工作日 8:30；
    ① dt 早于当日 8:30 → 当日 8:30；
    ② dt 晚于等于 17:30 → 下一工作日 8:30。
    """
    d = dt.date()
    # ③ 非工作日：顺延到假期后第一个工作日 8:30
    if not is_workday(d, holidays, extra_workdays):
        return datetime.combine(_next_workday(d, holidays, extra_workdays), DAY_START)
    # ① 早于 8:30：按当日 8:30 起算
    if dt.time() < DAY_START:
        return datetime.combine(d, DAY_START)
    # ② 晚于等于 17:30：下一工作日 8:30 起算
    if dt.time() >= DAY_END:
        return datetime.combine(_next_workday(d, holidays, extra_workdays), DAY_START)
    return dt


def add_workdays(start: datetime, n: float, holidays: set, extra_workdays: set) -> datetime:
    """从 start 起累加 n 个工作日的时限（24 小时累计制），返回截止时间。

    每个工作日贡献完整 24 小时（午休不扣），非工作日贡献 0。
    算法：remaining = n * 24h，从 start 起逐日推进；
    当天是工作日则可消耗时长，否则跳到次日 0 点。
    """
    remaining = timedelta(hours=n * 24)
    cur = start
    while remaining > timedelta(0):
        if is_workday(cur.date(), holidays, extra_workdays):
            # 当天剩余可用时长 = 到次日 0 点的时长
            next_midnight = datetime.combine(cur.date() + timedelta(days=1), time(0, 0))
            available = next_midnight - cur
            if available >= remaining:
                return cur + remaining
            remaining -= available
            cur = next_midnight
        else:
            # 非工作日贡献 0，直接跳到次日 0 点
            cur = datetime.combine(cur.date() + timedelta(days=1), time(0, 0))
    return cur


def status_color(now: datetime, deadline: datetime | None, holidays: set, extra_workdays: set) -> str:
    """返回工单时限状态颜色标识：'overdue' / 'warn' / 'normal' / 'none'。

    - deadline 为 None → 'none'
    - now > deadline → 'overdue'（已超期）
    - deadline 落在“今天或下一个工作日”内 → 'warn'（临期提醒口径）
    - 否则 → 'normal'
    """
    if deadline is None:
        return 'none'
    if now > deadline:
        return 'overdue'
    # 临期口径：deadline 日期 <= 今天之后的下一个工作日日期
    nxt = _next_workday(now.date(), holidays, extra_workdays)
    if deadline.date() <= nxt:
        return 'warn'
    return 'normal'


def remaining_text(now: datetime, deadline: datetime | None) -> str:
    """返回剩余/超期时间的人读文本，如 '剩2天3小时' / '已超1天5小时' / '-'。"""
    if deadline is None:
        return '-'

    def _fmt(delta: timedelta) -> str:
        days = delta.days
        hours = delta.seconds // 3600
        if days > 0 and hours > 0:
            return f'{days}天{hours}小时'
        if days > 0:
            return f'{days}天'
        return f'{hours}小时'

    if now > deadline:
        return '已超' + _fmt(now - deadline)
    return '剩' + _fmt(deadline - now)


def compute_deadlines(flow_type: str, start: datetime, holidays: set, extra_workdays: set):
    """计算 (上门服务截止, 全流程截止)。

    start 为任意报装时间，内部先经 adjust_start 对齐为合法起算时间
    （周末/节假日顺延、早于 8:30 按 8:30、晚于等于 17:30 顺延下一工作日）。
    visit 为 None 的类型，上门服务截止返回 None。
    """
    start = adjust_start(start, holidays, extra_workdays)
    cfg = FLOW_TYPES[flow_type]
    visit_deadline = (
        add_workdays(start, cfg['visit'], holidays, extra_workdays)
        if cfg['visit'] is not None
        else None
    )
    full_deadline = add_workdays(start, cfg['full'], holidays, extra_workdays)
    return visit_deadline, full_deadline
