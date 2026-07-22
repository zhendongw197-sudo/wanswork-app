# -*- coding: utf-8 -*-
"""营销工单助手入口。"""
import os
import sys
import tkinter as tk

from app import paths as paths_mod
from app.gui import MainWindow
from app.store import Store

# 数据/输出目录定位：打包（PyInstaller 冻结）时取 exe 所在目录，
# 源码运行时取脚本所在目录，避免把数据写进 exe 内部临时目录。
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据/输出目录可在 BASE_DIR/paths.json 中配置（相对或绝对路径均可），
# 未配置或配置损坏时使用默认的 data/ 与 output/ 子目录。
paths = paths_mod.load_paths(BASE_DIR)

root = tk.Tk()
store = Store(paths['data_dir'])
MainWindow(root, store, paths['output_dir'])
root.mainloop()
