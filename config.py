"""共享配置"""
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL"),
)
