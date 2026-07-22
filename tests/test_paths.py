# -*- coding: utf-8 -*-
"""paths 路径配置模块测试。

用临时目录模拟 BASE_DIR，覆盖：
- 默认生成（配置文件不存在时回退默认 data/output）
- 相对/绝对/UNC 路径的 resolve 行为
- 损坏 json 容错
- save 后 load 往返一致
"""

import json
import os
import sys
import tempfile

# 保证可以 import app 包（项目根目录加入 sys.path）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.paths import DEFAULTS, PATHS_FILE, load_paths, resolve, save_paths


def test_resolve_relative():
    """相对路径拼到 base_dir 后返回绝对路径。"""
    base = tempfile.mkdtemp()
    assert resolve(base, 'data') == os.path.abspath(os.path.join(base, 'data'))
    assert resolve(base, 'sub/dir') == os.path.abspath(os.path.join(base, 'sub', 'dir'))


def test_resolve_absolute():
    """绝对路径（含盘符路径与 UNC）原样返回。"""
    base = tempfile.mkdtemp()
    # 当前平台的绝对路径
    abs_p = os.path.abspath(os.path.join(base, 'abs_dir'))
    assert resolve(base, abs_p) == abs_p
    # Windows 盘符路径（在非 Windows 平台上 isabs 为 False，但按约定原样返回
    # 不强制——此处只验证 UNC；盘符路径在 Windows 上由 isabs 覆盖）
    unc = '\\\\server\\share\\data'
    assert resolve(base, unc) == unc
    assert resolve(base, '\\\\fileserver\\营销部\\output') == '\\\\fileserver\\营销部\\output'


def test_load_defaults_when_missing():
    """配置文件不存在时回退默认 data/output 子目录。"""
    base = tempfile.mkdtemp()
    paths = load_paths(base)
    assert paths['data_dir'] == os.path.abspath(os.path.join(base, 'data'))
    assert paths['output_dir'] == os.path.abspath(os.path.join(base, 'output'))


def test_load_corrupted_json():
    """损坏的 json（非合法 JSON、非 dict、缺键）容错回退默认。"""
    base = tempfile.mkdtemp()
    cfg_path = os.path.join(base, PATHS_FILE)

    # 非合法 JSON
    with open(cfg_path, 'w', encoding='utf-8') as f:
        f.write('{not valid json')
    paths = load_paths(base)
    assert paths['data_dir'] == os.path.abspath(os.path.join(base, 'data'))
    assert paths['output_dir'] == os.path.abspath(os.path.join(base, 'output'))

    # 合法 JSON 但不是 dict
    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(['data', 'output'], f)
    paths = load_paths(base)
    assert paths['data_dir'] == os.path.abspath(os.path.join(base, 'data'))

    # 缺键：有的键用配置值，缺的键用默认值
    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump({'data_dir': 'mydata'}, f)
    paths = load_paths(base)
    assert paths['data_dir'] == os.path.abspath(os.path.join(base, 'mydata'))
    assert paths['output_dir'] == os.path.abspath(os.path.join(base, 'output'))


def test_load_resolves_mixed_paths():
    """读取时 resolve：相对拼 base_dir，绝对（含 UNC）原样。"""
    base = tempfile.mkdtemp()
    unc = '\\\\server\\share\\output'
    with open(os.path.join(base, PATHS_FILE), 'w', encoding='utf-8') as f:
        json.dump({'data_dir': 'data2', 'output_dir': unc}, f, ensure_ascii=False)
    paths = load_paths(base)
    assert paths['data_dir'] == os.path.abspath(os.path.join(base, 'data2'))
    assert paths['output_dir'] == unc


def test_save_load_roundtrip():
    """save 原样写入（不 resolve），load 往返一致。"""
    base = tempfile.mkdtemp()
    unc = '\\\\server\\share\\营销输出'
    save_paths(base, 'data', unc)

    # json 中原样保存用户输入（相对路径不被 resolve）
    with open(os.path.join(base, PATHS_FILE), 'r', encoding='utf-8') as f:
        raw = json.load(f)
    assert raw == {'data_dir': 'data', 'output_dir': unc}

    # load 返回 resolve 后的绝对路径
    paths = load_paths(base)
    assert paths['data_dir'] == os.path.abspath(os.path.join(base, 'data'))
    assert paths['output_dir'] == unc


def test_defaults_constant():
    """DEFAULTS 与 PATHS_FILE 常量符合约定。"""
    assert PATHS_FILE == 'paths.json'
    assert DEFAULTS == {'data_dir': 'data', 'output_dir': 'output'}


if __name__ == '__main__':
    # pytest 不可用时可直接 python tests/test_paths.py 运行
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
