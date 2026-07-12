from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import os
import sys
import json
import secrets
import asyncio
import subprocess
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

app = FastAPI(title="Bot Management Panel")

# ========== Config ==========
PANEL_USERNAME = "seahorse"
PANEL_PASSWORD = "123456"

# Paths
BASE_DIR = Path(__file__).parent.parent.resolve()
ENV_FILE = BASE_DIR / ".env"
MEMORY_DIR = BASE_DIR / "memory"
DATA_DIR = BASE_DIR / "data"
PRIVATE_ADMIN_FILE = DATA_DIR / "private_admins.json"
PROMPTS_DIR = BASE_DIR / "prompts" / "su_su_system.txt"

# Load .env
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

# Load config from env
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1/chat/completions")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
SUPER_ADMIN = os.getenv("SUPER_ADMIN", "")
ADMIN_IDS = os.getenv("ADMIN_IDS", "")
admin_list = [uid.strip() for uid in ADMIN_IDS.split(",") if uid.strip()]
if SUPER_ADMIN and SUPER_ADMIN not in admin_list:
    admin_list.append(SUPER_ADMIN)

# Load system prompt
def load_system_prompt() -> str:
    if PROMPTS_DIR.exists():
        try:
            return PROMPTS_DIR.read_text(encoding="utf-8")
        except Exception:
            pass
    env_prompt = os.getenv("DEEPSEEK_SYSTEM_PROMPT", "")
    if env_prompt:
        return env_prompt
    return "你是小助手，一个活泼可爱的女孩子，像朋友一样聊天，回答自然简短。"

# Load private admins
def load_private_admins() -> list:
    if PRIVATE_ADMIN_FILE.exists():
        try:
            return json.loads(PRIVATE_ADMIN_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_private_admins(admins: list):
    DATA_DIR.mkdir(exist_ok=True)
    PRIVATE_ADMIN_FILE.write_text(json.dumps(admins, ensure_ascii=False, indent=2), encoding="utf-8")

private_admin_list = load_private_admins()

# Sessions
sessions = {}

def get_session(request: Request) -> Optional[dict]:
    session_id = request.cookies.get("session_id")
    if session_id and session_id in sessions:
        if sessions[session_id]["expires"] > datetime.now().timestamp():
            return sessions[session_id]
        else:
            del sessions[session_id]
    return None

def create_session() -> dict:
    session_id = secrets.token_hex(32)
    sessions[session_id] = {"expires": datetime.now().timestamp() + 86400}
    return {"session_id": session_id}

def require_auth(request: Request):
    session = get_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return session

# Templates & Static
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

# ========== Service Management (NoneBot + NapCat) ==========
# 通过端口监听探测状态：NoneBot=30081，NapCat=10086
# 同时使用 PID 文件做精确控制
NONE_BOT_PORT = 30081
NAPCAT_PORT = 10086  # NapCat 是 WS 客户端，不监听此端口，仅作旧字段占位
NONE_BOT_SCRIPT = BASE_DIR / "run.bat"
NONE_BOT_VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
NONE_BOT_ENTRY = BASE_DIR / "bot.py"
NAPCAT_DIR = Path(r"E:\nat\NapCat.44498.Shell")
NAPCAT_BAT = NAPCAT_DIR / "napcat.quick.bat"

BOT_PID_FILE = DATA_DIR / "bot.pid"
NAPCAT_PID_FILE = DATA_DIR / "napcat.pid"


def _port_listening(port: int) -> bool:
    """检测 TCP 端口是否正在监听"""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False


def _pid_alive(pid: int) -> bool:
    """Windows 下用 tasklist 检查 PID 是否存活"""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=3, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return str(pid) in result.stdout
    except Exception:
        return False


def _save_pid(pid_file: Path, pid: int):
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(pid), encoding="utf-8")


def _read_pid(pid_file: Path) -> Optional[int]:
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _clear_pid(pid_file: Path):
    try:
        pid_file.unlink(missing_ok=True)
    except Exception:
        pass


def _kill_pid(pid: int, force: bool = False):
    """优雅结束进程，10 秒后还没死就强杀"""
    import time
    try:
        flag = "/T" if not force else "/F /T"
        subprocess.run(
            ["taskkill", flag, "/PID", str(pid)],
            capture_output=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass
    # 等优雅退出
    for _ in range(20):
        time.sleep(0.5)
        if not _pid_alive(pid):
            return True
    # 强杀
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass
    return False


def _start_window_napcat(bat_path: Path, cwd: Path) -> Optional[int]:
    """直接启动 NapCatWinBootMain.exe 到新控制台窗口，返回 QQ/NapCat 主进程 PID"""
    if sys.platform != "win32":
        return None
    CREATE_NEW_CONSOLE = 0x00000010
    # bat 内容：chcp + 运行 NapCatWinBootMain.exe <QQ号>，绕过 pause 让面板能拿到真实 PID
    exe_path = cwd / "NapCatWinBootMain.exe"
    if not exe_path.exists():
        print(f"[NapCat 启动失败] 找不到 {exe_path}", flush=True)
        return None
    qq_account = "3014553661"
    try:
        proc = subprocess.Popen(
            [str(exe_path), qq_account],
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NEW_CONSOLE,
            close_fds=True,
        )
        return proc.pid
    except Exception as e:
        print(f"[NapCat 启动失败] {e}", flush=True)
        return None


def _start_window_python(python_exe: Path, script: Path, cwd: Path) -> Optional[int]:
    """启动 python 脚本到新控制台窗口"""
    if sys.platform != "win32":
        return None
    CREATE_NEW_CONSOLE = 0x00000010
    try:
        proc = subprocess.Popen(
            [str(python_exe), str(script)],
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NEW_CONSOLE,
            close_fds=True,
        )
        return proc.pid
    except Exception as e:
        print(f"[NoneBot 启动失败] {e}", flush=True)
        return None


def get_nonebot_status() -> dict:
    port_ok = _port_listening(NONE_BOT_PORT)
    pid = _read_pid(BOT_PID_FILE)
    pid_alive = pid is not None and _pid_alive(pid)
    # NoneBot 通过端口 30081 判断（HTTP 服务）
    running = port_ok
    if port_ok and not pid_alive and pid is not None:
        _clear_pid(BOT_PID_FILE)
    return {"running": running, "port_open": port_ok, "pid": pid}


def get_napcat_status() -> dict:
    # NapCat 是 WebSocket 客户端，不监听端口，所以只看 PID/进程
    pid = _read_pid(NAPCAT_PID_FILE)
    pid_alive = pid is not None and _pid_alive(pid)
    # 兜底：用 tasklist 看是否有 NapCatWinBootMain.exe 在跑（防止面板/手动启动后 PID 没记）
    proc_alive = False
    try:
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq NapCatWinBootMain.exe", "/NH"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=3, creationflags=0x08000000,
        )
        proc_alive = "NapCatWinBootMain.exe" in r.stdout
    except Exception:
        pass
    running = pid_alive or proc_alive
    if (not running) and pid is not None:
        _clear_pid(NAPCAT_PID_FILE)
    return {"running": running, "port_open": False, "pid": pid if pid_alive else None}


def is_bot_running() -> bool:
    """保留旧接口（其它地方仍引用），现在以 NoneBot 30081 端口为准"""
    return get_nonebot_status()["running"]


def start_nonebot() -> dict:
    """启动 NoneBot（在 BASE_DIR 中开新窗口跑 .venv python bot.py）"""
    status = get_nonebot_status()
    if status["running"]:
        return {"success": False, "message": "NoneBot 已经在运行"}
    # 清理 pid 文件残留
    _clear_pid(BOT_PID_FILE)
    # 在 Windows 上启动 .venv\Scripts\python.exe bot.py（新窗口）
    pid = _start_window_python(NONE_BOT_VENV_PYTHON, NONE_BOT_ENTRY, BASE_DIR)
    if pid is None:
        return {"success": False, "message": "无法启动 NoneBot 进程"}
    _save_pid(BOT_PID_FILE, pid)
    return {"success": True, "message": f"NoneBot 启动中 (PID {pid})", "pid": pid}


def stop_nonebot() -> dict:
    status = get_nonebot_status()
    if not status["running"]:
        # 兜底：即使没记录 PID，按端口查找占用进程并结束
        # 这里保持简单，先按 pid 文件
        _clear_pid(BOT_PID_FILE)
        return {"success": False, "message": "NoneBot 未运行"}
    pid = status["pid"]
    _kill_pid(pid, force=False)
    _clear_pid(BOT_PID_FILE)
    return {"success": True, "message": f"NoneBot 停止信号已发送 (PID {pid})"}


def start_napcat() -> dict:
    if not NAPCAT_BAT.exists():
        return {"success": False, "message": f"找不到 {NAPCAT_BAT}"}
    status = get_napcat_status()
    if status["running"]:
        return {"success": False, "message": "NapCat 已经在运行"}
    _clear_pid(NAPCAT_PID_FILE)
    # 用 start 启动 bat，它会创建新控制台窗口，完全独立
    pid = _start_window_napcat(NAPCAT_BAT, NAPCAT_DIR)
    if pid is None:
        return {"success": False, "message": "无法启动 NapCat"}
    _save_pid(NAPCAT_PID_FILE, pid)
    return {"success": True, "message": f"NapCat 启动中 (PID {pid})", "pid": pid}


def stop_napcat() -> dict:
    status = get_napcat_status()
    if not status["running"]:
        _clear_pid(NAPCAT_PID_FILE)
        return {"success": False, "message": "NapCat 未运行"}
    pid = status["pid"]
    _kill_pid(pid, force=False)
    _clear_pid(NAPCAT_PID_FILE)
    return {"success": True, "message": f"NapCat 停止信号已发送 (PID {pid})"}

# ========== Memory Helpers ==========
def _read_entity_messages(entity_dir: Path) -> list:
    """从 meta.json 的 summaries 中提取消息内容（从 summary_log 文件读取）"""
    messages = []
    meta_file = entity_dir / "meta.json"
    if not meta_file.exists():
        return messages

    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception:
        return messages

    seen_content = set()
    for s in meta.get("summaries", []):
        fname = s.get("file")
        offset = s.get("offset")
        length = s.get("length")
        if not fname:
            continue
        fpath = entity_dir / fname
        if not fpath.exists():
            continue
        try:
            text = fpath.read_text(encoding="utf-8")
            if offset is not None and length is not None:
                text = text[offset:offset + length]
            # 去掉 ---SUMMARY_START--- 等标记
            for line in text.splitlines():
                line = line.strip()
                if line and line not in seen_content:
                    seen_content.add(line)
        except Exception:
            pass

    return messages

def _get_entity_stats(entity_dir: Path) -> dict:
    """获取一个实体的统计信息"""
    msg_count = 0
    summary_count = 0
    total_chars = 0
    assistant_chars = 0
    last_time = None

    meta_file = entity_dir / "meta.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            summary_count = len(meta.get("summaries", []))

            # 优先读实时统计字段（NoneBot 端 bump_stats 写入）
            stats = meta.get("stats")
            if stats:
                msg_count = stats.get("messages", 0)
                total_chars = stats.get("chars", 0)
                assistant_chars = stats.get("assistant_chars", 0)
                lt = stats.get("last_time")
                if lt:
                    try:
                        last_time = datetime.fromtimestamp(lt)
                    except Exception:
                        pass
            else:
                # 回退到旧逻辑：从 summary 文件中估算
                for s in meta.get("summaries", []):
                    ts = s.get("timestamp")
                    if ts:
                        try:
                            t = datetime.fromtimestamp(ts)
                            if last_time is None or t > last_time:
                                last_time = t
                        except Exception:
                            pass

                    fname = s.get("file")
                    if fname:
                        fpath = entity_dir / fname
                        if fpath.exists():
                            try:
                                text = fpath.read_text(encoding="utf-8")
                                if s.get("offset") is not None and s.get("length") is not None:
                                    text = text[s["offset"]:s["offset"] + s["length"]]
                                import re
                                matches = re.findall(r'---SUMMARY_START---', text)
                                msg_count += len(matches)
                                total_chars += len(text)
                            except Exception:
                                pass
        except Exception:
            pass

    return {
        "messages": msg_count,
        "summaries": summary_count,
        "chars": total_chars,
        "assistant_chars": assistant_chars,
        "last_time": last_time.isoformat() if last_time else None,
    }

# ========== Routes ==========

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    session = get_session(request)
    templates_dir = Path(__file__).parent / "templates"
    if not session:
        login_html = templates_dir / "login.html"
        return HTMLResponse(content=login_html.read_text(encoding="utf-8"))
    index_html = templates_dir / "index.html"
    return HTMLResponse(content=index_html.read_text(encoding="utf-8"))

@app.post("/api/login")
async def login(request: Request):
    data = await request.json()
    if data.get("username") == PANEL_USERNAME and data.get("password") == PANEL_PASSWORD:
        session = create_session()
        response = JSONResponse({"success": True, "message": "Login successful"})
        response.set_cookie(key="session_id", value=session["session_id"], httponly=True, max_age=86400)
        return response
    return JSONResponse({"success": False, "message": "Invalid credentials"}, status_code=401)

@app.post("/api/logout")
async def logout(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id and session_id in sessions:
        del sessions[session_id]
    response = JSONResponse({"success": True})
    response.delete_cookie("session_id")
    return response

@app.get("/api/bot/status")
async def get_bot_status(request: Request):
    require_auth(request)
    nb = get_nonebot_status()
    nc = get_napcat_status()
    return JSONResponse({
        "success": True,
        "data": {
            "status": "running" if nb["running"] else "stopped",
            "version": "0.1.0",
            "nonebot": nb,
            "napcat": nc,
        }
    })


@app.post("/api/bot/start")
async def bot_start(request: Request):
    require_auth(request)
    result = start_nonebot()
    return JSONResponse(result)


@app.post("/api/bot/stop")
async def bot_stop(request: Request):
    require_auth(request)
    result = stop_nonebot()
    return JSONResponse(result)


@app.post("/api/napcat/start")
async def napcat_start(request: Request):
    require_auth(request)
    result = start_napcat()
    return JSONResponse(result)


@app.post("/api/napcat/stop")
async def napcat_stop(request: Request):
    require_auth(request)
    result = stop_napcat()
    return JSONResponse(result)


@app.get("/api/services")
async def get_services(request: Request):
    """统一返回 NoneBot 和 NapCat 状态"""
    require_auth(request)
    return JSONResponse({
        "success": True,
        "data": {
            "nonebot": get_nonebot_status(),
            "napcat": get_napcat_status(),
        }
    })

@app.get("/api/dashboard")
async def get_dashboard(request: Request):
    require_auth(request)

    user_count = 0
    group_count = 0
    total_messages = 0
    total_summaries = 0
    total_chars = 0
    total_reply_chars = 0

    if MEMORY_DIR.exists():
        for entity_dir in MEMORY_DIR.iterdir():
            if entity_dir.is_dir():
                if entity_dir.name.startswith("user_"):
                    user_count += 1
                elif entity_dir.name.startswith("group_"):
                    group_count += 1

                stats = _get_entity_stats(entity_dir)
                total_messages += stats["messages"]
                total_summaries += stats["summaries"]
                total_chars += stats["chars"]
                total_reply_chars += stats["assistant_chars"]

    return JSONResponse({
        "success": True,
        "data": {
            "entities": {
                "total": user_count + group_count,
                "users": user_count,
                "groups": group_count,
            },
            "messages": total_messages,
            "summaries": total_summaries,
            "chars": total_chars,
            "reply_chars": total_reply_chars,
            "admins": {
                "total": len(admin_list),
                "private": len(private_admin_list),
            },
            "features": {
                "sudo": {"name": "Sudo 自动回复", "description": "管理员开启后，bot 会主动找你聊天", "enabled": True},
                "search": {"name": "联网搜索", "description": "使用 qs/搜索 命令进行网络搜索", "enabled": True},
                "image_analysis": {"name": "图片理解", "description": "发送图片时自动识别内容", "enabled": bool(os.getenv("DASHSCOPE_API_KEY"))},
                "memory": {"name": "记忆系统", "description": "自动记住对话并生成总结", "enabled": True},
            },
            "bot_status": "running" if is_bot_running() else "stopped",
            "version": "0.1.0",
        }
    })

@app.get("/api/chart")
async def get_chart(request: Request, days: int = 7):
    require_auth(request)
    days = max(1, min(14, days))

    # 段长度（小时）：1天=每小时, 3天=12小时, 7天/14天=每天
    if days == 1:
        bucket_hours = 1
    elif days <= 3:
        bucket_hours = 12
    else:
        bucket_hours = 24

    now = datetime.now()
    total_hours = days * 24
    bucket_count = total_hours // bucket_hours
    # 把 now 对齐到当前 bucket 末端
    if bucket_hours >= 24:
        aligned_now = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    else:
        cur_hour = (now.hour // bucket_hours + 1) * bucket_hours
        aligned_now = now.replace(hour=cur_hour % 24, minute=0, second=0, microsecond=0)
        if cur_hour >= 24:
            aligned_now += timedelta(days=1)

    bucket_start = aligned_now - timedelta(hours=bucket_hours * bucket_count)

    def _bucket_label(idx: int) -> str:
        ts = bucket_start + timedelta(hours=bucket_hours * idx)
        if bucket_hours >= 24:
            return ts.strftime("%m-%d")
        return ts.strftime("%m-%d %H:00")

    labels = [_bucket_label(i) for i in range(bucket_count)]
    message_counts = [0] * bucket_count
    char_counts = [0] * bucket_count
    assistant_char_counts = [0] * bucket_count
    reply_counts = [0] * bucket_count

    if MEMORY_DIR.exists():
        for entity_dir in MEMORY_DIR.iterdir():
            if not entity_dir.is_dir():
                continue
            meta_file = entity_dir / "meta.json"
            if not meta_file.exists():
                continue
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                stats = meta.get("stats")
                if stats and stats.get("by_hour"):
                    for hour_key, d in stats["by_hour"].items():
                        try:
                            t = datetime.strptime(hour_key, "%Y-%m-%d %H:00")
                        except Exception:
                            continue
                        idx = int((t - bucket_start).total_seconds() // (bucket_hours * 3600))
                        if idx < 0 or idx >= bucket_count:
                            continue
                        message_counts[idx] += d.get("messages", 0)
                        char_counts[idx] += d.get("chars", 0)
                        assistant_char_counts[idx] += d.get("assistant_chars", 0)
                        reply_counts[idx] += d.get("messages", 0)
                elif stats and stats.get("by_day"):
                    for day_key, d in stats["by_day"].items():
                        try:
                            day_dt = datetime.strptime(day_key, "%Y-%m-%d")
                        except Exception:
                            continue
                        idx = int((day_dt - bucket_start.date()).total_seconds() // (bucket_hours * 3600))
                        if idx < 0 or idx >= bucket_count:
                            continue
                        message_counts[idx] += d.get("messages", 0)
                        char_counts[idx] += d.get("chars", 0)
                        assistant_char_counts[idx] += d.get("assistant_chars", 0)
                        reply_counts[idx] += d.get("messages", 0)
                else:
                    for s in meta.get("summaries", []):
                        ts = s.get("timestamp")
                        if not ts:
                            continue
                        try:
                            t = datetime.fromtimestamp(ts)
                        except Exception:
                            continue
                        idx = int((t - bucket_start).total_seconds() // (bucket_hours * 3600))
                        if idx < 0 or idx >= bucket_count:
                            continue
                        fname = s.get("file")
                        if fname:
                            fpath = entity_dir / fname
                            if fpath.exists():
                                try:
                                    text = fpath.read_text(encoding="utf-8")
                                    if s.get("offset") is not None and s.get("length") is not None:
                                        text = text[s["offset"]:s["offset"] + s["length"]]
                                    char_counts[idx] += len(text)
                                    import re
                                    message_counts[idx] += len(re.findall(r'---SUMMARY_START---', text))
                                except Exception:
                                    pass
            except Exception:
                pass

    return JSONResponse({
        "success": True,
        "data": {
            "labels": labels,
            "message_counts": message_counts,
            "char_counts": char_counts,
            "assistant_char_counts": assistant_char_counts,
            "reply_counts": reply_counts,
            "bucket_hours": bucket_hours,
        }
    })

@app.get("/api/config")
async def get_config(request: Request):
    require_auth(request)
    prompt = load_system_prompt()
    return JSONResponse({
        "success": True,
        "data": {
            "api_key": DEEPSEEK_API_KEY[:8] + "..." if DEEPSEEK_API_KEY else "",
            "api_url": DEEPSEEK_BASE_URL,
            "model": DEEPSEEK_MODEL,
            "system_prompt": prompt,
            "system_prompt_preview": prompt[:200] + "..." if len(prompt) > 200 else prompt,
        }
    })

@app.post("/api/config")
async def update_config(request: Request):
    require_auth(request)
    data = await request.json()

    env_lines = []
    if ENV_FILE.exists():
        env_lines = ENV_FILE.read_text(encoding="utf-8").splitlines()

    def update_env(key, value):
        nonlocal env_lines
        found = False
        new_lines = []
        for line in env_lines:
            if line.strip().startswith(f"{key}="):
                new_lines.append(f"{key}={value}")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"{key}={value}")
        return new_lines

    updates = []
    if data.get("api_key"):
        env_lines = update_env("DEEPSEEK_API_KEY", data["api_key"])
        updates.append("API Key")
    if data.get("api_url"):
        env_lines = update_env("DEEPSEEK_BASE_URL", data["api_url"])
        updates.append("API URL")
    if data.get("model"):
        env_lines = update_env("DEEPSEEK_MODEL", data["model"])
        updates.append("Model")
    if "system_prompt" in data and data["system_prompt"] is not None:
        PROMPTS_DIR.parent.mkdir(exist_ok=True)
        PROMPTS_DIR.write_text(data["system_prompt"], encoding="utf-8")
        env_lines = update_env("DEEPSEEK_SYSTEM_PROMPT_FILE", "prompts/su_su_system.txt")
        updates.append("System Prompt")

    ENV_FILE.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    return JSONResponse({
        "success": True,
        "message": f"Configuration updated: {', '.join(updates)}. Restart bot to apply changes.",
        "updated_fields": updates,
    })

@app.get("/api/admins")
async def get_admins(request: Request):
    require_auth(request)
    return JSONResponse({
        "success": True,
        "data": {
            "super_admin": SUPER_ADMIN,
            "admins": admin_list,
            "private_admins": private_admin_list,
        }
    })

@app.post("/api/admins")
async def add_admin(request: Request):
    require_auth(request)
    data = await request.json()
    admin_id = data.get("admin_id", "").strip()
    if not admin_id.isdigit():
        return JSONResponse({"success": False, "message": "Invalid admin ID"}, status_code=400)
    if admin_id in private_admin_list:
        return JSONResponse({"success": False, "message": "Admin already exists"}, status_code=400)
    private_admin_list.append(admin_id)
    save_private_admins(private_admin_list)
    return JSONResponse({"success": True, "message": f"Admin {admin_id} added successfully"})

@app.delete("/api/admins/{admin_id}")
async def remove_admin(request: Request, admin_id: str):
    require_auth(request)
    if admin_id not in private_admin_list:
        return JSONResponse({"success": False, "message": "Admin not found"}, status_code=404)
    private_admin_list.remove(admin_id)
    save_private_admins(private_admin_list)
    return JSONResponse({"success": True, "message": f"Admin {admin_id} removed successfully"})

@app.get("/api/memory")
async def get_memory_list(request: Request, type: Optional[str] = None):
    require_auth(request)
    entities = []
    if MEMORY_DIR.exists():
        for entity_dir in MEMORY_DIR.iterdir():
            if not entity_dir.is_dir():
                continue
            eid = entity_dir.name
            entity_type = "user" if eid.startswith("user_") else "group"

            if type and entity_type != type:
                continue

            entity_id_num = eid.replace("user_", "").replace("group_", "")
            stats = _get_entity_stats(entity_dir)

            entities.append({
                "id": eid,
                "type": entity_type,
                "number": entity_id_num,
                "messages": stats["messages"],
                "summaries": stats["summaries"],
                "last_time": stats["last_time"],
            })
    return JSONResponse({"success": True, "data": entities})

@app.get("/api/memory/{entity_id}")
async def get_memory_detail(request: Request, entity_id: str):
    """返回所有历史 summary 供 modal 展示（按 index 编号）"""
    require_auth(request)
    entity_dir = MEMORY_DIR / entity_id
    if not entity_dir.exists():
        return JSONResponse({"success": False, "message": "Entity not found"}, status_code=404)

    summaries = []  # 每个元素: {index, timestamp, length, content}
    meta_file = entity_dir / "meta.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            for idx, s in enumerate(meta.get("summaries", [])):
                fname = s.get("file")
                content = ""
                if fname:
                    fpath = entity_dir / fname
                    if fpath.exists():
                        try:
                            text = fpath.read_text(encoding="utf-8")
                            offset = s.get("offset")
                            length = s.get("length")
                            if offset is not None and length is not None:
                                text = text[offset:offset + length]
                            # 去掉标记行，只保留总结内容
                            lines = []
                            for line in text.splitlines():
                                stripped = line.strip()
                                if stripped in ("---SUMMARY_START---", "---SUMMARY_END---", ""):
                                    continue
                                lines.append(line)
                            content = "\n".join(lines).strip()
                        except Exception:
                            content = ""
                summaries.append({
                    "index": idx + 1,
                    "timestamp": s.get("timestamp"),
                    "length": s.get("length", 0),
                    "content": content,
                })
        except Exception:
            pass

    return JSONResponse({
        "success": True,
        "data": {
            "id": entity_id,
            "summaries": summaries,  # 全部，不截断
        }
    })

@app.get("/api/memory/{entity_id}/export")
async def export_memory(request: Request, entity_id: str):
    require_auth(request)
    entity_dir = MEMORY_DIR / entity_id
    if not entity_dir.exists():
        return JSONResponse({"success": False, "message": "Entity not found"}, status_code=404)

    entity_type = "用户" if entity_id.startswith("user_") else "群组"
    entity_num = entity_id.replace("user_", "").replace("group_", "")

    lines = []
    lines.append(f"{'='*60}")
    lines.append(f"记忆导出 - {entity_type} {entity_num}")
    lines.append(f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"{'='*60}")
    lines.append("")

    meta_file = entity_dir / "meta.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if meta.get("summaries"):
                lines.append("【历史总结】")
                lines.append("-" * 40)
                for s in meta.get("summaries", []):
                    fname = s.get("file")
                    if not fname:
                        continue
                    fpath = entity_dir / fname
                    if not fpath.exists():
                        continue
                    try:
                        text = fpath.read_text(encoding="utf-8")
                        offset = s.get("offset")
                        length = s.get("length")
                        if offset is not None and length is not None:
                            text = text[offset:offset + length]
                        ts = s.get("timestamp")
                        if ts:
                            try:
                                ts_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                                lines.append(f"[{ts_str}]")
                            except Exception:
                                pass
                        for line in text.splitlines():
                            stripped = line.strip()
                            if stripped in ("---SUMMARY_START---", "---SUMMARY_END---", ""):
                                continue
                            lines.append(line)
                        lines.append("")
                    except Exception:
                        pass
        except Exception:
            pass

    lines.append("")
    lines.append(f"{'='*60}")
    lines.append("记忆路径：" + str(entity_dir))
    lines.append(f"{'='*60}")

    export_dir = Path(__file__).parent / "exports"
    export_dir.mkdir(exist_ok=True)
    filename = f"{entity_id}_memory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    export_path = export_dir / filename
    export_path.write_text("\n".join(lines), encoding="utf-8")

    return FileResponse(
        str(export_path),
        media_type="text/plain; charset=utf-8",
        filename=filename,
    )

@app.get("/api/features")
async def get_features(request: Request):
    require_auth(request)
    return JSONResponse({
        "success": True,
        "data": {
            "sudo": {"name": "Sudo 自动回复", "description": "管理员开启后，bot 会主动找你聊天", "enabled": True},
            "search": {"name": "联网搜索", "description": "使用 qs/搜索 命令进行网络搜索", "enabled": True},
            "image_analysis": {"name": "图片理解", "description": "发送图片时自动识别内容", "enabled": bool(os.getenv("DASHSCOPE_API_KEY"))},
            "memory": {"name": "记忆系统", "description": "自动记住对话并生成总结", "enabled": True},
            "reminders": {"name": "提醒功能", "description": "定时提醒功能", "enabled": False},
        }
    })

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=30080)
