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

    # 🎙 Conversational-mode instructions — plain speech, no markdown
    instructions += """
    - Be extremely conversational and brief.
    - NEVER use markdown: no asterisks, no bullet points, no numbered lists, no bold.
    - Speak in plain natural sentences exactly like you are talking out loud in a phone call.
    - Keep responses short and to the point — 1 to 3 sentences unless the topic truly needs more.
    - If the student interrupts, stop and address what they said immediately.
    """

    state = "listening"
    assistant_speaking = False
    last_valid_user_transcript = ""

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
                        "threshold": 0.65,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 800
                    }
                    # No tool_choice — no tools are registered for this realtime session.
                    # Setting tool_choice:auto with no tools causes status=failed responses.
                }
            )

            session_ready = asyncio.Event()

            # ==============================
            # RECEIVE LOOP
            # ==============================
            async def receive_messages():
                nonlocal state

                await session_ready.wait()
                print(f"✅ Voice Assistant session active for Student: {student_id}", flush=True)

                while True:
                    msg = await websocket.receive()

                    if msg["type"] == "websocket.disconnect":
                        break

                    if msg.get("bytes"):
                        import base64
                        audio_bytes = msg["bytes"]

                        # Drop stray tiny packets (not real audio)
                        if len(audio_bytes) <= 4:
                            continue

                        # ✅ Always stream audio to OpenAI — barge-in is handled natively
                        # by server VAD via `input_audio_buffer.speech_started` event.
                        # Flutter MUST have echoCancellation:true to prevent loopback.
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

                    # ⚡ BARGE-IN — OpenAI server VAD fires this the moment it
                    # detects the user's voice while the assistant is still speaking.
                    # No custom control signals needed from Flutter.
                    if event.type == "input_audio_buffer.speech_started":
                        if assistant_speaking:
                            print("⚡ Barge-in: User started speaking — cancelling assistant.", flush=True)
                            try:
                                await websocket.send_text(json.dumps({"type": "stop_audio"}))
                            except:
                                pass
                            try:
                                await session.response.cancel()
                            except:
                                pass
                            assistant_speaking = False
                            state = "listening"

                    # 🔊 STREAM AUDIO TO FLUTTER
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

                    # 🎙 USER TRANSCRIPTION COMPLETE
                    if event.type == "conversation.item.input_audio_transcription.completed":
                        user_text = getattr(event, "transcript", "")

                        if not user_text or len(user_text.strip()) < 3:
                            print("⚠️ Ignoring empty/noise transcript.", flush=True)
                            continue

                        last_valid_user_transcript = user_text.strip()
                        print(f"👤 User (Speech): {last_valid_user_transcript}", flush=True)
                        await save_chat_event(student_id, session_id, "user", last_valid_user_transcript)

                    # 🧠 RESPONSE COMPLETE
                    if event.type == "response.done":

                        assistant_speaking = False
                        state = "listening"

                        resp = getattr(event, "response", None)

                        # Skip cancelled / incomplete responses (e.g. interrupted by barge-in)
                        resp_status = getattr(resp, "status", None)
                        if resp_status != "completed":
                            # Log the full error detail so we can debug failures
                            status_detail = getattr(resp, "status_details", None)
                            print(f"⚠️ Response skipped (status={resp_status}, detail={status_detail}).", flush=True)
                            continue

                        if not resp or not getattr(resp, "output", None):
                            print("⚠️ Empty response ignored.", flush=True)
                            continue

                        # Skip if no user ever spoke (e.g. echo-triggered response)
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

                        # Reset after a full completed turn
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
