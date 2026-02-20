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

            async def receive_audio():
                try:
                    while True:
                        audio_chunk = await websocket.receive_bytes()
                        # Base64 encode the bytes because the SDK sends this as JSON
                        import base64
                        base64_audio = base64.b64encode(audio_chunk).decode("utf-8")
                        await session.input_audio_buffer.append(audio=base64_audio)
                except WebSocketDisconnect:
                    logger.info(f"WebSocket disconnected for student {student_id}")
                except Exception as e:
                    logger.error(f"Error receiving audio: {e}")

            async def send_events():
                try:
                    async for event in session:
                        # 1. Stream audio delta back to client for instant playback
                        if event.type == "response.audio.delta":
                            await websocket.send_bytes(event.delta)

                        # 2. Capture and save Assistant response
                        if event.type == "response.done":
                            # Get the text from the response item
                            for item in event.response.output:
                                if item.type == "message":
                                    for content in item.content:
                                        if content.type == "text":
                                            logger.info(f"AI Response: {content.text}")
                                            await save_chat_event(student_id, session_id, "assistant", content.text)

                        # 3. Capture and save User transcription (Whisper)
                        if event.type == "conversation.item.input_audio_transcription.completed":
                            user_text = event.transcript
                            logger.info(f"User Speech: {user_text}")
                            await save_chat_event(student_id, session_id, "user", user_text)

                except Exception as e:
                    logger.error(f"Error handling OpenAI events: {e}")

            await asyncio.gather(
                receive_audio(),
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
