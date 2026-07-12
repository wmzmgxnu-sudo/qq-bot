# hello-world (Private)

基于 NoneBot 2 + OneBot V11 + NapCat 的私人 QQ 机器人。

## 功能
- AI 对话（DeepSeek / 通义千问多模型路由）
- 自动记忆总结（基于对话队列定时生成）
- 管理面板（`panel/app.py`，端口 30080）

## 启动
1. 复制 `.env` 并填入 API Key
2. `setup.bat` 装依赖
3. `run.bat` 启动 NapCat + Bot

## 目录
- `src/plugins/ai_chat/` — AI 聊天与记忆核心
- `panel/` — Web 管理面板
- `memory/` — 各实体（用户/群）的持久化记忆
- `prompts/` — 人设提示词

## 注意
本仓库为私有。`.env`、`.venv/`、PID 文件不会提交，但 `memory/` 中含真实聊天记录，已根据用户要求一并提交。