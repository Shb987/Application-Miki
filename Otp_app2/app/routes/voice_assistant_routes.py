import os
import asyncio
from datetime import datetime, timezone
from bson import ObjectId
from openai import AsyncOpenAI
from app.core.database import db
from app.core.settings import settings
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from app.services.ai_tutor_service import ai_tutor_service
import logging
import json

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice-assistant")

# OpenAI client initialization
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# MongoDB collection
history_collection = db.voice_assistant_history

async def save_chat_event(student_id: str, session_id: str, role: str, content: str):
    """Utility to save a chat event to MongoDB."""
    if not content or not content.strip():
        return
        
    try:
        await history_collection.insert_one({
            "student_id": student_id,
            "session_id": session_id,
            "role": role,
            "content": content.strip(),
            "timestamp": datetime.now(timezone.utc)
        })
    except Exception as e:
        logger.error(f"Error saving {role} event to MongoDB: {e}")



async def handle_realtime_voice(websocket: WebSocket, student_id: str, session_id: str, student_data: dict):

    student_name = student_data.get("student_name", "Student")
    student_class = str(student_data.get("student_class", "general"))
    instructions = ai_tutor_service.get_persona_instructions(student_name, student_class)

    # 🔥 TURN STATE MACHINE
    state = "listening"  # listening | thinking | speaking | interrupted
    assistant_speaking = False

    try:
        async with client.beta.realtime.connect(
            model="gpt-4o-mini-realtime-preview"
        ) as session:

            await session.session.update(
                session={
                    "instructions": instructions,
                    "modalities": ["audio", "text"],
                    "input_audio_transcription": {"model": "whisper-1"},
                    "temperature": 0.6,
                    "max_response_output_tokens": 400,  # 🔥 COST CONTROL
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 700
                    },
                    "tools": [
                        {
                            "type": "function",
                            "name": "search_textbook",
                            "description": "Search textbook for academic info.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string"}
                                },
                                "required": ["query"]
                            }
                        },
                        {
                            "type": "function",
                            "name": "search_web",
                            "description": "Search web for live info.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string"}
                                },
                                "required": ["query"]
                            }
                        }
                    ],
                    "tool_choice": "auto"
                }
            )

            session_ready = asyncio.Event()

            # =========================================
            # 🔥 RECEIVE LOOP (USER INPUT)
            # =========================================
            async def receive_messages():
                nonlocal state, assistant_speaking

                await session_ready.wait()
                print(f"✅ Voice Assistant session active for Student: {student_id}", flush=True)

                while True:
                    msg = await websocket.receive()

                    if msg["type"] == "websocket.disconnect":
                        break

                    # =============================
                    # 🎙 AUDIO INPUT
                    # =============================
                    if msg.get("bytes"):
                        audio_chunk = msg["bytes"]
                        import base64
                        base64_audio = base64.b64encode(audio_chunk).decode("utf-8")

                        # 🔥 BARGE-IN HANDLING
                        if assistant_speaking:
                            print("⚡ Barge-in detected: Interrupting Assistant.", flush=True)
                            await session.response.cancel()
                            assistant_speaking = False
                            state = "interrupted"

                        await session.input_audio_buffer.append(audio=base64_audio)
                        state = "listening"

                    # =============================
                    # 🛑 END OF SPEECH SIGNAL
                    # =============================
                    elif msg.get("text") == "__END_OF_SPEECH__":
                        # Client should send this after silence detection
                        await session.input_audio_buffer.commit()
                        await session.response.create()
                        state = "thinking"

                    # =============================
                    # 📝 TEXT INPUT
                    # =============================
                    elif "text" in msg:
                        text_raw = msg["text"]
                        print(f"DEBUG: Raw WebSocket text received: {text_raw}", flush=True)
                        text_content = text_raw
                        try:
                            # If it's a JSON string, extract the 'text' or 'message' field
                            data = json.loads(text_raw)
                            if isinstance(data, dict):
                                text_content = data.get("text", data.get("message", text_raw))
                        except Exception as e:
                            print(f"DEBUG: JSON parse failed: {e}", flush=True)

                        print(f"👤 User (Text): {text_content}", flush=True)
                        await save_chat_event(student_id, session_id, "user", text_content)

                        await session.conversation.item.create(
                            item={
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": text_content}],
                            }
                        )

                        await session.response.create()
                        state = "thinking"

            # =========================================
            # 🔥 SEND LOOP (MODEL EVENTS)
            # =========================================
            async def send_events():
                nonlocal state, assistant_speaking
                import base64

                async for event in session:

                    if event.type == "session.created":
                        session_ready.set()

                    # 🔊 STREAM AUDIO BACK
                    if event.type == "response.audio.delta":
                        assistant_speaking = True
                        state = "speaking"

                        delta = getattr(event, "delta", None)
                        if delta:
                            if isinstance(delta, str):
                                await websocket.send_bytes(base64.b64decode(delta))
                            else:
                                await websocket.send_bytes(delta)

                    # 🧠 RESPONSE COMPLETE
                    if event.type == "response.done":
                        assistant_speaking = False
                        state = "listening"

                        resp = getattr(event, "response", None)
                        if not resp:
                            continue

                        # 🔥 COST GUARD
                        if hasattr(resp, "usage") and resp.usage:
                            from app.utils.ai_usage_logger import log_ai_usage
                            await log_ai_usage(
                                student_id=student_id,
                                action_type="Voice Assistant",
                                model="gpt-4o-mini-realtime-preview",
                                usage_obj=resp.usage
                            )

                            # HARD TOKEN SAFETY
                            if resp.usage.total_tokens > 3000:
                                print(f"⚠️ Safety Guard: Response cancelled due to high token count ({resp.usage.total_tokens}).", flush=True)
                                await session.response.cancel()
                            else:
                                print(f"📊 Usage Summary: {resp.usage.total_tokens} tokens | Status: {getattr(resp, 'status', 'done')}", flush=True)

                        for item in getattr(resp, "output", []):
                            if item.type == "message":
                                for content in item.content:
                                    text = ""
                                    if content.type == "text":
                                        text = content.text
                                    elif content.type == "audio":
                                        text = content.transcript

                                    if text:
                                        print(f"🤖 Miki: {text}", flush=True)
                                        await websocket.send_text(f"AI: {text}")
                                        await save_chat_event(student_id, session_id, "assistant", text)

                    # 🎙 USER TRANSCRIPTION COMPLETE
                    if event.type == "conversation.item.input_audio_transcription.completed":
                        user_text = getattr(event, "transcript", "")
                        if user_text:
                            print(f"👤 User (Speech): {user_text}", flush=True)
                            await save_chat_event(student_id, session_id, "user", user_text)

                    # 🛠 TOOL CALL
                    if event.type == "response.function_call_arguments.done":

                        tool_call_id = event.call_id
                        function_name = event.name
                        arguments = json.loads(event.arguments)
                        print(f"🛠️ Tool Call: {function_name}({arguments})", flush=True)

                        result = ""

                        if function_name == "search_textbook":
                            result = await ai_tutor_service.get_relevant_context(
                                student_class,
                                arguments["query"]
                            )

                        elif function_name == "search_web":
                            result = await ai_tutor_service.search_web(
                                arguments["query"]
                            )

                        # 🔥 TOOL OUTPUT LIMIT (CRITICAL)
                        MAX_TOOL_CHARS = 4000
                        result = (result or "")[:MAX_TOOL_CHARS]
                        
                        if result:
                            print(f"📝 Tool Result (Truncated): {result[:100]}...", flush=True)
                        else:
                            print("⚠️ Tool returned NO results.", flush=True)

                        await session.conversation.item.create(
                            item={
                                "type": "function_call_output",
                                "call_id": tool_call_id,
                                "output": result or "No relevant information found."
                            }
                        )

                        await session.response.create()

            await asyncio.gather(
                receive_messages(),
                send_events()
            )

    except Exception as e:
        logger.error(f"Realtime session error: {e}")
        await websocket.close(code=1011)




@router.websocket("/ws/{student_id}/{session_id}")
async def websocket_endpoint(websocket: WebSocket, student_id: str, session_id: str):
    # 1. Validate student_id
    try:
        s_oid = ObjectId(student_id)
    except:
        await websocket.accept()
        await websocket.send_text("Invalid student_id format.")
        await websocket.close(code=1003)
        return

    student = await db.students.find_one({"_id": s_oid})
    if not student:
        print('not found')
        await websocket.accept()
        await websocket.send_text("Student not found.")
        await websocket.close(code=1003)
        return

    # 3. Accept connection and start the loop
    await websocket.accept()
    try:
        await handle_realtime_voice(websocket, student_id, session_id, student)
    except Exception as e:
        logger.error(f"WebSocket endpoint error: {e}")
