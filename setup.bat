@echo off
chcp 65001 >nul
echo ==========================================
echo 初始化项目环境
echo ==========================================

REM 检查 Python 是否可用
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+ 并加入 PATH。
    pause
    exit /b 1
)

REM 创建虚拟环境（如果不存在）
if not exist ".venv" (
    echo [1/5] 创建虚拟环境 .venv ...
    python -m venv .venv
) else (
    echo [1/5] 虚拟环境 .venv 已存在，跳过创建。
)

REM 激活虚拟环境并升级 pip
echo [2/5] 升级 pip ...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip

REM 安装项目依赖
echo [3/5] 安装项目依赖 ...
pip install -e .

REM 安装运行/开发常用工具
echo [4/5] 安装 nb-cli 及插件依赖 ...
pip install nb-cli dashscope ddgs nonebot-plugin-apscheduler python-dotenv

REM 创建快速启动脚本
echo [5/5] 生成启动脚本 run.bat ...
if not exist "run.bat" (
    echo @echo off > run.bat
    echo chcp 65001 ^>nul >> run.bat
    echo echo ========================================== >> run.bat
    echo echo 启动 NoneBot 项目 >> run.bat
    echo echo ========================================== >> run.bat
    echo. >> run.bat
    echo call .venv\Scripts\activate.bat >> run.bat
    echo nb run >> run.bat
)

echo.
echo ==========================================
echo 环境初始化完成
echo ==========================================
echo 启动方式：
echo   直接双击 run.bat
echo   或执行：nb run
echo.
pause
