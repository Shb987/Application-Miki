import os
import asyncio
from datetime import datetime, timezone
from bson import ObjectId
from openai import AsyncOpenAI
from app.core.database import db
from app.core.settings import settings
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
import logging

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

async def handle_realtime_voice(websocket: WebSocket, student_id: str, session_id: str):
    try:
        async with client.beta.realtime.connect(
            model="gpt-4o-realtime-preview"
        ) as session:
            # Configure the session
            await session.session.update(
                session={
                    "instructions": "You are a fast, intelligent student companion. You and the student must communicate ONLY in English. Respond briefly and encouragingly.",
                    "modalities": ["audio", "text"],
                    "input_audio_transcription": {"model": "whisper-1"} # Enable user transcription
                }
            )

            async def receive_messages():
                try:
                    while True:
                        msg = await websocket.receive()
                        
                        # Handle disconnection
                        if msg["type"] == "websocket.disconnect":
                            logger.info(f"WebSocket disconnected for student {student_id}")
                            break
                            
                        # Handle binary audio
                        if msg.get("bytes"):
                            audio_chunk = msg["bytes"]
                            import base64
                            base64_audio = base64.b64encode(audio_chunk).decode("utf-8")
                            await session.input_audio_buffer.append(audio=base64_audio)
                            
                        # Handle text trigger
                        elif msg.get("text"):
                            text_content = msg["text"]
                            # If the client sends a text message, treat it as user input
                            await session.conversation.item.create(
                                item={
                                    "type": "message",
                                    "role": "user",
                                    "content": [{"type": "input_text", "text": text_content}],
                                }
                            )
                            await session.response.create()
                except Exception as e:
                    logger.error(f"Error in receive_messages loop: {e}")

            async def send_events():
                import traceback
                import base64
                try:
                    async for event in session:
                        # Log every event type for deep debugging
                        logger.info(f"OpenAI Event Received: {event.type}")

                        # 0. Handle explicit error events from OpenAI
                        if event.type == "error":
                            logger.error(f"OpenAI Realtime Error detail: {getattr(event, 'error', 'No detail')}")
                            continue

                        # 1. Stream audio delta back to client for instant playback
                        if event.type == "response.audio.delta":
                            delta = getattr(event, "delta", None)
                            if delta:
                                try:
                                    # Handle both raw bytes and base64 strings
                                    if isinstance(delta, str):
                                        await websocket.send_bytes(base64.b64decode(delta))
                                    else:
                                        await websocket.send_bytes(delta)
                                except Exception as audio_err:
                                    logger.error(f"Error sending audio delta: {audio_err}")

                        # 2. Capture and save Assistant response
                        if event.type == "response.done":
                            resp = getattr(event, "response", None)
                            if not resp or not hasattr(resp, "output"):
                                continue
                                
                            # Get the text from the response item
                            for item in resp.output:
                                if getattr(item, "type", None) == "message":
                                    content_list = getattr(item, "content", [])
                                    for content in content_list:
                                        if getattr(content, "type", None) == "text":
                                            text = getattr(content, "text", "")
                                            if text:
                                                logger.info(f"AI Response: {text}")
                                                await save_chat_event(student_id, session_id, "assistant", text)

                        # 3. Capture and save User transcription (Whisper)
                        if event.type == "conversation.item.input_audio_transcription.completed":
                            user_text = getattr(event, "transcript", "")
                            if user_text:
                                logger.info(f"User Speech: {user_text}")
                                await save_chat_event(student_id, session_id, "user", user_text)

                except Exception as e:
                    logger.error(f"FATAL Exception in OpenAI event loop ({type(e).__name__}): {e}")
                    logger.error(traceback.format_exc())

            await asyncio.gather(
                receive_messages(),
                send_events()
            )
    except Exception as e:
        logger.error(f"Realtime session error for student {student_id}: {e}")
        try:
            await websocket.close(code=1011)
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

    # 2. Verify student exists in DB
    student = await db.students.find_one({"_id": s_oid})
    if not student:
        await websocket.accept()
        await websocket.send_text("Student not found.")
        await websocket.close(code=1003)
        return

    # 3. Accept connection and start the loop
    await websocket.accept()
    try:
        await handle_realtime_voice(websocket, student_id, session_id)
    except Exception as e:
        logger.error(f"WebSocket endpoint error: {e}")
