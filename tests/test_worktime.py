# -*- coding: utf-8 -*-
"""worktime 时限计算引擎测试。

基准日历（2024 年 1 月）：
- 2024-01-05 周五，2024-01-06 周六，2024-01-07 周日，
- 2024-01-08 周一，2024-01-09 周二。
"""

import os
import sys
from datetime import date, datetime

# 保证可以 import app 包（项目根目录加入 sys.path）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.worktime import (
    FLOW_TYPES,
    add_workdays,
    adjust_start,
    compute_deadlines,
    is_workday,
    remaining_text,
    status_color,
)

FRI = date(2024, 1, 5)   # 周五
SAT = date(2024, 1, 6)   # 周六
SUN = date(2024, 1, 7)   # 周日
MON = date(2024, 1, 8)   # 周一
TUE = date(2024, 1, 9)   # 周二

NO_HOLIDAY: set = set()
NO_EXTRA: set = set()


def test_is_workday_basic():
    assert is_workday(FRI, NO_HOLIDAY, NO_EXTRA) is True
    assert is_workday(SAT, NO_HOLIDAY, NO_EXTRA) is False
    assert is_workday(SUN, NO_HOLIDAY, NO_EXTRA) is False


def test_is_workday_holiday_and_extra():
    # 周一遇节假日 → 非工作日
    assert is_workday(MON, {MON}, NO_EXTRA) is False
    # 周六调休上班 → 工作日
    assert is_workday(SAT, NO_HOLIDAY, {SAT}) is True
    # 调休上班日优先于节假日（同日既是调休又是节假日时按上班算）
    assert is_workday(SAT, {SAT}, {SAT}) is True


def test_adjust_start_weekend_skip():
    """周末顺延：周六 10:00 → 下周一 8:30。"""
    dt = datetime(2024, 1, 6, 10, 0)
    assert adjust_start(dt, NO_HOLIDAY, NO_EXTRA) == datetime(2024, 1, 8, 8, 30)


def test_adjust_start_holiday_skip():
    """节假日顺延：周五晚遇下周一为节假日 → 周二 8:30。"""
    dt = datetime(2024, 1, 5, 18, 0)  # 周五 17:30 之后
    assert adjust_start(dt, {MON}, NO_EXTRA) == datetime(2024, 1, 9, 8, 30)
    # 假期当天直接报装也顺延到假期后第一个工作日
    dt2 = datetime(2024, 1, 8, 10, 0)  # 周一（节假日）
    assert adjust_start(dt2, {MON}, NO_EXTRA) == datetime(2024, 1, 9, 8, 30)


def test_adjust_start_after_1730():
    """17:30 之后（含 17:30）→ 下一工作日 8:30。"""
    assert adjust_start(datetime(2024, 1, 5, 17, 30), NO_HOLIDAY, NO_EXTRA) == datetime(2024, 1, 8, 8, 30)
    assert adjust_start(datetime(2024, 1, 8, 20, 15), NO_HOLIDAY, NO_EXTRA) == datetime(2024, 1, 9, 8, 30)


def test_adjust_start_before_830():
    """早于 8:30 → 当日 8:30。"""
    assert adjust_start(datetime(2024, 1, 8, 6, 30), NO_HOLIDAY, NO_EXTRA) == datetime(2024, 1, 8, 8, 30)
    # 正好 8:30 不变
    assert adjust_start(datetime(2024, 1, 8, 8, 30), NO_HOLIDAY, NO_EXTRA) == datetime(2024, 1, 8, 8, 30)


def test_adjust_start_within_window_unchanged():
    """工作时间内不变。"""
    dt = datetime(2024, 1, 8, 10, 23)
    assert adjust_start(dt, NO_HOLIDAY, NO_EXTRA) == dt


def test_adjust_start_extra_workday():
    """调休上班的周六按工作日处理。"""
    dt = datetime(2024, 1, 6, 10, 0)
    assert adjust_start(dt, NO_HOLIDAY, {SAT}) == dt


def test_add_workdays_same_day():
    """时限当天内可消化：周一 10:00 + 0.5 天（12h）→ 周一 22:00。"""
    start = datetime(2024, 1, 8, 10, 0)
    assert add_workdays(start, 0.5, NO_HOLIDAY, NO_EXTRA) == datetime(2024, 1, 8, 22, 0)


def test_add_workdays_cross_weekend():
    """24h 累计跨周末：周五 10:00 + 1 天（24h）。

    周五贡献 14h（10:00→24:00），周末贡献 0，周一补 10h → 周一 10:00。
    """
    start = datetime(2024, 1, 5, 10, 0)
    assert add_workdays(start, 1, NO_HOLIDAY, NO_EXTRA) == datetime(2024, 1, 8, 10, 0)
    # +2 天（48h）：周五 14h + 周一 24h + 周二 10h → 周二 10:00
    assert add_workdays(start, 2, NO_HOLIDAY, NO_EXTRA) == datetime(2024, 1, 9, 10, 0)


def test_add_workdays_with_holiday():
    """跨节假日：周五 10:00 + 1 天，周一为节假日 → 周二 10:00。"""
    start = datetime(2024, 1, 5, 10, 0)
    assert add_workdays(start, 1, {MON}, NO_EXTRA) == datetime(2024, 1, 9, 10, 0)


def test_add_workdays_zero():
    """0 天时限：截止时间即起算时间。"""
    start = datetime(2024, 1, 8, 10, 0)
    assert add_workdays(start, 0, NO_HOLIDAY, NO_EXTRA) == start


def test_status_color_overdue():
    now = datetime(2024, 1, 8, 10, 0)
    assert status_color(now, datetime(2024, 1, 8, 9, 59), NO_HOLIDAY, NO_EXTRA) == 'overdue'


def test_status_color_warn():
    now = datetime(2024, 1, 5, 10, 0)  # 周五
    # 截止在今天 → warn
    assert status_color(now, datetime(2024, 1, 5, 16, 0), NO_HOLIDAY, NO_EXTRA) == 'warn'
    # 截止在下一个工作日（周一）→ warn（周末不算，顺延口径）
    assert status_color(now, datetime(2024, 1, 8, 10, 0), NO_HOLIDAY, NO_EXTRA) == 'warn'


def test_status_color_normal_and_none():
    now = datetime(2024, 1, 5, 10, 0)  # 周五
    # 截止在周二（晚于下一个工作日）→ normal
    assert status_color(now, datetime(2024, 1, 9, 10, 0), NO_HOLIDAY, NO_EXTRA) == 'normal'
    # deadline 为 None → none
    assert status_color(now, None, NO_HOLIDAY, NO_EXTRA) == 'none'


def test_remaining_text():
    now = datetime(2024, 1, 8, 10, 0)
    assert remaining_text(now, datetime(2024, 1, 10, 13, 0)) == '剩2天3小时'
    assert remaining_text(now, datetime(2024, 1, 7, 5, 0)) == '已超1天5小时'
    assert remaining_text(now, datetime(2024, 1, 8, 15, 0)) == '剩5小时'
    assert remaining_text(now, None) == '-'


def test_compute_deadlines():
    """compute_deadlines：visit 为 None 的类型上门服务截止返回 None。"""
    start = datetime(2024, 1, 8, 8, 30)  # 周一 8:30
    visit, full = compute_deadlines('低压居民新装', start, NO_HOLIDAY, NO_EXTRA)
    assert visit is None
    assert full > start
    # 居民新装 full=5 个工作日（120h）：周一 8:30 → 下周一 8:30
    assert full == datetime(2024, 1, 15, 8, 30)

    visit2, full2 = compute_deadlines('低压非居民新装', start, NO_HOLIDAY, NO_EXTRA)
    assert visit2 is not None and visit2 < full2
    # 非居民新装 visit=4（96h）→ 周五 8:30；full=15（360h）→ 第四周周一 8:30
    assert visit2 == datetime(2024, 1, 12, 8, 30)
    assert full2 == datetime(2024, 1, 29, 8, 30)

    assert FLOW_TYPES['低压非居民新装']['visit'] == 4


def test_flow_types_contract():
    """六种流程类型时限配置与共享契约一致。"""
    assert set(FLOW_TYPES.keys()) == {
        '低压居民新装', '低压居民增容',
        '低压充电桩新装', '低压充电桩增容',
        '低压非居民新装', '低压非居民增容',
    }
    # 居民新装/增容：full=5，无上门服务环节
    assert FLOW_TYPES['低压居民新装'] == {'full': 5, 'visit': None}
    assert FLOW_TYPES['低压居民增容'] == {'full': 5, 'visit': None}
    # 充电桩新装/增容：full=15，上门服务时限 3 个工作日
    assert FLOW_TYPES['低压充电桩新装'] == {'full': 15, 'visit': 3}
    assert FLOW_TYPES['低压充电桩增容'] == {'full': 15, 'visit': 3}
    # 非居民新装/增容：full=15，上门服务时限 4 个工作日
    assert FLOW_TYPES['低压非居民新装'] == {'full': 15, 'visit': 4}
    assert FLOW_TYPES['低压非居民增容'] == {'full': 15, 'visit': 4}


def test_compute_deadlines_charging_pile():
    """充电桩 visit=3：周一 8:30 + 3 个工作日（72h）→ 周四 8:30。"""
    start = datetime(2024, 1, 8, 8, 30)  # 周一 8:30
    visit, full = compute_deadlines('低压充电桩新装', start, NO_HOLIDAY, NO_EXTRA)
    assert visit == datetime(2024, 1, 11, 8, 30)
    assert full == datetime(2024, 1, 29, 8, 30)
    # 跨周末：周五 8:30 起算，visit=3 → 周三 8:30（周末贡献 0）
    start2 = datetime(2024, 1, 5, 8, 30)  # 周五 8:30
    visit2, _ = compute_deadlines('低压充电桩新装', start2, NO_HOLIDAY, NO_EXTRA)
    assert visit2 == datetime(2024, 1, 10, 8, 30)


def test_compute_deadlines_capacity_same_as_new():
    """增容与新装时限一致：三种业务各自对比。"""
    start = datetime(2024, 1, 8, 8, 30)  # 周一 8:30
    for new, expand in (
        ('低压居民新装', '低压居民增容'),
        ('低压充电桩新装', '低压充电桩增容'),
        ('低压非居民新装', '低压非居民增容'),
    ):
        assert compute_deadlines(new, start, NO_HOLIDAY, NO_EXTRA) == \
            compute_deadlines(expand, start, NO_HOLIDAY, NO_EXTRA)


if __name__ == '__main__':
    # pytest 不可用时可直接 python tests\test_worktime.py 运行
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
