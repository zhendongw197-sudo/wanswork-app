#!/bin/bash
# 营销工单助手 Mac 启动器 —— 双击本文件即可启动
cd "$(dirname "$0")"
PYTHON="/Users/wangzhendong/Library/Application Support/kimi-desktop/daimon-share/daimon/runtime/python/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    # 内置 Python 不在时退回系统 python3
    PYTHON="$(command -v python3)"
fi
exec "$PYTHON" main.py
