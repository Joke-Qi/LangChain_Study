import os, uuid
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from fastapi.responses import StreamingResponse
import json

from utils.sqlite_tool import (
    create_conversation, list_conversations, get_conversation,
    touch_conversation, set_title_if_default, delete_conversation, init_db,
    add_message, list_messages,
)

from utils.oss_tool import upload_bytes

from agents.agents import agent, get_config
from langchain_core.messages import HumanMessage

app = FastAPI()
init_db()

# 允许前端直连调试（走 Vite 代理时这段不是必须的，但本地测试留着更保险）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/api/files", StaticFiles(directory=UPLOAD_DIR), name="files")

BASE_URL = "http://127.0.0.1:8000"


# 1. 新建对话
@app.post("/api/conversations")
def new_conversation():
    thread_id = str(uuid.uuid4())
    return create_conversation(thread_id)


# 2. 对话列表
@app.get("/api/conversations")
def get_list():
    return {"conversations": list_conversations()}


# 3. 对话详情（历史消息）—— 从 SQLite messages 表读取，而非 LangGraph state，
#    这样图片 URL 也能正常回显。
@app.get("/api/conversations/{thread_id}")
def get_detail(thread_id: str):
    conv = get_conversation(thread_id)
    if not conv:
        raise HTTPException(404, "conversation not found")

    messages = list_messages(thread_id)
    return {"thread_id": thread_id, "title": conv["title"], "messages": messages}


# 4. 发送消息

"""
流式调用
"""
@app.post("/api/chat/stream")
async def chat_stream(
        thread_id: str = Form(...),
        text: Optional[str] = Form(None),
        images: Optional[List[UploadFile]] = File(None),
):
    if not get_conversation(thread_id):
        raise HTTPException(404, "conversation not found")
    if not text and not images:
        raise HTTPException(400, "text and images cannot both be empty")

    # 1) 图片上传 OSS
    image_urls = []
    for img in images or []:
        ext = os.path.splitext(img.filename)[1] or ".jpg"
        data = await img.read()
        url = upload_bytes(data, ext=ext)
        image_urls.append(url)

    # 2) 保存用户消息
    add_message(thread_id, "user", text or "", image_urls)

    # 3) 组装多模态消息
    content_blocks = []
    if text:
        content_blocks.append({"type": "text", "text": text})
    for url in image_urls:
        content_blocks.append({"type": "image_url", "image_url": {"url": url}})
    human_message = HumanMessage(content=content_blocks if image_urls else (text or ""))

    # 4) 定义 SSE 同步生成器
    #    用同步 agent.stream()（而非 astream），因为 checkpointer 是同步的
    #    SqliteSaver，它不支持 async 方法。FastAPI 的 StreamingResponse 接受
    #    同步生成器，会自动在线程池里迭代，不会阻塞事件循环。
    def event_generator():
        reply_content = ""
        try:
            for chunk in agent.stream(
                    {"messages": [human_message]},
                    config=get_config(thread_id),
                    stream_mode="messages"
            ):
                # stream_mode="messages" 返回 (message_chunk, metadata) 元组
                msg_chunk, metadata = chunk

                # 过滤非文本（有时会吐出空内容或工具调用相关的特殊 chunk）
                content = msg_chunk.content
                if content:
                    reply_content += content
                    data = {"type": "token", "content": content}
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

            # 流正常结束，落库保存完整回复
            add_message(thread_id, "assistant", reply_content)
            set_title_if_default(thread_id, text or "图片消息")
            touch_conversation(thread_id)

            # 发送 done 事件
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            # 发生异常时，发送 error 事件给前端
            error_data = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

    # 5) 返回流式响应
    return StreamingResponse(event_generator(), media_type="text/event-stream")
"""
以下为非流式调用
"""
# @app.post("/api/chat")
# async def chat(
#     thread_id: str = Form(...),
#     text: Optional[str] = Form(None),
#     images: Optional[List[UploadFile]] = File(None),
# ):
#     if not get_conversation(thread_id):
#         raise HTTPException(404, "conversation not found")
#     if not text and not images:
#         raise HTTPException(400, "text and images cannot both be empty")
#
#     # 1) 上传图片到 OSS，拿到可访问 URL
#     image_urls = []
#     for img in images or []:
#         ext = os.path.splitext(img.filename)[1] or ".jpg"
#         data = await img.read()
#         url = upload_bytes(data, ext=ext)
#         image_urls.append(url)
#
#     # 2) 保存用户消息到 SQLite（供历史回显）
#     add_message(thread_id, "user", text or "", image_urls)
#
#     # 3) 组装多模态消息并调用 LangGraph agent
#     content_blocks = []
#     if text:
#         content_blocks.append({"type": "text", "text": text})
#     for url in image_urls:
#         content_blocks.append({"type": "image_url", "image_url": {"url": url}})
#     human_message = HumanMessage(content=content_blocks if image_urls else (text or ""))
#
#     try:
#         result = agent.invoke(
#             {"messages": [human_message]},
#             get_config(thread_id),
#         )
#         reply_content = result["messages"][-1].content
#         if not isinstance(reply_content, str):
#             reply_content = str(reply_content)
#     except Exception as e:
#         raise HTTPException(500, f"model invoke failed: {e}")
#
#     # 4) 保存回复、更新会话标题/时间
#     reply = add_message(thread_id, "assistant", reply_content)
#     set_title_if_default(thread_id, text or "图片消息")
#     touch_conversation(thread_id)
#
#     return {"thread_id": thread_id, "reply": reply}


# 5. 删除对话
@app.delete("/api/conversations/{thread_id}")
def del_conversation(thread_id: str):
    delete_conversation(thread_id)
    # 可选：agent.checkpointer.delete_thread(thread_id) 清理 checkpoint
    return {"success": True}
