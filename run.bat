@echo off
chcp 65001 >nul
echo ==========================================
echo 启动 NoneBot 项目
echo ==========================================

REM 优先使用项目内已安装的 nb 启动
call .venv\Scripts\activate.bat
nb run
