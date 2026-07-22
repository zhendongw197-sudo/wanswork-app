# -*- coding: utf-8 -*-
"""路径配置模块：数据目录与输出目录的可配置化。

配置文件为 BASE_DIR 下的 paths.json（BASE_DIR 即 exe/main.py 所在目录）。
json 中原样保存用户输入（相对或绝对路径均可），读取时才 resolve 为绝对路径。
相对路径相对 BASE_DIR 解析；绝对路径（含 Windows UNC \\\\server\\share
与盘符路径）原样使用，便于内网环境指向服务器共享路径。
"""

import json
import os

PATHS_FILE = 'paths.json'

# 默认配置：数据/输出目录均相对 BASE_DIR
DEFAULTS = {
    'data_dir': 'data',
    'output_dir': 'output',
}


def resolve(base_dir: str, p: str) -> str:
    """把配置路径解析为绝对路径。

    p 为绝对路径（含 Windows UNC '\\\\server\\share' 与盘符路径）时原样返回；
    相对路径则拼到 base_dir 后返回绝对路径。
    """
    # os.path.isabs 之外，以 '\\' 开头的 UNC 路径也视为绝对，
    # 保证在 macOS/Linux 上处理 Windows 共享路径时不被误拼 base_dir。
    if os.path.isabs(p) or p.startswith('\\\\'):
        return p
    return os.path.abspath(os.path.join(base_dir, p))


def load_paths(base_dir: str) -> dict:
    """读取 base_dir/paths.json，返回解析后的绝对路径配置。

    配置文件不存在或损坏（非合法 JSON、缺键等）时回退到 DEFAULTS。
    返回 {'data_dir': 绝对路径, 'output_dir': 绝对路径}。
    """
    cfg = dict(DEFAULTS)
    path = os.path.join(base_dir, PATHS_FILE)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            for key in DEFAULTS:
                value = saved.get(key)
                if isinstance(value, str) and value.strip():
                    cfg[key] = value
    except (OSError, ValueError):
        # 文件不存在/不可读/JSON 损坏：使用默认配置
        pass
    return {key: resolve(base_dir, cfg[key]) for key in DEFAULTS}


def save_paths(base_dir: str, data_dir: str, output_dir: str) -> None:
    """把用户输入原样写入 base_dir/paths.json（不 resolve）。"""
    cfg = {'data_dir': data_dir, 'output_dir': output_dir}
    path = os.path.join(base_dir, PATHS_FILE)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
