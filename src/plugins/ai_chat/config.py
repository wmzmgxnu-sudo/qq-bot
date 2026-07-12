import os
from dotenv import load_dotenv

_loaded = False

def _reload_env() -> None:
    global _loaded
    load_dotenv(override=True)
    _loaded = True

def get_deepseek_api_key() -> str:
    if not _loaded:
        _reload_env()
    return os.getenv("DEEPSEEK_API_KEY", "")

def get_deepseek_base_url() -> str:
    if not _loaded:
        _reload_env()
    return os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1/chat/completions")

def get_deepseek_model() -> str:
    if not _loaded:
        _reload_env()
    return os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

def get_super_admin() -> str:
    if not _loaded:
        _reload_env()
    return os.getenv("SUPER_ADMIN", "")

def get_admin_ids() -> list:
    if not _loaded:
        _reload_env()
    admin_ids = os.getenv("ADMIN_IDS", "")
    admin_list = [uid.strip() for uid in admin_ids.split(",") if uid.strip()]
    super_admin = get_super_admin()
    if super_admin and super_admin not in admin_list:
        admin_list.append(super_admin)
    return admin_list

DEEPSEEK_API_KEY = get_deepseek_api_key()
DEEPSEEK_BASE_URL = get_deepseek_base_url()
DEEPSEEK_MODEL = get_deepseek_model()
SUPER_ADMIN = get_super_admin()
admin_list = get_admin_ids()

def load_system_prompt() -> str:
    if not _loaded:
        _reload_env()
    prompt_file = os.getenv("DEEPSEEK_SYSTEM_PROMPT_FILE")
    if prompt_file and os.path.exists(prompt_file):
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    env_prompt = os.getenv("DEEPSEEK_SYSTEM_PROMPT")
    if env_prompt:
        return env_prompt
    return "你是小助手，一个活泼可爱的女孩子，像朋友一样聊天，回答自然简短。"
