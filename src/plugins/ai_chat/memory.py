import os
import json
import time
from collections import deque
from typing import Dict, List

# ========== 基础配置 ==========
BASE_MEMORY_DIR = r"E:\nat\QQbot\hello-world\memory"
_memory_queues: Dict[str, deque] = {}
MAX_QUEUE_LEN = 50  # 队列达到50条时触发自动总结

# ========== 总结文件轮转配置 ==========
SUMMARY_BASE_NAME = "summary_log"    # 文件名前缀
MAX_FILE_SIZE = 5 * 1024 * 1024      # 5MB

# ---------- 目录与元数据操作 ----------
def get_entity_dir(entity_id: str) -> str:
    path = os.path.join(BASE_MEMORY_DIR, entity_id)
    os.makedirs(path, exist_ok=True)
    return path

def get_meta_path(entity_id: str) -> str:
    return os.path.join(get_entity_dir(entity_id), "meta.json")

def load_meta(entity_id: str) -> dict:
    meta_path = get_meta_path(entity_id)
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {"summaries": [], "next_id": 1}

def save_meta(entity_id: str, meta: dict):
    with open(get_meta_path(entity_id), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

# ---------- 消息队列操作 ----------
def add_message(entity_id: str, role: str, content: str):
    if entity_id not in _memory_queues:
        _memory_queues[entity_id] = deque(maxlen=MAX_QUEUE_LEN)
    _memory_queues[entity_id].append({
        "role": role,
        "content": content,
        "timestamp": time.time()
    })

def get_recent_messages(entity_id: str, count: int = None) -> list:
    if entity_id not in _memory_queues:
        return []
    if count is None:
        count = len(_memory_queues[entity_id])
    return list(_memory_queues[entity_id])[-count:]

def clear_queue(entity_id: str):
    if entity_id in _memory_queues:
        _memory_queues[entity_id].clear()

def get_all_entity_ids() -> list:
    return list(_memory_queues.keys())

# ---------- 总结生成（带时间戳） ----------
async def generate_summary(entity_id: str, messages: list, api_func) -> str:
    current_time = time.strftime('%Y-%m-%d %H:%M:%S')
    prompt = f"当前时间：{current_time}\n请将以下对话历史总结为文字，但不要太过简短，一次大概150~300字，概括主要内容和关键信息，并在总结的开头注明当前时间（格式：YYYY-MM-DD HH:MM:SS）：\n"
    for msg in messages:
        prompt += f"{msg['role']}: {msg['content']}\n"
    summary = await api_func([{"role": "user", "content": prompt}])
    return summary

# ---------- 总结文件轮转辅助函数 ----------
def get_current_summary_file(entity_id: str) -> str:
    """获取实体当前可写入的总结文件路径，若大小超限则创建新文件"""
    dir_path = get_entity_dir(entity_id)
    existing = [f for f in os.listdir(dir_path) if f.startswith(SUMMARY_BASE_NAME) and f.endswith('.txt')]
    if existing:
        def get_num(name):
            try:
                return int(name.replace(SUMMARY_BASE_NAME, '').replace('.txt', ''))
            except:
                return -1
        existing.sort(key=get_num)
        latest = existing[-1]
        latest_path = os.path.join(dir_path, latest)
        if os.path.getsize(latest_path) < MAX_FILE_SIZE:
            return latest_path

    # 需要创建新文件
    max_num = 0
    for f in existing:
        try:
            num = int(f.replace(SUMMARY_BASE_NAME, '').replace('.txt', ''))
            if num >= max_num:
                max_num = num + 1
        except:
            continue
    new_name = f"{SUMMARY_BASE_NAME}_{max_num}.txt"
    new_path = os.path.join(dir_path, new_name)
    with open(new_path, 'w', encoding='utf-8') as f:
        pass
    return new_path

def append_summary_to_file(entity_id: str, summary_text: str) -> dict:
    """追加总结到当前文件，返回 {'file': filename, 'offset': int, 'length': int}"""
    file_path = get_current_summary_file(entity_id)
    filename = os.path.basename(file_path)
    offset = os.path.getsize(file_path) if os.path.exists(file_path) else 0
    content = f"---SUMMARY_START---\n{summary_text}\n---SUMMARY_END---\n"
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(content)
    length = len(content.encode('utf-8'))  # 字节长度
    return {"file": filename, "offset": offset, "length": length}

# ---------- 创建总结（自动/强制） ----------
async def create_summary(entity_id: str, api_func) -> bool:
    if entity_id not in _memory_queues or len(_memory_queues[entity_id]) < MAX_QUEUE_LEN:
        return False
    messages = list(_memory_queues[entity_id])
    summary_text = await generate_summary(entity_id, messages, api_func)

    meta = load_meta(entity_id)
    summary_id = meta["next_id"]
    meta["next_id"] += 1

    file_info = append_summary_to_file(entity_id, summary_text)

    meta["summaries"].append({
        "id": summary_id,
        "timestamp": time.time(),
        "file": file_info["file"],
        "offset": file_info["offset"],
        "length": file_info["length"],
        "importance": 1.0,
        "access_count": 0
    })
    save_meta(entity_id, meta)
    clear_queue(entity_id)
    return True

async def force_create_summary(entity_id: str, api_func) -> bool:
    if entity_id not in _memory_queues or len(_memory_queues[entity_id]) == 0:
        return False
    messages = list(_memory_queues[entity_id])
    summary_text = await generate_summary(entity_id, messages, api_func)

    meta = load_meta(entity_id)
    summary_id = meta["next_id"]
    meta["next_id"] += 1

    file_info = append_summary_to_file(entity_id, summary_text)

    meta["summaries"].append({
        "id": summary_id,
        "timestamp": time.time(),
        "file": file_info["file"],
        "offset": file_info["offset"],
        "length": file_info["length"],
        "importance": 1.0,
        "access_count": 0
    })
    save_meta(entity_id, meta)
    clear_queue(entity_id)
    return True

# ---------- 实时统计（用于管理面板） ----------
def bump_stats(entity_id: str, user_chars: int, assistant_chars: int):
    """每次对话后累加消息数和字符数，供 panel 读取"""
    meta = load_meta(entity_id)
    stats = meta.get("stats") or {
        "messages": 0,
        "chars": 0,
        "last_time": None,
        "by_day": {},
    }
    stats["messages"] = stats.get("messages", 0) + 1
    stats["chars"] = stats.get("chars", 0) + int(user_chars) + int(assistant_chars)
    stats["last_time"] = time.time()
    stats["assistant_chars"] = stats.get("assistant_chars", 0) + int(assistant_chars)

    day_key = time.strftime("%Y-%m-%d")
    by_day = stats.get("by_day") or {}
    day = by_day.get(day_key) or {"messages": 0, "chars": 0}
    day["messages"] += 1
    day["chars"] += int(user_chars) + int(assistant_chars)
    day["assistant_chars"] = day.get("assistant_chars", 0) + int(assistant_chars)
    by_day[day_key] = day
    # 保留最近 60 天的数据
    if len(by_day) > 60:
        for k in sorted(by_day.keys())[:-60]:
            by_day.pop(k, None)
    stats["by_day"] = by_day

    # 同时记录按小时段（panel chart 1天/3天细分用）
    hour_key = time.strftime("%Y-%m-%d %H:00")
    by_hour = stats.get("by_hour") or {}
    hour = by_hour.get(hour_key) or {"messages": 0, "chars": 0}
    hour["messages"] += 1
    hour["chars"] += int(user_chars) + int(assistant_chars)
    hour["assistant_chars"] = hour.get("assistant_chars", 0) + int(assistant_chars)
    by_hour[hour_key] = hour
    # 保留最近 60*24=1440 个小时段（约 60 天）
    if len(by_hour) > 1440:
        for k in sorted(by_hour.keys())[:-1440]:
            by_hour.pop(k, None)
    stats["by_hour"] = by_hour

    meta["stats"] = stats
    save_meta(entity_id, meta)

# ============================
# 修复重点：get_recent_summaries
# ============================
def get_recent_summaries(entity_id: str, count: int = 5) -> List[str]:
    """
    获取最近的总结内容，修复了 UnicodeDecodeError 和字节/字符读取错位问题。
    采用二进制模式读取，并使用 errors='ignore' 容错解码。
    """
    meta = load_meta(entity_id)
    summaries = meta["summaries"]
    sorted_summaries = sorted(summaries, key=lambda x: x["timestamp"], reverse=True)
    recent = sorted_summaries[:count]
    result = []
    for s in recent:
        file_path = os.path.join(get_entity_dir(entity_id), s["file"])
        if not os.path.exists(file_path):
            continue

        # 判断是否为新格式（包含 offset 和 length）
        if "offset" in s and "length" in s:
            try:
                # 使用二进制模式读取精确字节数，然后手动解码（容错）
                with open(file_path, 'rb') as f:
                    f.seek(s["offset"])
                    raw_bytes = f.read(s["length"])
                    # 尝试 UTF-8 解码，忽略非法字节
                    content = raw_bytes.decode('utf-8', errors='ignore')
                # 去除分隔符
                start_tag = "---SUMMARY_START---\n"
                end_tag = "\n---SUMMARY_END---\n"
                if content.startswith(start_tag) and content.endswith(end_tag):
                    content = content[len(start_tag):-len(end_tag)]
                result.append(content)
            except Exception as e:
                # 任何读取错误，记录日志并跳过该摘要
                print(f"读取摘要文件 {file_path} 失败: {e}")
                continue
        else:
            # 旧格式：整个文件就是总结内容，同样使用容错解码
            try:
                with open(file_path, 'rb') as f:
                    raw_bytes = f.read()
                    content = raw_bytes.decode('utf-8', errors='ignore')
                result.append(content)
            except Exception as e:
                print(f"读取旧格式摘要文件 {file_path} 失败: {e}")
                continue

        # 更新访问次数
        s["access_count"] = s.get("access_count", 0) + 1

    save_meta(entity_id, meta)
    return result

# ---------- 可选：清理损坏的摘要文件 ----------
def clean_corrupted_summaries(entity_id: str):
    """
    扫描并删除无法正常解码的摘要文件（谨慎使用）。
    调用前请确保备份重要数据。
    """
    meta = load_meta(entity_id)
    new_summaries = []
    for s in meta["summaries"]:
        file_path = os.path.join(get_entity_dir(entity_id), s["file"])
        if not os.path.exists(file_path):
            continue
        try:
            with open(file_path, 'rb') as f:
                f.read()  # 仅测试是否可读
            new_summaries.append(s)
        except Exception:
            print(f"删除损坏文件: {file_path}")
            os.remove(file_path)
    meta["summaries"] = new_summaries
    save_meta(entity_id, meta)

# ---------- 定时维护 ----------
async def periodic_maintenance(api_func):
    """每6小时执行：自动总结 + 修剪"""
    entity_ids = get_all_entity_ids()
    for eid in entity_ids:
        if len(_memory_queues.get(eid, [])) >= MAX_QUEUE_LEN:
            await create_summary(eid, api_func)
        # prune_summaries(eid)   # 注意：原代码中此函数未定义，如需使用请自行实现