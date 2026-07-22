@echo off
rem ============================================================
rem  营销工单助手 - 一键重新打包脚本
rem  双击运行即可：安装 PyInstaller -> 打包单文件 exe
rem  产物：dist\营销工单助手.exe
rem ============================================================
cd /d "%~dp0"

echo [1/2] 安装 / 确认 PyInstaller ...
python -m pip install pyinstaller
if errorlevel 1 (
    echo.
    echo [失败] PyInstaller 安装失败，请检查网络或 Python 环境。
    pause
    exit /b 1
)

echo.
echo [2/2] 开始打包（单文件、无控制台窗口）...
python -m PyInstaller --noconfirm --clean --onefile --windowed --name 营销工单助手 --add-data "assets;assets" main.py
if errorlevel 1 (
    echo.
    echo [失败] 打包过程出错，请查看上方日志。
    pause
    exit /b 1
)

echo.
echo [完成] 打包成功：dist\营销工单助手.exe
echo 提示：把 exe 拷到固定目录使用，data\ 与 output\ 会自动建在 exe 旁边。
pause
