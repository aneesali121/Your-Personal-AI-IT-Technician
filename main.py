import base64
import os
from pathlib import Path

from anthropic import AsyncAnthropic
from dotenv import load_dotenv  # optional convenience; see requirements
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import tools
from prompts import SYSTEM_PROMPT

load_dotenv()

BASE_DIR = Path(__file__).parent
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}

client = AsyncAnthropic()  # reads ANTHROPIC_API_KEY from the environment

app = FastAPI(title="Your Personal AI IT Technician")
db.init()
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class NewConversation(BaseModel):
    title: str | None = None


class PasswordInput(BaseModel):
    password: str


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


# ---------- Conversations ----------

@app.get("/api/conversations")
def list_conversations():
    return db.list_conversations()


@app.post("/api/conversations")
def create_conversation(body: NewConversation | None = None):
    title = (body.title or "").strip() if body else ""
    return db.create_conversation(title or "New session")


@app.get("/api/conversations/{cid}")
def get_conversation(cid: str):
    conv = db.get_conversation(cid)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    conv["messages"] = db.get_messages(cid)
    return conv


@app.delete("/api/conversations/{cid}")
def delete_conversation(cid: str):
    if not db.get_conversation(cid):
        raise HTTPException(404, "Conversation not found")
    db.delete_conversation(cid)
    return {"ok": True}


# ---------- Chat ----------

@app.post("/api/chat")
async def chat(
    conversation_id: str = Form(...),
    message: str = Form(""),
    image: UploadFile | None = File(None),
):
    if not db.get_conversation(conversation_id):
        raise HTTPException(404, "Conversation not found")

    message = message.strip()
    image_block = None
    if image and image.filename:
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(400, "Unsupported image type. Use PNG, JPEG, WEBP, or GIF.")
        data = await image.read()
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(400, "Image is larger than 5 MB.")
        image_block = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image.content_type,
                "data": base64.standard_b64encode(data).decode("ascii"),
            },
        }

    if not message and not image_block:
        raise HTTPException(400, "Send a message or attach a screenshot.")

    stored_text = f"[Screenshot attached] {message}".strip() if image_block else message
    prompt_text = message or "Please analyze the attached screenshot and help me troubleshoot the issue it shows."

    history = db.get_messages(conversation_id)
    api_messages = [{"role": m["role"], "content": m["content"]} for m in history]
    user_content = ([image_block] if image_block else []) + [{"type": "text", "text": prompt_text}]
    api_messages.append({"role": "user", "content": user_content})
    is_first_turn = len(history) == 0

    async def generate():
        parts: list[str] = []
        try:
            async with client.messages.stream(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=api_messages,
            ) as stream:
                async for text in stream.text_stream:
                    parts.append(text)
                    yield text
        except Exception as exc:  # surface a readable error in the chat instead of a broken stream
            yield (
                f"\n\n**The AI service returned an error ({exc.__class__.__name__}).** "
                "Check that ANTHROPIC_API_KEY and CLAUDE_MODEL are set correctly, then try again."
            )
            return

        full_reply = "".join(parts)
        db.add_message(conversation_id, "user", stored_text)
        db.add_message(conversation_id, "assistant", full_reply)
        if is_first_turn:
            title = (message or "Screenshot analysis")[:60]
            db.set_title(conversation_id, title)

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


# ---------- IT utilities ----------

@app.get("/api/tools/ip")
async def tool_ip(host: str):
    try:
        return await tools.ip_info(host.strip())
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/tools/dns")
def tool_dns(name: str, type: str = "A"):
    try:
        return tools.dns_lookup(name.strip(), type)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/tools/http-status")
async def tool_http_status(url: str):
    try:
        return await tools.http_status(url.strip())
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/tools/port")
async def tool_port(host: str, port: int):
    try:
        return await tools.port_check(host.strip(), port)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/tools/password")
def tool_password(body: PasswordInput):
    # The password is used for this request only and is never stored or logged.
    if not body.password:
        raise HTTPException(400, "Enter a password to check.")
    return tools.password_strength(body.password)


@app.get("/api/tools/network-commands")
def tool_network_commands(host: str, os: str = "linux"):
    try:
        return tools.network_commands(os, host.strip())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
