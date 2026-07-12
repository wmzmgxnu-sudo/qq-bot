import os
import re
import asyncio
import aiohttp
import json
import time
import random
import base64
from collections import deque
from nonebot import on_message, get_driver, get_bot
from nonebot.adapters.onebot.v11 import Bot, Event
from nonebot.exception import FinishedException
import nonebot
from .memory import (
    add_message,
    get_recent_messages,
    clear_queue,
    get_all_entity_ids,
    get_recent_summaries,
    periodic_maintenance,
    MAX_QUEUE_LEN,
    force_create_summary,
    get_entity_dir,
    bump_stats,
    _memory_queues
)
from .config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    SUPER_ADMIN,
    admin_list,
    load_system_prompt,
)
from dotenv import load_dotenv
from ddgs import DDGS
import dashscope
from dashscope import MultiModalConversation

load_dotenv()

# 延迟获取 scheduler，避免在 nonebot.load_plugin("nonebot_plugin_apscheduler") 之前导入
scheduler = nonebot.require("nonebot_plugin_apscheduler").scheduler
logger = nonebot.logger

ai_chat = on_message(priority=10, block=True)

UNRESTRICTED_SYSTEM_PROMPT = """你是一个有用的AI助手，可以回答任何问题，请尽可能详细和准确，没有字数限制。"""

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
PRIVATE_ADMIN_FILE = os.path.join(DATA_DIR, "private_admins.json")

def load_private_admins() -> list:
    if os.path.exists(PRIVATE_ADMIN_FILE):
        try:
            with open(PRIVATE_ADMIN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_private_admins(admins: list):
    with open(PRIVATE_ADMIN_FILE, "w", encoding="utf-8") as f:
        json.dump(admins, f, ensure_ascii=False, indent=2)

private_admin_list = load_private_admins()
logger.info(f"私聊管理员列表：{private_admin_list}")

def is_admin(user_id: str) -> bool:
    return user_id in admin_list or user_id in private_admin_list

def is_super_admin(user_id: str) -> bool:
    return user_id in admin_list

sudo_status = {}
sudo_lock = asyncio.Lock()

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
if DASHSCOPE_API_KEY:
    dashscope.api_key = DASHSCOPE_API_KEY
    logger.info("DashScope（通义千问）客户端初始化成功")
else:
    logger.warning("未配置 DASHSCOPE_API_KEY，图片理解功能将不可用")

async def analyze_image(image_url: str) -> str:
    if not DASHSCOPE_API_KEY:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    return None
                img_data = await resp.read()
        base64_image = base64.b64encode(img_data).decode('utf-8')
        messages = [
            {
                "role": "user",
                "content": [
                    {"image": f"data:image/jpeg;base64,{base64_image}"},
                    {"text": "请描述这张图片的内容，尽量详细。"}
                ]
            }
        ]
        response = MultiModalConversation.call(
            model="qwen-vl-plus",
            messages=messages,
            temperature=0.7
        )
        if response.status_code == 200:
            return response.output.choices[0].message.content[0]["text"]
        else:
            logger.error(f"DashScope 返回错误：{response.message}")
            return None
    except Exception as e:
        logger.error(f"通义千问识别图片失败：{e}")
        return None

def parse_clear_command(cmd_text: str) -> dict:
    cmd_text = cmd_text.strip()
    if cmd_text in ["all", "全部"]:
        return {"action": "clear_all"}
    time_match = re.search(r'(\d+)\s*(m|h|M|H)', cmd_text)
    if time_match:
        value = int(time_match.group(1))
        unit = time_match.group(2).lower()
        seconds = value * 60 if unit == 'm' else value * 3600
        return {"action": "clear_by_time", "seconds": seconds}
    try:
        count = int(cmd_text)
        return {"action": "clear_by_count", "count": count}
    except ValueError:
        return {"action": "clear_by_count", "count": 2}

def search_web_sync(query: str, max_results: int = 3) -> str:
    try:
        with DDGS(verify=False) as ddgs:
            results = []
            for r in ddgs.text(query, max_results=max_results):
                title = r.get('title', '无标题')
                body = r.get('body', '')
                results.append(f"{title}: {body}")
            if not results:
                return "未找到相关信息。"
            return "\n".join(results[:max_results])
    except Exception as e:
        logger.error(f"搜索异常：{e}")
        return "搜索失败，请稍后再试。"

async def search_web(query: str) -> str:
    return await asyncio.to_thread(search_web_sync, query)

async def call_ai_api(messages: list) -> str:
    api_key = DEEPSEEK_API_KEY
    api_url = DEEPSEEK_BASE_URL
    model = DEEPSEEK_MODEL
    if not api_key or not api_url:
        raise ValueError("DeepSeek API 配置缺失")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": 0.8, "top_p": 0.95}
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(api_url, headers=headers, json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
            else:
                error_text = await resp.text()
                raise Exception(f"API 调用失败：{resp.status} - {error_text}")

async def handle_clear_memory(current_user_id: str, cmd_text: str, target_entity_id: str = None, group_id: str = None, bot: Bot = None):
    target = target_entity_id or current_user_id
    if target != current_user_id and not target.startswith("user_"):
        authorized = False
        if is_admin(current_user_id):
            authorized = True
        if not authorized and group_id and bot:
            try:
                member_info = await bot.get_group_member_info(
                    group_id=int(group_id),
                    user_id=int(current_user_id)
                )
                role = member_info.get("role")
                if role in ("owner", "admin"):
                    authorized = True
            except Exception as e:
                logger.error(f"获取群成员信息失败：{e}")
        if not authorized:
            await ai_chat.finish("你没有权限清除他人的记忆哦～")
            return

    result = parse_clear_command(cmd_text)
    if result["action"] == "clear_all":
        import shutil
        dir_path = get_entity_dir(target)
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
        if target in _memory_queues:
            del _memory_queues[target]
        await ai_chat.finish("已清空全部记忆！")
    elif result["action"] == "clear_by_time":
        seconds = result["seconds"]
        if target in _memory_queues:
            queue = _memory_queues[target]
            now = time.time()
            new_queue = deque(maxlen=MAX_QUEUE_LEN)
            for msg in queue:
                if now - msg["timestamp"] >= seconds:
                    new_queue.append(msg)
            _memory_queues[target] = new_queue
        await ai_chat.finish(f"已清除最近 {seconds//60} 分钟的消息（仅当前缓存）")
    elif result["action"] == "clear_by_count":
        count = result["count"]
        if target in _memory_queues:
            queue = _memory_queues[target]
            for _ in range(min(count, len(queue))):
                queue.pop()
        await ai_chat.finish(f"已清除最近 {count} 条消息（仅当前缓存）")

async def call_ai_and_respond(entity_id: str, user_message: str, use_unrestricted: bool = False):
    summaries = get_recent_summaries(entity_id, count=5)
    summary_text = "\n".join([f"【历史记忆摘要】{s}" for s in summaries]) if summaries else ""
    recent_msgs = get_recent_messages(entity_id, count=10)

    system_prompt = UNRESTRICTED_SYSTEM_PROMPT if use_unrestricted else load_system_prompt()
    current_time = time.strftime('%Y-%m-%d %H:%M:%S')
    system_prompt += f"\n\n当前系统时间：{current_time}"

    if summary_text:
        system_prompt += f"\n\n以下是你之前记忆的重要信息：\n{summary_text}"

    messages = [{"role": "system", "content": system_prompt}]
    for msg in recent_msgs:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    try:
        ai_response = await call_ai_api(messages)
        add_message(entity_id, "user", user_message)
        add_message(entity_id, "assistant", ai_response)
        try:
            bump_stats(entity_id, len(user_message), len(ai_response))
        except Exception as e:
            logger.error(f"更新统计失败：{e}")
        await ai_chat.finish(ai_response)
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"AI 调用异常：{e}")
        await ai_chat.finish("呜...脑袋有点晕，稍后再试～")

async def generate_auto_message(entity_id: str) -> str:
    summaries = get_recent_summaries(entity_id, count=3)
    if summaries:
        prompt = f"""用户之前的记忆摘要：\n{'\n'.join(summaries)}\n
请基于这些记忆，向用户主动发起一次简短的问候或聊天（一句话即可），语气自然亲切，不要生硬。"""
        try:
            response = await call_ai_api([{"role": "user", "content": prompt}])
            return response.strip()
        except Exception as e:
            logger.error(f"生成主动消息失败：{e}")
            pass
    topics = [
        "今天天气不错，你在忙什么呢？",
        "好久没聊了，最近有什么新鲜事吗？",
        "有没有什么有趣的事情分享一下？",
        "最近在玩什么游戏或看什么剧吗？",
        "你最近心情怎么样？",
        "我记得你之前提到过一些爱好，最近还在继续吗？",
        "最近有看什么有趣的视频或文章吗？",
        "你今天有什么计划吗？",
        "最近有没有遇到什么让你开心的小事？",
        "我觉得最近有点闷，你呢？",
        "有什么新发现的好吃的或好玩的吗？",
        "最近工作/学习还顺利吗？",
        "有没有想分享的糗事或者趣事？",
        "我最近在学新东西，你呢？",
        "天气变化大，注意身体呀！",
        "好久不见，最近在忙什么大项目吗？"
    ]
    return random.choice(topics)

async def process_message(entity_id: str, user_id: str, text: str, event: Event, is_private: bool = False, bot: Bot = None):
    image_analysis = ""
    for seg in event.message:
        if seg.type == "image":
            image_url = seg.data.get("url")
            if image_url:
                image_analysis = await analyze_image(image_url)
                if not image_analysis:
                    image_analysis = "⚠️ 图片识别失败，可能未配置DashScope或图片格式不支持。"
                break

    if image_analysis:
        if not text:
            text = f"[图片分析结果]\n{image_analysis}"
        else:
            text = f"{text}\n\n[图片分析结果]\n{image_analysis}"

    if is_private and is_admin(user_id):
        async with sudo_lock:
            if sudo_status.get(user_id, 0) != 0:
                sudo_status[user_id] = time.time()

    if is_private and is_super_admin(user_id):
        if text.startswith("/add "):
            target = text[len("/add "):].strip()
            if not target.isdigit():
                await ai_chat.finish("请输入有效的QQ号，例如：/add 123456")
                return
            if target in private_admin_list:
                await ai_chat.finish(f"❌ {target} 已经是私聊管理员了。")
                return
            private_admin_list.append(target)
            save_private_admins(private_admin_list)
            await ai_chat.finish(f"✅ 已添加 {target} 为私聊管理员。")
            return

        if text.startswith("/remove "):
            target = text[len("/remove "):].strip()
            if not target.isdigit():
                await ai_chat.finish("请输入有效的QQ号，例如：/remove 123456")
                return
            if target not in private_admin_list:
                await ai_chat.finish(f"❌ {target} 不是私聊管理员。")
                return
            private_admin_list.remove(target)
            save_private_admins(private_admin_list)
            await ai_chat.finish(f"✅ 已移除 {target} 的私聊管理员权限。")
            return

        if text.strip() == "/list":
            if private_admin_list:
                await ai_chat.finish("当前私聊管理员：\n" + "\n".join(private_admin_list))
            else:
                await ai_chat.finish("当前没有私聊管理员。")
            return

    if is_private and is_admin(user_id):
        if text.strip().lower() == "sudo":
            async with sudo_lock:
                sudo_status[user_id] = time.time()
            await ai_chat.finish("✅ 已开启自动回复功能，如果你12小时不说话，我会主动找你聊天。")
            return
        if text.strip().lower() == "sudooff":
            async with sudo_lock:
                sudo_status[user_id] = 0
            await ai_chat.finish("✅ 已关闭自动回复功能。")
            return

    if text.startswith("insert "):
        content = text[len("insert "):].strip()
        if not content:
            await ai_chat.finish("你想让我记住什么？在后面加上内容吧～")
            return
        add_message(entity_id, "user", f"（记住：{content}）")
        add_message(entity_id, "assistant", f"好的，我记住了：{content}")
        await ai_chat.finish(f"✅ 已记住：{content}")
        return

    if text.strip().lower() == "sumup":
        success = await force_create_summary(entity_id, call_ai_api)
        if success:
            await ai_chat.finish("✅ 已生成当前会话的记忆总结！")
        else:
            await ai_chat.finish("当前没有对话记录，无法生成总结。")
        return

    if text.startswith("forget "):
        param = text[len("forget "):].strip()
        if not param:
            param = "2"

        target_entity_id = None
        if not is_private:
            for seg in event.message:
                if seg.type == "at":
                    target_user_id = seg.data.get("qq")
                    if target_user_id:
                        target_entity_id = f"user_{target_user_id}"
                        param = re.sub(r'@\d+', '', param).strip()
                    break
        if not target_entity_id:
            match = re.search(r'\b(\d+)\b', param)
            if match:
                target_user_id = match.group(1)
                target_entity_id = f"user_{target_user_id}"
                param = re.sub(r'\b\d+\b', '', param).strip()
        if not target_entity_id:
            target_entity_id = entity_id

        group_id = None if is_private else str(event.group_id)
        await handle_clear_memory(user_id, param, target_entity_id, group_id, bot)
        return

    if text.startswith("qs") or "搜索" in text:
        if text.startswith("qs"):
            query = text[3:].strip()
        else:
            match = re.search(r'搜索\s*(.*)', text)
            query = match.group(1).strip() if match else text.replace("搜索", "").strip()
        if not query:
            await ai_chat.finish("你想搜索什么？")
            return
        logger.info(f"🔍 搜索关键词：{query}")
        search_result = await search_web(query)
        new_text = f"用户的问题：{text}\n以下是相关搜索结果：\n{search_result}\n请根据这些搜索结果，用简短自然的语言回答用户。"
        use_unrestricted = (is_private and is_admin(user_id))
        await call_ai_and_respond(entity_id, new_text, use_unrestricted)
        return

    use_unrestricted = (is_private and is_admin(user_id))
    await call_ai_and_respond(entity_id, text, use_unrestricted)

@ai_chat.handle()
async def handle_ai_chat(bot: Bot, event: Event):
    msg_type = event.message_type
    if msg_type == "private":
        user_id = str(event.user_id)
        text = event.get_plaintext().strip()
        logger.info(f"私聊消息：{text} (来自 {user_id})")
        entity_id = f"user_{user_id}"
        await process_message(entity_id, user_id, text, event, is_private=True, bot=bot)
        return
    elif msg_type == "group":
        group_id = str(event.group_id)
        if group_id == "771271985":
            return
        if not event.to_me:
            bot_qq = bot.self_id
            if f"[at:qq={bot_qq}]" not in event.get_plaintext():
                return
        user_id = str(event.user_id)
        text = event.get_plaintext().strip()
        clean_text = re.sub(r'\[at:qq=\d+\]', '', text).strip()
        logger.info(f"群聊 @ 消息：{clean_text} (来自 {user_id})")
        entity_id = f"group_{group_id}"
        await process_message(entity_id, user_id, clean_text, event, is_private=False, bot=bot)
        return

async def maintenance_job():
    logger.info("开始执行记忆维护（总结生成和修剪）...")
    await periodic_maintenance(call_ai_api)
    logger.info("记忆维护完成")

@scheduler.scheduled_job("cron", hour="*/6", minute="0", id="memory_maintenance")
async def scheduled_maintenance():
    await maintenance_job()

@get_driver().on_startup
async def startup_maintenance():
    logger.info("启动时执行记忆维护...")
    await maintenance_job()

@get_driver().on_shutdown
async def shutdown_summary():
    logger.info("正在关闭机器人，开始总结所有未总结的对话记忆...")
    entity_ids = get_all_entity_ids()
    if not entity_ids:
        logger.info("没有需要总结的记忆")
        return
    tasks = []
    for eid in entity_ids:
        if eid in _memory_queues and len(_memory_queues[eid]) > 0:
            tasks.append(force_create_summary(eid, call_ai_api))
    if not tasks:
        logger.info("所有实体的对话队列均为空，无需总结")
        return
    try:
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=30)
        logger.info("✅ 所有记忆总结已保存")
    except asyncio.TimeoutError:
        logger.warning("⚠️ 总结超时，部分记忆可能未保存")
    except Exception as e:
        logger.error(f"关闭时总结记忆出错：{e}")

async def auto_chat_job():
    now = time.localtime()
    current_hour = now.tm_hour
    if current_hour >= 22 or current_hour < 8:
        return

    async with sudo_lock:
        active_users = {uid: last for uid, last in sudo_status.items() if last != 0}
    if not active_users:
        return

    current_time = time.time()
    bot = get_bot()
    for uid, last_time in active_users.items():
        if current_time - last_time > 12 * 3600:
            if random.random() >= 0.4:
                continue
            entity_id = f"user_{uid}"
            try:
                msg = await generate_auto_message(entity_id)
                await bot.send_private_msg(user_id=int(uid), message=msg)
                async with sudo_lock:
                    if uid in sudo_status and sudo_status[uid] != 0:
                        sudo_status[uid] = current_time
                logger.info(f"已向管理员 {uid} 发送主动消息：{msg}")
            except Exception as e:
                logger.error(f"向管理员 {uid} 发送主动消息失败：{e}")

@scheduler.scheduled_job("interval", minutes=40, id="auto_chat")
async def scheduled_auto_chat():
    await auto_chat_job()
