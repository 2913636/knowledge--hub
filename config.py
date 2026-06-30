"""共享配置"""
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

DEEPSEEK_KEY = os.getenv("DEEPSEEK_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

if not DEEPSEEK_KEY:
    raise ValueError(
        "DEEPSEEK_KEY 未设置。请复制 .env.example 为 .env 并填入你的 API Key。\n"
        "获取 Key: https://platform.deepseek.com/api_keys"
    )

client = OpenAI(api_key=DEEPSEEK_KEY, base_url=DEEPSEEK_BASE_URL)
