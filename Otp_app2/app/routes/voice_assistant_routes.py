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

    instructions += """
    - Be extremely conversational and brief.
    - Avoid markdown formatting.
    - Speak naturally like a human tutor.
    - If interrupted, continue naturally.
    """

    state = "listening"
    assistant_speaking = False
    last_valid_user_transcript = ""
    last_barge_in_time = 0.0
    last_silence_time = 0.0
    DEBOUNCE_SECONDS = 0.5

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
                    "max_response_output_tokens": 1200,
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.65,              # 🔥 stricter
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 1200     # 🔥 longer silence required
                    },
                    "tool_choice": "auto"
                }
            )

            session_ready = asyncio.Event()

            # ==============================
            # RECEIVE LOOP
            # ==============================
            async def receive_messages():
                nonlocal state, assistant_speaking, last_barge_in_time, last_silence_time
                import time

                await session_ready.wait()
                print(f"✅ Voice Assistant session active for Student: {student_id}", flush=True)

                while True:
                    msg = await websocket.receive()

                    if msg["type"] == "websocket.disconnect":
                        break

                    if msg.get("bytes"):
                        import base64
                        audio_bytes = msg["bytes"]

                        # ── Control signals (e.g., barge-in / silence) are tiny (<= 4 bytes) ──
                        if len(audio_bytes) <= 4:
                            now = time.monotonic()

                            # Treat as silence commit signal
                            if not assistant_speaking:
                                if now - last_silence_time >= DEBOUNCE_SECONDS:
                                    last_silence_time = now
                                    print("🤫 Silence signal: Commit & Create Response.", flush=True)
                            else:
                                # Barge-in: debounce and cancel current response
                                if now - last_barge_in_time >= DEBOUNCE_SECONDS:
                                    last_barge_in_time = now
                                    print("⚡ Barge-in detected: Interrupting Assistant.", flush=True)
                                    try:
                                        await websocket.send_text(json.dumps({"type": "stop_audio"}))
                                    except:
                                        pass
                                    try:
                                        await session.response.cancel()
                                    except:
                                        pass
                                    assistant_speaking = False
                                    state = "interrupted"
                            continue  # Never send control bytes to OpenAI

                        # ── Real audio chunk ──
                        # 🔥 FIX 1: Block loopback — do NOT append audio while assistant is speaking
                        if assistant_speaking:
                            continue

                        base64_audio = base64.b64encode(audio_bytes).decode("utf-8")
                        await session.input_audio_buffer.append(audio=base64_audio)
                        state = "listening"

            # ==============================
            # SEND LOOP
            # ==============================
            async def send_events():
                nonlocal state, assistant_speaking, last_valid_user_transcript
                import base64

                async for event in session:

                    if event.type == "session.created":
                        session_ready.set()

                    # 🔊 STREAM AUDIO
                    if event.type == "response.audio.delta":
                        assistant_speaking = True
                        state = "speaking"

                        delta = getattr(event, "delta", None)
                        if delta:
                            try:
                                if isinstance(delta, str):
                                    await websocket.send_bytes(base64.b64decode(delta))
                                else:
                                    await websocket.send_bytes(delta)
                            except:
                                break

                    # 🎙 TRANSCRIPTION COMPLETE
                    if event.type == "conversation.item.input_audio_transcription.completed":
                        user_text = getattr(event, "transcript", "")

                        # 🔥 BLOCK EMPTY / NOISE
                        if not user_text or len(user_text.strip()) < 3:
                            print("⚠️ Ignoring empty/noise transcript.", flush=True)
                            continue

                        last_valid_user_transcript = user_text.strip()

                        print(f"👤 User: {last_valid_user_transcript}", flush=True)
                        await save_chat_event(student_id, session_id, "user", last_valid_user_transcript)

                    # 🧠 RESPONSE COMPLETE
                    if event.type == "response.done":

                        assistant_speaking = False
                        state = "listening"

                        resp = getattr(event, "response", None)

                        # 🔥 FIX 3: Skip cancelled / incomplete responses
                        resp_status = getattr(resp, "status", None)
                        if resp_status != "completed":
                            print(f"⚠️ Response skipped (status={resp_status}).", flush=True)
                            continue

                        # 🔥 BLOCK EMPTY MODEL RESPONSES
                        if not resp or not getattr(resp, "output", None):
                            print("⚠️ Empty response ignored.", flush=True)
                            continue

                        # 🔥 BLOCK RESPONSE IF NO VALID USER INPUT
                        if not last_valid_user_transcript:
                            print("⚠️ No valid user transcript — skipping response.", flush=True)
                            continue

                        for item in resp.output:
                            if item.type == "message":
                                for content in item.content:

                                    text = ""
                                    if content.type == "text":
                                        text = content.text
                                    elif content.type == "audio":
                                        text = content.transcript

                                    if text and text.strip():

                                        print(f"🤖 Miki: {text}", flush=True)

                                        try:
                                            await websocket.send_text(f"AI: {text}")
                                        except:
                                            pass

                                        await save_chat_event(student_id, session_id, "assistant", text.strip())

                        # 🔥 Reset transcript tracker
                        last_valid_user_transcript = ""

            receive_task = asyncio.create_task(receive_messages())
            send_task = asyncio.create_task(send_events())

            done, pending = await asyncio.wait(
                [receive_task, send_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            for task in pending:
                task.cancel()
                try:
                    await task
                except:
                    pass

    except Exception as e:
        logger.error(f"Realtime session error: {e}")
    finally:
        try:
            if websocket.client_state.name != "DISCONNECTED":
                await websocket.close()
        except:
            pass

    

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
