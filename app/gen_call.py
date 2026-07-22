# -*- coding: utf-8 -*-
"""iPhone 通话记录详情页截图生成（以真实截图为底版，局部擦除+重绘）。

原理：以 assets/template_call.jpg（真实 iPhone 截图，1280x2781）为底版，
仅擦除并重绘可变内容：状态栏时间、电量数字、大号号码、通话记录时间与时长。
擦除采用"逐行边缘采样插值"：对目标矩形每一行，取左右界外原图像素颜色线性
插值填充，纵向渐变背景无缝复原。其余像素完全保留原图。

依赖：pillow。
"""
from __future__ import annotations

import os
import random
import re
import sys
from datetime import datetime, timedelta

from PIL import Image, ImageDraw, ImageFont


def _asset(name: str) -> str:
    base = getattr(sys, '_MEIPASS',
                   os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, 'assets', name)


# ---------------------------------------------------------------------------
# 字体（Segoe UI 数字形态接近 iOS SF；中文用微软雅黑）
# ---------------------------------------------------------------------------
_F_SEG = r"C:\Windows\Fonts\segoeui.ttf"
_F_SEGB = r"C:\Windows\Fonts\segoeuib.ttf"
_F_SEGSB = r"C:\Windows\Fonts\seguisb.ttf"
_F_CN = r"C:\Windows\Fonts\msyh.ttc"

# macOS 开发调试用候选字体（Windows 路径存在时不会走到这里）
_MAC_CN_FONTS = ("/System/Library/Fonts/PingFang.ttc",
                 "/System/Library/Fonts/STHeiti Light.ttc",
                 "/System/Library/Fonts/Hiragino Sans GB.ttc")
_MAC_EN_FONTS = ("/System/Library/Fonts/Helvetica.ttc",
                 "/System/Library/Fonts/Avenir Next.ttc")


def _resolve_font(preferred: str, fallback_kind: str) -> str:
    """跨平台字体解析：preferred 存在则原样返回（Windows 行为不变）；
    否则按 fallback_kind（'cn'/'en'）依次探测 macOS 候选；
    都找不到则回退 preferred，保持原报错行为。"""
    if os.path.exists(preferred):
        return preferred
    candidates = _MAC_CN_FONTS if fallback_kind == 'cn' else _MAC_EN_FONTS
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    return preferred


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    path = _resolve_font(path, 'cn' if path == _F_CN else 'en')
    if not os.path.exists(path):
        path = _resolve_font(_F_CN, 'cn')
    return ImageFont.truetype(path, size)


def _fit_size(path: str, sample: str, target_h: int) -> int:
    """按样本字符串的字形高度反推字号。"""
    f = _font(path, 100)
    box = f.getbbox(sample)
    h = box[3] - box[1]
    if h <= 0:
        return target_h
    return max(8, round(100 * target_h / h))


# ---------------------------------------------------------------------------
# 模板测量常量（像素，基于 1280x2781 原图实测）
# ---------------------------------------------------------------------------
TW, TH = 1280, 2781

# 状态栏时间 '19:08'
TIME_BBOX = (176, 75, 311, 115)
TIME_ERASE = (160, 55, 330, 135)
TIME_COLOR = (240, 246, 247)
# '19:08' 逐字符槽位（原图实测），保证任意 HH:MM 位置一致
TIME_SLOTS = ((176, 192), (200, 228), (234, 242), (249, 277), (282, 311))
TIME_GLYPH_H = 40

# 大号号码（分组槽位：+86 / 前三位 / 中四位 / 后四位）
NUM_ERASE = (70, 1845, 1215, 1975)
NUM_SLOTS = ((90, 305), (338, 539), (575, 866), (902, 1191))
NUM_TOP, NUM_BOT = 1868, 1953
NUM_COLOR = (250, 250, 252)

# 通话记录行 '今天·19:07'
TODAY_ERASE = (895, 2398, 1180, 2468)
TODAY_RIGHT = 1162
TODAY_VC = 2435
TODAY_CN_H, TODAY_NUM_H = 44, 36
TODAY_GAP_L, TODAY_GAP_R = 19, 18
TODAY_DOT_W = 6
TODAY_COLOR = (230, 230, 239)

# 时长 '10秒钟'
DUR_ERASE = (105, 2468, 290, 2545)
DUR_LEFT = 120
DUR_VC = 2503
DUR_CN_H, DUR_NUM_H = 44, 36
DUR_GAP = 11
DUR_COLOR = (150, 143, 166)

# 电池（胶囊内部）
BAT_ERASE = (1071, 75, 1154, 112)     # 仅内部，保留圆角边缘行
BAT_IN_X0, BAT_IN_X1 = 1072, 1153     # 内部可用宽度（红条 9%≈7px 实测吻合）
BAT_IN_Y0, BAT_IN_Y1 = 75, 112
BAT_REF_COL = 1145                    # 胶囊内干净参考列（逐行取色）
BAT_RED = (226, 76, 75)
BAT_DIGIT_WHITE = (250, 250, 252)
BAT_DIGIT_DARK = (60, 64, 70)
BAT_DIGIT_H = 29


# ---------------------------------------------------------------------------
# 擦除与重绘工具
# ---------------------------------------------------------------------------
def _erase_interp(img: Image.Image, rect, noise: float = 1.3):
    """逐行边缘采样插值擦除矩形区域，使渐变背景无缝复原。"""
    x0, y0, x1, y1 = rect
    px = img.load()
    w, h = img.size
    for y in range(y0, y1):
        cl = px[max(0, x0 - 1), y]
        cr = px[min(w - 1, x1), y]
        n = x1 - x0
        for x in range(x0, x1):
            t = (x - x0 + 1) / (n + 1)
            px[x, y] = tuple(
                max(0, min(255, round(cl[i] + (cr[i] - cl[i]) * t
                                      + random.gauss(0, noise))))
                for i in range(3))


def _erase_colfill(img: Image.Image, rect, ref_col: int, noise: float = 1.0):
    """以参考列逐行取色填充（用于电池胶囊内部这类均匀底色）。"""
    x0, y0, x1, y1 = rect
    px = img.load()
    for y in range(y0, y1):
        c = px[ref_col, y]
        for x in range(x0, x1):
            px[x, y] = tuple(
                max(0, min(255, round(c[i] + random.gauss(0, noise))))
                for i in range(3))


def _bbox(draw, text, font):
    return draw.textbbox((0, 0), text, font=font)


def _draw_at(draw, text, font, fill, left=None, top=None, right=None, vcenter=None):
    """按字形 bbox 精确摆放文字。"""
    tb = _bbox(draw, text, font)
    w, h = tb[2] - tb[0], tb[3] - tb[1]
    if left is None:
        left = right - w
    if top is None:
        top = vcenter - h / 2
    draw.text((left - tb[0], top - tb[1]), text, font=font, fill=fill)
    return w


def _draw_centered_char(draw, ch, font, fill, cx, cy, stroke=0):
    tb = _bbox(draw, ch, font)
    x = cx - (tb[0] + tb[2]) / 2
    y = cy - (tb[1] + tb[3]) / 2
    draw.text((x, y), ch, font=font, fill=fill,
              stroke_width=stroke, stroke_fill=fill)


def _fmt_phone_groups(phone: str) -> list[str]:
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    if len(digits) == 11:
        return ["+86", digits[:3], digits[3:7], digits[7:]]
    return ["+86", digits] if digits else [phone]


# ---------------------------------------------------------------------------
# 各区域重绘
# ---------------------------------------------------------------------------
def _redraw_status_time(img, draw, time_str: str):
    _erase_interp(img, TIME_ERASE)
    f = _font(_F_SEGSB, _fit_size(_F_SEGSB, "0", TIME_GLYPH_H))
    cy = (TIME_BBOX[1] + TIME_BBOX[3]) / 2
    for (a, b), ch in zip(TIME_SLOTS, time_str):
        _draw_centered_char(draw, ch, f, TIME_COLOR, (a + b) / 2, cy)


def _redraw_battery(img, draw, battery: int):
    battery = max(0, min(100, int(battery)))
    _erase_colfill(img, BAT_ERASE, BAT_REF_COL)
    inner_w = BAT_IN_X1 - BAT_IN_X0
    fill_w = round(inner_w * battery / 100)
    if fill_w > 0:
        color = BAT_RED if battery <= 20 else (238, 241, 245)
        draw.rounded_rectangle(
            [BAT_IN_X0, BAT_IN_Y0, BAT_IN_X0 + fill_w, BAT_IN_Y1],
            radius=min(9, fill_w // 2), fill=color)
    digit_color = BAT_DIGIT_WHITE if battery <= 20 else BAT_DIGIT_DARK
    f = _font(_F_SEGSB, _fit_size(_F_SEGSB, "9", BAT_DIGIT_H))
    cx = (BAT_IN_X0 + BAT_IN_X1) / 2
    cy = (BAT_IN_Y0 + BAT_IN_Y1) / 2
    tb = _bbox(draw, str(battery), f)
    x = cx - (tb[0] + tb[2]) / 2
    y = cy - (tb[1] + tb[3]) / 2
    draw.text((x, y), str(battery), font=f, fill=digit_color)


def _redraw_number(img, draw, phone: str):
    _erase_interp(img, NUM_ERASE)
    f = _font(_F_SEGB, _fit_size(_F_SEGB, "0", NUM_BOT - NUM_TOP))
    cy = (NUM_TOP + NUM_BOT) / 2
    groups = _fmt_phone_groups(phone)
    for (a, b), g in zip(NUM_SLOTS, groups):
        cell = (b - a) / max(1, len(g))
        for i, ch in enumerate(g):
            _draw_centered_char(draw, ch, f, NUM_COLOR,
                                a + (i + 0.5) * cell, cy, stroke=1)


def _redraw_record(img, draw, rec_time: datetime, duration_sec: int):
    # '今天 · HH:MM'（右对齐，间隔点两侧各留 19/18px 与原图一致）
    _erase_interp(img, TODAY_ERASE)
    f_cn = _font(_F_CN, _fit_size(_F_CN, "今天", TODAY_CN_H))
    f_num = _font(_F_SEG, _fit_size(_F_SEG, "19:07", TODAY_NUM_H))
    tstr = rec_time.strftime("%H:%M")
    # 自右向左排：数字 -> 间隔点(手绘小圆点,左留18) -> 今天(左留19)
    tb_num = _bbox(draw, tstr, f_num)
    num_l = TODAY_RIGHT - (tb_num[2] - tb_num[0])
    _draw_at(draw, tstr, f_num, TODAY_COLOR, left=num_l, vcenter=TODAY_VC)
    dot_cx = num_l - TODAY_GAP_R - TODAY_DOT_W / 2
    draw.ellipse([dot_cx - 3, TODAY_VC - 3.5, dot_cx + 3, TODAY_VC + 3.5],
                 fill=TODAY_COLOR)
    tb_cn = _bbox(draw, "今天", f_cn)
    cn_l = (num_l - TODAY_GAP_R - TODAY_DOT_W) - TODAY_GAP_L - (tb_cn[2] - tb_cn[0])
    _draw_at(draw, "今天", f_cn, TODAY_COLOR, left=cn_l, vcenter=TODAY_VC)

    # 'X秒钟'（左对齐，去电二字保留不动）
    _erase_interp(img, DUR_ERASE)
    f_dcn = _font(_F_CN, _fit_size(_F_CN, "秒钟", DUR_CN_H))
    f_dnum = _font(_F_SEG, _fit_size(_F_SEG, "10", DUR_NUM_H))
    d = str(max(0, int(duration_sec)))
    w2 = _draw_at(draw, d, f_dnum, DUR_COLOR, left=DUR_LEFT, vcenter=DUR_VC)
    _draw_at(draw, "秒钟", f_dcn, DUR_COLOR,
             left=DUR_LEFT + w2 + DUR_GAP, vcenter=DUR_VC)


# ---------------------------------------------------------------------------
# 主接口
# ---------------------------------------------------------------------------
def gen_call_screenshot(phone: str, out_path: str, duration_sec: int = 10,
                        battery: int = 79, time: datetime | None = None) -> str:
    """以真实截图为底版生成通话记录详情页截图，保存 PNG 并返回 out_path。"""
    now = time or datetime.now()
    rec_time = now - timedelta(minutes=1)  # 通话记录时间略早于状态栏时间，更自然

    img = Image.open(_asset("template_call.jpg")).convert("RGB")
    if img.size != (TW, TH):
        img = img.resize((TW, TH), Image.LANCZOS)
    draw = ImageDraw.Draw(img)

    _redraw_status_time(img, draw, now.strftime("%H:%M"))
    _redraw_battery(img, draw, battery)
    _redraw_number(img, draw, phone)
    _redraw_record(img, draw, rec_time, duration_sec)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path, "PNG")
    return out_path
