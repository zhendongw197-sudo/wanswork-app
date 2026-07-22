# -*- coding: utf-8 -*-
"""仿真短信对话截图生成（以真实 iPhone 截图为底版）。

底版：assets/template_sms.jpg（真实 iMessage 截图，1280x2781）。
策略：底版像素全部保留，仅对可变内容做局部擦除 + 重绘——
  ① 状态栏时间；② 电池电量；③ 顶部号码胶囊；④ “今天 HH:MM” 时间戳；
  ⑤ 蓝色长短信气泡（圆角 + 右下尾巴 + 电话号码下划线）；
  ⑥ “已送达”；⑦ 灰色回复气泡“是”（含左下尾巴，位置随蓝气泡联动）。

所有几何与颜色均实测自底版原图（单位：像素，1280x2781 坐标系）。
新绘元素在 2 倍超采样层上绘制后 LANCZOS 缩回，保证边缘抗锯齿与原图一致。

依赖：pillow。中文字体微软雅黑，数字/英文用 Segoe UI Bold。
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime

from PIL import Image, ImageChops, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
W, H = 1280, 2781  # 底版分辨率（iPhone 截图物理像素）

COMPANY = "溧水区供电公司"  # 供电公司名称（如需变更改这里即可）

_FONT_CN = r"C:\Windows\Fonts\msyh.ttc"        # 微软雅黑
_FONT_CN_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"  # 微软雅黑 Bold
_FONT_EN_BOLD = r"C:\Windows\Fonts\segoeuib.ttf"  # Segoe UI Bold（状态栏时间/电量）
_FONT_FALLBACK = r"C:\Windows\Fonts\simsun.ttc"  # 宋体

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

# 短信正文模板
_SMS_TEMPLATE = (
    "尊敬的{customer_name}您好，这里是{company}低压客户经理{manager_name}。"
    "您于{apply_date}在{address}申请{flow_type}新装增容业务，流程号{flow_id}，"
    "由于用户{reason}，需终止此流程，请确实是否属实，回复是或否即可，"
    "您后续有任何问题，可电话联系{manager_phone}，谢谢您对我们工作的理解与支持。"
)

_SS = 2  # 超采样倍数

# ---- 底版实测颜色 ----
_BLUE = (88, 165, 245)        # 蓝气泡填充（原图众数采样）
_GRAY_BUBBLE = (233, 233, 233)  # 灰气泡填充
_GRAY_TEXT = (142, 142, 142)  # 时间戳 / 已送达
_BATT_GRAY = (178, 178, 178)  # 电池胶囊底
_BATT_RED = (236, 72, 73)     # 低电量红色
_CHEVRON = (196, 196, 200)    # 号码右侧 > 箭头
_CAPSULE_BG = (253, 253, 253)  # 号码胶囊底（极浅）
_BLACK = (10, 10, 10)
_WHITE = (255, 255, 255)

# ---- 底版实测几何 ----
_TIME_X, _TIME_TOP = 178, 76            # 状态栏时间左缘 / 字形顶
_TIME_SIZE = 50                          # segoeuib，"18:57" 宽 130px
_BATT_BODY = (1067, 72, 1147, 114)       # 电池胶囊体
_BATT_INNER = (1071, 76, 1143, 110)      # 电量填充区
_BATT_NUB = (1150, 86, 1157, 100)        # 电池正极凸点
_BATT_SIZE = 40                          # 电量数字字号
_CAPSULE_RECT = (350, 350, 932, 450)     # 号码胶囊
_CAPSULE_R = 50
_NUM_SIZE = 48                           # 号码字号（msyhbd，宽 469≈原 474）
_NUM_TOP = 370                           # 号码字形顶
_GROUP_CX = 644                          # 号码+箭头组中心
_CHEV_W, _CHEV_H = 22, 33                # 箭头尺寸
_CHEV_GAP = 8                            # 号码与箭头间距
_TS_CX, _TS_TOP = 640, 621               # 时间戳中心 / 字形顶
_TS_SIZE = 31
_BUBBLE_X0, _BUBBLE_X1, _BUBBLE_TOP = 330, 1220, 676
_BUBBLE_R = 55
_BODY_SIZE = 48                          # 气泡正文字号
_TEXT_INSET_X = 46                       # 气泡内左右留白
_TEXT_TOP_PAD = 38                       # 气泡顶到首行字形顶
_TEXT_BOT_PAD = 37                       # 末行字形底到气泡底
_LINE_PITCH = 58                         # 行距
_GLYPH_H = 40                            # 正文字形高（实测 39-41）
_DELIVERED_SIZE = 30
_DELIVERED_RIGHT_INSET = 60              # 已送达右缘距气泡右缘
_DELIVERED_TOP_GAP = 23                  # 已送达字形顶距气泡底
_GRAY_X0 = 58
_GRAY_TOP_GAP = 75                       # 灰气泡顶距蓝气泡底
_GRAY_H = 124
_GRAY_INSET_X = 49
_GRAY_TOP_PAD = 38


# ---------------------------------------------------------------------------
# 资源与字体
# ---------------------------------------------------------------------------
def _asset(name: str) -> str:
    base = getattr(sys, "_MEIPASS",
                   os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "assets", name)


def _font(size: int, bold: bool = False, en: bool = False) -> ImageFont.FreeTypeFont:
    """加载字体。en=True 用 Segoe UI Bold（数字/英文），否则微软雅黑。"""
    if en:
        path = _resolve_font(_FONT_EN_BOLD, 'en')
    elif bold:
        path = _resolve_font(_FONT_CN_BOLD, 'cn')
    else:
        path = _FONT_CN
    if not os.path.exists(path):
        path = _FONT_CN if os.path.exists(_FONT_CN) else _FONT_FALLBACK
        path = _resolve_font(path, 'cn')
    return ImageFont.truetype(path, size)


# ---------------------------------------------------------------------------
# 文本工具（与原版一致：数字/英文不断词、标点不落行首）
# ---------------------------------------------------------------------------
_NO_LINE_START = "，。、；：？！）》】”’%‰"


def _fmt_phone(phone: str) -> str:
    """手机号格式化为 +86 XXX XXXX XXXX。"""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    if len(digits) == 11:
        return f"+86 {digits[:3]} {digits[3:7]} {digits[7:]}"
    return f"+86 {digits}" if digits else phone


def _tokenize(text: str) -> list[str]:
    """把文本切成折行单元：每个汉字/标点单独一个单元，连续的字母数字算一个整体。"""
    tokens, buf = [], ""
    for ch in text:
        if ch.isascii() and (ch.isalnum() or ch in "+-.@"):
            buf += ch
        else:
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(ch)
    if buf:
        tokens.append(buf)
    return tokens


def _wrap_text(draw, text: str, font, max_w: int) -> list[str]:
    """按像素宽度自动换行：数字/英文不断开，标点不出现在行首（避头尾）。"""
    lines, cur = [], ""
    for tok in _tokenize(text):
        if tok == "\n":
            lines.append(cur)
            cur = ""
            continue
        # 标点禁止在行首：即使超宽也并入上一行
        if cur and tok in _NO_LINE_START:
            cur += tok
            continue
        if not cur or draw.textlength(cur + tok, font=font) <= max_w:
            cur += tok
        else:
            lines.append(cur)
            cur = tok
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------------------
# 绘制辅助
# ---------------------------------------------------------------------------
def _erase(img: Image.Image, rect: tuple[int, int, int, int]) -> None:
    """用带轻微噪点的白块擦除区域，模拟 JPEG 底噪，避免"过于干净"的补丁感。"""
    x0, y0, x1, y1 = rect
    w, h = x1 - x0, y1 - y0
    base = Image.new("L", (w, h), 255)
    noise = Image.effect_noise((w, h), 4)  # 均值 128 的高斯噪
    patch = ImageChops.add(base, noise, 1.0, -128)
    img.paste(Image.merge("RGB", (patch, patch, patch)), (x0, y0))


def _s(v: float) -> int:
    return int(round(v * _SS))


def _sr(rect) -> list[int]:
    return [_s(rect[0]), _s(rect[1]), _s(rect[2]), _s(rect[3])]


def _text_at(od: ImageDraw.ImageDraw, x: float, glyph_top: float, text: str,
             font: ImageFont.FreeTypeFont, fill, anchor: str = "left") -> None:
    """以"字形顶"为纵向基准画文字（坐标为 1x 逻辑坐标，内部换算超采样）。"""
    bbox = od.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    if anchor == "center":
        x0 = _s(x) - bbox[0] - tw // 2
    elif anchor == "right":
        x0 = _s(x) - bbox[0] - tw
    else:
        x0 = _s(x) - bbox[0]
    od.text((x0, _s(glyph_top) - bbox[1]), text, font=font, fill=fill)


# ---------------------------------------------------------------------------
# 主接口
# ---------------------------------------------------------------------------
def gen_sms_screenshot(customer_name: str, manager_name: str, apply_date: str,
                       address: str, flow_type: str, flow_id: str, reason: str,
                       manager_phone: str, out_path: str, battery: int = 79,
                       time: datetime | None = None,
                       customer_phone: str | None = None) -> str:
    """生成仿 iMessage 短信截图，保存 PNG 并返回 out_path。

    customer_phone：顶部号码胶囊显示的对方号码（即客户手机号）。
    不传时回退为 manager_phone（兼容旧调用）。
    """
    now = time or datetime.now()
    time_str = now.strftime("%H:%M")

    body = _SMS_TEMPLATE.format(
        customer_name=customer_name, company=COMPANY, manager_name=manager_name,
        apply_date=apply_date, address=address, flow_type=flow_type,
        flow_id=flow_id, reason=reason, manager_phone=manager_phone,
    )

    img = Image.open(_asset("template_sms.jpg")).convert("RGB")

    # ---- 1. 局部擦除（底版旧内容） ----
    _erase(img, (150, 55, 345, 130))      # 状态栏时间
    _erase(img, (1045, 60, 1170, 126))    # 电池
    _erase(img, (335, 338, 960, 462))     # 号码胶囊
    _erase(img, (480, 605, 800, 662))     # 时间戳
    _erase(img, (315, 660, 1235, 1400))   # 蓝气泡 + 尾巴
    _erase(img, (1020, 1388, 1185, 1438))  # 已送达
    _erase(img, (38, 1438, 235, 1605))    # 灰气泡 + 尾巴

    # ---- 2. 超采样层重绘 ----
    ov = Image.new("RGBA", (W * _SS, H * _SS), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    S = _SS

    f_time = _font(_TIME_SIZE * S, en=True)
    f_batt = _font(_BATT_SIZE * S, en=True)
    f_num = _font(_NUM_SIZE * S, bold=True)
    f_ts = _font(_TS_SIZE * S)
    f_body = _font(_BODY_SIZE * S)
    f_measure = _font(_BODY_SIZE)  # 1x 测量字体（折行用）

    # ① 状态栏时间
    _text_at(od, _TIME_X, _TIME_TOP, time_str, f_time, _BLACK)

    # ② 电池：灰色胶囊 + 电量填充 + 正极凸点 + 白色数字
    od.rounded_rectangle(_sr(_BATT_BODY), radius=_s(21), fill=_BATT_GRAY)
    ix0, iy0, ix1, iy1 = _BATT_INNER
    pct = max(0, min(100, battery))
    fill_w = max(8, int((ix1 - ix0) * pct / 100))
    level_color = _BATT_RED if pct <= 20 else (45, 45, 45)
    if fill_w >= 28:
        od.rounded_rectangle(_sr((ix0, iy0, ix0 + fill_w, iy1)),
                             radius=_s(15), fill=level_color)
    else:
        od.rectangle(_sr((ix0, iy0, ix0 + fill_w, iy1)), fill=level_color)
    od.rounded_rectangle(_sr(_BATT_NUB), radius=_s(3), fill=_BATT_GRAY)
    batt_cx = (_BATT_BODY[0] + _BATT_BODY[2]) / 2
    batt_cy = (_BATT_BODY[1] + _BATT_BODY[3]) / 2
    bb = od.textbbox((0, 0), str(pct), font=f_batt)
    _text_at(od, batt_cx, batt_cy - (bb[3] - bb[1]) / S / 2, str(pct),
             f_batt, _WHITE, anchor="center")

    # ③ 号码胶囊：浅色圆角底 + 黑粗号码 + 灰色 > 箭头
    od.rounded_rectangle(_sr(_CAPSULE_RECT), radius=_s(_CAPSULE_R), fill=_CAPSULE_BG)
    num_text = _fmt_phone(customer_phone or manager_phone)
    num_w = od.textlength(num_text, font=f_num) / S
    group_w = num_w + _CHEV_GAP + _CHEV_W
    num_x = _GROUP_CX - group_w / 2
    _text_at(od, num_x, _NUM_TOP, num_text, f_num, _BLACK)
    chx = num_x + num_w + _CHEV_GAP
    chy = _NUM_TOP + 1
    od.line([(_s(chx), _s(chy)), (_s(chx + _CHEV_W), _s(chy + _CHEV_H / 2)),
             (_s(chx), _s(chy + _CHEV_H))],
            fill=_CHEVRON, width=_s(5), joint="curve")

    # ④ 时间戳 “今天 HH:MM”
    _text_at(od, _TS_CX, _TS_TOP, f"今天 {time_str}", f_ts, _GRAY_TEXT,
             anchor="center")

    # ⑤ 蓝色气泡：固定原气泡最大宽，高度随行数自适应
    text_max_w = (_BUBBLE_X1 - _BUBBLE_X0) - _TEXT_INSET_X * 2
    probe = ImageDraw.Draw(img)
    lines = _wrap_text(probe, body, f_measure, text_max_w)
    n = len(lines)
    b_y0 = _BUBBLE_TOP
    b_y1 = b_y0 + _TEXT_TOP_PAD + _GLYPH_H + _LINE_PITCH * (n - 1) + _TEXT_BOT_PAD
    od.rounded_rectangle(_sr((_BUBBLE_X0, b_y0, _BUBBLE_X1, b_y1)),
                         radius=_s(_BUBBLE_R), fill=_BLUE)
    # 右下角尾巴（实测：自气泡底右段向右下收成小尖）
    od.polygon([(_s(1161), _s(b_y1 - 4)), (_s(1190), _s(b_y1 - 4)),
                (_s(1196), _s(b_y1 + 19)), (_s(1191), _s(b_y1 + 19))], fill=_BLUE)

    # 气泡正文（电话号码自动加下划线，模拟 iOS 识别效果）
    phone_raw = str(manager_phone)
    tx = _BUBBLE_X0 + _TEXT_INSET_X
    ty = b_y0 + _TEXT_TOP_PAD
    for ln in lines:
        _text_at(od, tx, ty, ln, f_body, _WHITE)
        idx = ln.find(phone_raw)
        if idx >= 0 and phone_raw:
            pre = od.textlength(ln[:idx], font=f_body) / S
            pw = od.textlength(phone_raw, font=f_body) / S
            uy = ty + _GLYPH_H + 3
            od.rectangle(_sr((tx + pre, uy, tx + pre + pw, uy + 3)), fill=_WHITE)
        ty += _LINE_PITCH

    # ⑥ “已送达”（右缘对齐气泡右缘内缩，随气泡底联动）
    _text_at(od, _BUBBLE_X1 - _DELIVERED_RIGHT_INSET, b_y1 + _DELIVERED_TOP_GAP,
             "已送达", f_ts, _GRAY_TEXT, anchor="right")

    # ⑦ 灰色回复气泡 “是”（位置随蓝气泡底联动）
    g_y0 = b_y1 + _GRAY_TOP_GAP
    g_y1 = g_y0 + _GRAY_H
    reply = "是"
    rw = od.textlength(reply, font=f_body) / S
    g_x1 = _GRAY_X0 + _GRAY_INSET_X + rw + _GRAY_INSET_X
    od.rounded_rectangle(_sr((_GRAY_X0, g_y0, g_x1, g_y1)),
                         radius=_s(_BUBBLE_R), fill=_GRAY_BUBBLE)
    # 左下角尾巴（实测：自气泡底左段向左下收成小尖）
    od.polygon([(_s(88), _s(g_y1 - 3)), (_s(111), _s(g_y1 - 3)),
                (_s(89), _s(g_y1 + 11)), (_s(84), _s(g_y1 + 11))],
               fill=_GRAY_BUBBLE)
    _text_at(od, _GRAY_X0 + _GRAY_INSET_X, g_y0 + _GRAY_TOP_PAD, reply,
             f_body, (20, 20, 20))

    # ---- 3. 缩回合成 ----
    ov = ov.resize((W, H), Image.LANCZOS)
    out = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    out.save(out_path, "PNG")
    return out_path


if __name__ == "__main__":
    # 用底版原始数据自检：应得到与原图几乎一致的画面
    gen_sms_screenshot(
        customer_name="刘露露", manager_name="王振东", apply_date="2026年7月7日",
        address="溧水区永阳镇广成东方名城", flow_type="低压充电桩",
        flow_id="3226070700066527", reason="暂无用电需求",
        manager_phone="17302549216",
        out_path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "samples", "短信确认截图.png"),
        battery=11, time=datetime(2026, 7, 7, 18, 57),
    )
