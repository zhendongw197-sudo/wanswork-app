# -*- coding: utf-8 -*-
"""生成全套示例材料到 samples\\ 目录，并做基本校验。

用法（在项目根目录或任意目录下）：
    python tests\\gen_samples.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

# 让脚本可以直接运行：把项目根目录加入 sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from app.gen_call import gen_call_screenshot          # noqa: E402
from app.gen_sms import gen_sms_screenshot            # noqa: E402
from app.gen_docs import (                            # noqa: E402
    gen_termination_note, gen_jiaodi_apply,
    gen_construct_plan, gen_supervision_note,
)

SAMPLES = os.path.join(PROJECT_ROOT, "samples")

# 示例工单数据
ORDER = {
    "flow_id": "3226070700066527",
    "flow_type": "低压充电桩",
    "account_no": "3201240001234567",
    "account_name": "刘露露",
    "start_time": "2026-07-07 09:30:00",
    "manager": "王振东",
    "manager_phone": "17302549216",
    "address": "溧水区永阳镇广成东方名城",
    "phone": "18936863386",
}

CONFIG = {
    "gas_company": "溧水区燃气有限公司",
    "org_name": "国网南京市溧水区供电公司",
    "dig_depth_cm": "80",
    "builder_name": "南京宏远电力工程有限公司",
    "builder_leader": "李建国",
    "builder_phone": "13805170000",
    "period_days": "3",
}

REASON = "暂无用电需求"


def _verify_docx(path: str, keywords: list[str]) -> bool:
    """用 python-docx 回读校验关键文字是否都在文档里。"""
    from docx import Document
    text = "\n".join(p.text for p in Document(path).paragraphs)
    missing = [k for k in keywords if k not in text]
    if missing:
        print(f"  [校验失败] {os.path.basename(path)} 缺少关键字: {missing}")
        return False
    print(f"  [校验通过] {os.path.basename(path)}")
    return True


def main() -> int:
    os.makedirs(SAMPLES, exist_ok=True)
    now = datetime(2026, 7, 7, 18, 56)
    ok = True

    # 1. 通话截图
    call_png = os.path.join(SAMPLES, "通话记录截图.png")
    gen_call_screenshot(ORDER["phone"], call_png, duration_sec=10, battery=79, time=now)
    print(f"已生成: {call_png}")

    # 2. 短信截图
    sms_png = os.path.join(SAMPLES, "短信确认截图.png")
    gen_sms_screenshot(
        customer_name=ORDER["account_name"], manager_name=ORDER["manager"],
        apply_date="2026年7月7日", address=ORDER["address"],
        flow_type=ORDER["flow_type"], flow_id=ORDER["flow_id"],
        reason=REASON, manager_phone=ORDER["manager_phone"],
        customer_phone=ORDER["phone"],
        out_path=sms_png, battery=79, time=now,
    )
    print(f"已生成: {sms_png}")

    # 3. 材料4 情况说明
    p4 = os.path.join(SAMPLES, "材料4-终止白名单情况说明.docx")
    gen_termination_note(ORDER, REASON, p4)
    ok &= _verify_docx(p4, ["刘露露", "3201240001234567", "2026年07月07日",
                            "低压充电桩", "3226070700066527", "暂无用电需求"])

    # 4. 附件5 交底申请书
    p5 = os.path.join(SAMPLES, "附件5-交底申请书.docx")
    gen_jiaodi_apply(ORDER, street="永阳街道", distance_m="15",
                     jiaodi_date="2026年07月10日", out_path=p5, config=CONFIG)
    ok &= _verify_docx(p5, ["溧水区燃气有限公司", "永阳街道", "刘露露",
                            "2026年07月10日", "国网南京市溧水区供电公司"])

    # 5. 附件6 施工方案
    p6 = os.path.join(SAMPLES, "附件6-施工方案.docx")
    gen_construct_plan(ORDER, distance_m="15", out_path=p6, config=CONFIG)
    ok &= _verify_docx(p6, ["刘露露业扩", "15米", "80厘米", "王振东",
                            "17302549216", "李建国", "13805170000"])

    # 6. 附件7 情况说明
    p7 = os.path.join(SAMPLES, "附件7-情况说明.docx")
    gen_supervision_note(ORDER, p7)
    ok &= _verify_docx(p7, ["情况说明", "刘露露", "低压充电桩", "未设立监理", "建设方"])

    print("\n全部示例输出目录:", SAMPLES)
    print("总体校验:", "通过" if ok else "存在问题")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
