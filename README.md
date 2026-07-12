# qq-bot (Private)

> 基于 **NoneBot 2 + OneBot V11 + NapCat** 的私人 QQ 机器人。
> 多模型 AI 对话 · 长期记忆 · 主动消息 · 图片理解 · Web 管理面板

![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![NoneBot](https://img.shields.io/badge/NoneBot-2.5%2B-green) ![License](https://img.shields.io/badge/License-Private-red) ![Visibility](https://img.shields.io/badge/Repo-Private-lightgrey)

---

## ✨ 特性

| 类别 | 能力 |
|---|---|
| 🤖 **AI 对话** | 兼容 OpenAI 协议的 Chat Completion 接口（DeepSeek、通义千问等），可扩展多模型路由 |
| 🧠 **长期记忆** | 按用户 / 群分开维护消息队列与历史摘要，定时（每 6 小时）自动总结，旧摘要自动归档 |
| 🔍 **联网搜索** | 基于 DuckDuckGo（`ddgs`）的实时搜索，命中关键词 `qs` / `搜索` 自动触发 |
| 🖼️ **图片理解** | 通义千问 `qwen-vl-plus` 多模态模型，自动识别 QQ 消息中的图片 |
| 💬 **主动消息** | 管理员开启 `sudo` 后，机器人每 40 分钟检查一次，超过 12 小时未聊天会以 **60% 概率**主动发起对话（22:00–08:00 静默） |
| 📊 **Web 管理面板** | `panel/app.py`，本地端口 `30080`，可查看 / 导出每个实体的记忆与对话记录 |
| 👮 **权限分级** | `SUPER_ADMIN` / `private_admins.json` / 群管理 / 普通用户，私聊指令隔离 |
| 📅 **定时任务** | 集成 `nonebot-plugin-apscheduler`，记忆维护 + 主动消息全自动 |

---

## 📂 目录结构

```
hello-world/
├── bot.py                       # NoneBot 启动入口
├── pyproject.toml               # 项目元数据 & 依赖 & NoneBot 配置
├── setup.bat                    # Windows 一键安装（venv + 依赖）
├── run.bat                      # Windows 一键启动（NapCat + Bot）
├── .env                         # 本地环境变量（API Key 等，未提交）
├── .env.prod                    # 生产环境变量样例
│
├── src/
│   └── plugins/
│       └── ai_chat/
│           ├── __init__.py      # 主插件：消息处理 / 调度器 / sudo 模式
│           ├── memory.py        # 记忆队列 / 摘要生成 / 持久化
│           └── config.py        # 从 .env 读取的配置 + 人设加载
│
├── panel/                       # FastAPI Web 管理面板
│   ├── app.py                   # 服务入口（端口 30080）
│   ├── run.bat                  # 启动脚本
│   ├── templates/               # Jinja2 模板
│   ├── static/                  # 前端资源
│   └── exports/                 # 导出的对话 JSON
│
├── prompts/
│   └── su_su_system.txt         # 人设提示词（苏苏）
│
├── memory/                      # 长期记忆（已提交）
│   ├── user_<qqid>/             # 每个私聊用户一个目录
│   │   ├── meta.json            # 统计信息
│   │   ├── summary_*.txt        # 历史摘要
│   │   └── summary_log_0.txt    # 当前滚动摘要
│   └── group_<groupid>/         # 每个群一个目录
│
├── data/
│   ├── bot.pid                  # Bot 进程 PID（运行期）
│   ├── napcat.pid               # NapCat 进程 PID（运行期）
│   ├── private_admins.json      # 私聊管理员名单
│   └── reminders.json           # 提醒事项
│
└── 项目初始化记录.md              # 历史开发笔记
```

---

## 🚀 快速开始

### 1. 环境要求

- **操作系统**：Windows 10/11（脚本为 `.bat`）
- **Python**：3.10 – 3.13
- **NapCat**：QQ 客户端协议实现（一个独立的 QQ 协议适配器，[下载](https://github.com/NapNeko/NapCatQQ)）

### 2. 安装

```powershell
# 克隆
git clone https://github.com/wmzmgxnu-sudo/qq-bot.git
cd qq-bot

# 一键安装（创建 .venv 并安装依赖）
setup.bat
```

### 3. 配置

复制 `.env.prod` 为 `.env`，填入你的密钥：

```ini
# .env（不要提交到 Git）
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1/chat/completions
DEEPSEEK_MODEL=deepseek-chat

DASHSCOPE_API_KEY=sk-xxx          # 通义千问，用于图片理解（可留空）

SUPER_ADMIN=你的QQ号                # 超级管理员（多个用英文逗号分隔）
NAPCAT_HOST=127.0.0.1
NAPCAT_PORT=6099
NAPCAT_TOKEN=                      # NapCat WebSocket Token
```

### 4. 启动

启动顺序：**NapCat → Bot**

```powershell
# 终端 A：先启 NapCat（QQ 协议适配）
#         配置反向 WS 到 ws://127.0.0.1:6099/onebot/v11/ws

# 终端 B：启动机器人
run.bat
```

启动成功后会看到：

```
[INFO] ai_chat | 私聊管理员列表：[...]
[INFO] ai_chat | DashScope（通义千问）客户端初始化成功
[INFO] nonebot | OneBot V11 | Bot xxx 已连接
```

打开浏览器访问 `http://127.0.0.1:30080` 进入管理面板。

---

## 🎮 指令速查

### 所有用户

| 指令 | 说明 |
|---|---|
| `@机器人 任意文字` | 群聊中 @ 触发对话 |
| 私聊任意文字 | 直接对话 |
| `insert 你想让我记住的话` | 手动写入记忆 |
| `sumup` | 立即为当前会话生成一次总结 |
| `forget` / `forget 5` / `forget 30m` / `forget all` | 清除记忆：默认 2 条 / 指定条数 / 指定分钟前 / 全部 |
| `qs 关键词` / `搜索 关键词` | 联网搜索后再回答 |
| 发送图片 | 自动识别并描述图片内容 |

### 群聊专属

| 指令 | 说明 |
|---|---|
| `@机器人 forget 5 @某人` | 群管清除某人的记忆（需 owner / admin） |

### 管理员（私聊）

| 指令 | 说明 |
|---|---|
| `sudo` | 开启"自动回复"，超过 12 小时未聊天机器人会主动找你聊 |
| `sudooff` | 关闭自动回复 |

### 超级管理员（私聊）

| 指令 | 说明 |
|---|---|
| `/add <QQ号>` | 添加私聊管理员 |
| `/remove <QQ号>` | 移除私聊管理员 |
| `/list` | 列出所有私聊管理员 |

---

## 🧠 记忆系统

每个实体（用户 = `user_<qqid>`，群 = `group_<groupid>`）独立维护：

```
对话流：
用户消息 ──▶ 内存队列 (deque, 上限 50) ──▶ AI 调用
                │
                └─▶ 定期触发：生成 summary ──▶ summary_N.txt
                                                │
                                                └─▶ 达到阈值后压缩、归档
```

- **写入**：每条消息进入队列，同时通过 `bump_stats` 更新统计
- **触发总结**：每 6 小时一次 cron（`memory_maintenance`）+ 启动时 + 退出时 + 主动 `sumup`
- **读取**：回复前取最近 5 条摘要 + 最近 10 条原始消息拼成 system prompt
- **修剪**：保留摘要数量上限，旧摘要合并/归档

详细算法见 [`src/plugins/ai_chat/memory.py`](src/plugins/ai_chat/memory.py)。

---

## 🔌 架构

```
┌─────────────────────────────────────────────────────────────┐
│                         QQ 用户                             │
└──────────────────────────────┬──────────────────────────────┘
                               │ 消息 / @Bot
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                      NapCat (QQ 协议层)                       │
│           反向 WS  ws://127.0.0.1:6099/onebot/v11/ws         │
└──────────────────────────────┬──────────────────────────────┘
                               │ OneBot V11 事件
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                   NoneBot 2  (bot.py)                        │
│                                                              │
│  ┌────────────────────────────────────────────────────┐      │
│  │ src/plugins/ai_chat/                               │      │
│  │  ├─ on_message 路由                                │      │
│  │  ├─ memory 队列 + 摘要                             │      │
│  │  ├─ DashScope (qwen-vl-plus) ── 图片理解           │      │
│  │  ├─ DDGS ── 联网搜索                              │      │
│  │  └─ apscheduler ── 记忆维护 + 主动消息             │      │
│  └────────────────────────────────────────────────────┘      │
│                                                              │
│  ┌────────────────────────────────────────────────────┐      │
│  │ panel/  FastAPI :30080                             │      │
│  │   ├─ /        浏览记忆                             │      │
│  │   ├─ /export/<id>  导出对话 JSON                  │      │
│  │   └─ /login   登录页                               │      │
│  └────────────────────────────────────────────────────┘      │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTPS
                               ▼
┌──────────────────────────────────────────────────────────────┐
│             DeepSeek / 通义千问 / 其他 OpenAI 兼容 API         │
└──────────────────────────────────────────────────────────────┘
```

---

## ⚙️ 关键依赖

| 包 | 版本 | 用途 |
|---|---|---|
| `nonebot2[fastapi]` | ≥2.5.0 | 机器人框架 |
| `nonebot-adapter-onebot` | ≥2.4.0 | OneBot V11 适配器 |
| `nonebot-plugin-apscheduler` | ≥0.5.0 | 定时任务 |
| `nonebot-plugin-quark` | ≥0.1.1 | 夸克网盘工具 |
| `dashscope` | latest | 通义千问 SDK（图片理解） |
| `ddgs` | latest | DuckDuckGo 搜索 |
| `python-dotenv` | latest | `.env` 加载 |

完整声明见 [`pyproject.toml`](pyproject.toml)。

---

## ⚠️ 安全与隐私

> **本仓库为 PRIVATE（私有仓库），但仍请注意：**

1. **`memory/` 目录包含真实聊天摘要**，已根据用户要求一并提交。如需删除本地记忆：
   - 私聊机器人发送 `forget all`
   - 或直接删除 `memory/<entity_id>/` 目录
2. **`.env` 文件不会提交**，但 `.env.prod` 样例中**不包含真实密钥**。请勿将真实密钥硬编码到任何已提交文件。
3. **`.venv/`、PID 文件**已通过 `.gitignore` 排除。
4. **NapCat WebSocket Token** 务必配置，否则本地局域网任何人都可接入你的机器人。
5. **管理面板 `panel/`** 默认绑定 `127.0.0.1`，**不要** 修改为 `0.0.0.0` 后暴露到公网（明文无鉴权）。

---

## 🛠️ 常见问题

<details>
<summary><b>NapCat 连不上 / 机器人收不到消息？</b></summary>

1. 确认 NapCat 已登录 QQ
2. 确认 NapCat 反向 WS 配置为 `ws://127.0.0.1:6099/onebot/v11/ws`（与 `.env` 中端口一致）
3. 看 NapCat 日志是否有 `connection established`
4. 看 `bot.py` 终端是否打印 `Bot xxx 已连接`

</details>

<details>
<summary><b>AI 回复 "脑袋有点晕"？</b></summary>

- `DEEPSEEK_API_KEY` 未配置或余额不足
- API 地址 `DEEPSEEK_BASE_URL` 配置错误
- 检查终端日志中 `AI 调用异常` 的具体错误

</details>

<details>
<summary><b>图片识别失败？</b></summary>

- 未配置 `DASHSCOPE_API_KEY`（功能默认关闭，不会报错，只是不识别）
- 图片格式不支持（推荐 jpg/png，< 10MB）

</details>

<details>
<summary><b>主动消息不触发？</b></summary>

- 你需要在私聊对机器人说 `sudo` 开启
- 时间窗口：每天 08:00 – 22:00，每 40 分钟检查一次
- 超过 12 小时未互动才会触发，且 60% 概率发送

</details>

<details>
<summary><b>如何重置整个记忆？</b></summary>

```powershell
# 关闭 Bot 后
rmdir /s /q memory
```

下次启动时 Bot 会自动重建空记忆。

</details>

---

## 📝 开发笔记

- 历史开发记录见 [`项目初始化记录.md`](项目初始化记录.md)
- 修改提示词：编辑 `prompts/su_su_system.txt`，重启 Bot 生效
- 新增插件：在 `src/plugins/<your_plugin>/__init__.py` 下用 `on_message` / `on_command` 装饰器即可

---

## 📄 License

Private / Unlicensed. 仅供个人使用，未经作者授权不得二次分发。

---

<sub>最后更新：2026-07-12</sub>