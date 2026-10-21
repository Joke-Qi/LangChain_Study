from langchain.tools import tool
from langchain_tavily import TavilySearch
from dotenv import load_dotenv

load_dotenv()

tavily_tool = TavilySearch(
    max_results=5,
    topic="general",
)

@tool(description="使用联网搜索，输入关键词，返回搜索结果")
def search_tool(query: str) -> str:
    return tavily_tool.invoke(query)
