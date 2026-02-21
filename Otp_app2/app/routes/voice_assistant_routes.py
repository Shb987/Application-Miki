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
client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=20.0)

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

    try:
        async with client.beta.realtime.connect(
            model="gpt-4o-realtime-preview"
        ) as session:
            print(f"🔗 Connected to OpenAI Realtime for student {student_id}", flush=True)
            # Configure the session with tools
            await session.session.update(
                session={
                    "instructions": instructions,
                    "modalities": ["audio", "text"],
                    "input_audio_transcription": {"model": "whisper-1"},
                    "tools": [
                        {
                            "type": "function",
                            "name": "search_textbook",
                            "description": "Search the student's textbook for academic information, definitions, or chapter content.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string", "description": "The academic query to search for."}
                                },
                                "required": ["query"]
                            }
                        },
                        {
                            "type": "function",
                            "name": "search_web",
                            "description": "Search the web for current events, live data, or facts outside the textbook.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string", "description": "The search query."}
                                },
                                "required": ["query"]
                            }
                        }
                    ],
                    "tool_choice": "auto"
                }
            )
            print("⚙️ OpenAI session configured with tools.", flush=True)

            session_ready = asyncio.Event()

            async def receive_messages():
                try:
                    # Wait for OpenAI session to be fully handshake-created
                    print("⏳ Waiting for OpenAI 'session.created'...", flush=True)
                    await session_ready.wait()
                    print("✅ OpenAI session is ready for messages.", flush=True)

                    while True:
                        msg = await websocket.receive()
                        
                        # Handle disconnection
                        if msg["type"] == "websocket.disconnect":
                            print(f"🔌 WebSocket disconnected for student {student_id}", flush=True)
                            break
                            
                        # Handle binary audio
                        if msg.get("bytes"):
                            audio_chunk = msg["bytes"]
                            import base64
                            base64_audio = base64.b64encode(audio_chunk).decode("utf-8")
                            await session.input_audio_buffer.append(audio=base64_audio)
                            
                        # Handle text trigger
                        elif "text" in msg:
                            text_raw = msg["text"]
                            text_content = text_raw
                            # Try to parse JSON in case the client sends {"text": "..."}
                            try:
                                data = json.loads(text_raw)
                                if isinstance(data, dict):
                                    text_content = data.get("text", data.get("message", text_raw))
                            except:
                                pass

                            print(f"🎙️ Handled Text Trigger: {text_content}", flush=True)
                            
                            # SAVE User Text immediately
                            await save_chat_event(student_id, session_id, "user", text_content)

                            await session.conversation.item.create(
                                item={
                                    "type": "message",
                                    "role": "user",
                                    "content": [{"type": "input_text", "text": text_content}],
                                }
                            )
                            await session.response.create()
                            print("📩 Response requested for text trigger.", flush=True)
                except Exception as e:
                    logger.error(f"Error in receive_messages loop: {e}")

            async def send_events():
                import traceback
                import base64
                try:
                    async for event in session:
                        # Log full event for deep debugging (limited to 500 chars)
                        event_str = str(event)
                        print(f"🔹 OpenAI Event: {event.type} | DATA: {event_str[:500]}...", flush=True)

                        # Signal that session is ready
                        if event.type == "session.created":
                            session_ready.set()

                        # 0. Handle explicit error events from OpenAI
                        if event.type == "error":
                            print(f"❌ OpenAI Error: {getattr(event, 'error', 'No detail')}", flush=True)
                            continue

                        # 1. Stream audio delta back to client for instant playback
                        if event.type == "response.audio.delta":
                            delta = getattr(event, "delta", None)
                            if delta:
                                try:
                                    if isinstance(delta, str):
                                        await websocket.send_bytes(base64.b64decode(delta))
                                    else:
                                        await websocket.send_bytes(delta)
                                except Exception as audio_err:
                                    logger.error(f"Error sending audio delta: {audio_err}")

                        # 2. Capture and save Assistant response
                        if event.type == "response.done":
                            resp = getattr(event, "response", None)
                            if not resp:
                                print("⚠️ response.done received but no response object found.", flush=True)
                                continue
                            
                            # Check if the response was cancelled or failed
                            status = getattr(resp, "status", "unknown")
                            output_items = getattr(resp, "output", [])
                            print(f"🏁 Response Done. Status: {status} | Output items: {len(output_items)}", flush=True)
                                
                            for item in output_items:
                                item_type = getattr(item, "type", None)
                                print(f"  - Item Type: {item_type}", flush=True)
                                
                                if item_type == "message":
                                    content_list = getattr(item, "content", [])
                                    for content in content_list:
                                        # Handle BOTH text and audio transcriptions
                                        content_type = getattr(content, "type", None)
                                        text = ""
                                        if content_type == "text":
                                            text = getattr(content, "text", "")
                                        elif content_type == "audio":
                                            text = getattr(content, "transcript", "")
                                            
                                        if text:
                                            print(f"✨ AI Response: {text}", flush=True)
                                            # Also send text back to client for verification in test script
                                            await websocket.send_text(f"AI: {text}")
                                            await save_chat_event(student_id, session_id, "assistant", text)
                                
                                elif item_type == "function_call":
                                    f_name = getattr(item, "name", "unknown")
                                    f_args = getattr(item, "arguments", "{}")
                                    print(f"  🛠️ Model requested function: {f_name}({f_args})", flush=True)

                        # 3. Capture and save User transcription (Whisper generated)
                        if event.type == "conversation.item.input_audio_transcription.completed":
                            user_text = getattr(event, "transcript", "")
                            if user_text:
                                uv_logger = logging.getLogger("uvicorn.error")
                                print(f"🎙️ User Speech: {user_text}", flush=True)
                                uv_logger.info(f"🎙️ User Speech: {user_text}")
                                await save_chat_event(student_id, session_id, "user", user_text)

                        # 4. Handle Tool Calls (Tool Calling in Realtime API)
                        if event.type == "response.function_call_arguments.done":
                            tool_call_id = event.call_id
                            function_name = event.name
                            arguments = json.loads(event.arguments)
                            
                            uv_logger = logging.getLogger("uvicorn.error")
                            print(f"🛠️ Tool Call: {function_name}({arguments})", flush=True)
                            uv_logger.info(f"🛠️ Tool Call: {function_name}({arguments})")
                            
                            result = ""
                            if function_name == "search_textbook":
                                result = await ai_tutor_service.get_relevant_context(student_class, arguments["query"])
                            elif function_name == "search_web":
                                result = await ai_tutor_service.search_web(arguments["query"])
                            
                            # Log tool result
                            # print(f"📝 Tool Result: {result[:100]}...", flush=True)
                            
                            # Provide the tool result back to the model
                            await session.conversation.item.create(
                                item={
                                    "type": "function_call_output",
                                    "call_id": tool_call_id,
                                    "output": result or "No relevant information found."
                                }
                            )
                            # Request a new response based on the tool output
                            await session.response.create()

                except Exception as e:
                    logger.error(f"FATAL Exception in OpenAI event loop ({type(e).__name__}): {e}")
                    logger.error(traceback.format_exc())

            await asyncio.gather(
                receive_messages(),
                send_events()
            )
    except Exception as e:
        print(f"❌ Realtime session error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        try:
            await websocket.close(code=1011)
        except:
            pass

@router.websocket("/ws/{student_id}/{session_id}")
async def websocket_endpoint(websocket: WebSocket, student_id: str, session_id: str):
    # 1. Validate student_id
    try:
        s_oid = ObjectId(student_id)
        print('asd')
    except:
        await websocket.accept()
        await websocket.send_text("Invalid student_id format.")
        await websocket.close(code=1003)
        return

    # 2. Verify student exists in DB
    student = await db.students.find_one({"_id": s_oid})
    print(student)
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
