import sqlite3
import os

from langchain.agents import create_agent
from langgraph.checkpoint.sqlite import SqliteSaver
from dotenv import load_dotenv
from utils.path_tool import get_abs_path
from langchain.chat_models import init_chat_model
from tools.agent_tools import search_tool
from utils.sqlite_tool import init_db

init_db()

load_dotenv()

DB_PATH = get_abs_path("resource\\cook_chat.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

checkpoint = SqliteSaver(sqlite3.connect(DB_PATH, check_same_thread=False))

system_prompt = ""
with open(get_abs_path("agents\\system_prompt.txt"), 'r', encoding='utf-8') as f:
    system_prompt = f.read()


def get_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}

model = init_chat_model(
    model="qwen-max",
    base_url=os.getenv('BASE_URL'),
    api_key=os.getenv('DASHSCOPE_API_KEY'),
    model_provider='openai',
)

agent = create_agent(
    model=model,
    tools=[search_tool],
    system_prompt=system_prompt,
    checkpointer=checkpoint
)

if __name__ == '__main__':
    print(system_prompt)
