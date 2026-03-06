import os
import asyncio
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
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
    last_assistant_text = ""       # For echo detection
    mute_until = 0.0               # Epoch time until which audio is muted
    MUTE_COOLDOWN_S = 1.5          # Seconds to mute mic after Miki stops talking

    def _is_echo(user_text: str, assistant_text: str) -> bool:
        """Return True if user_text is suspiciously similar to what Miki just said."""
        if not assistant_text or not user_text:
            return False
        # Normalise both sides
        u = user_text.lower().strip()
        a = assistant_text.lower().strip()
        ratio = SequenceMatcher(None, u, a).ratio()
        return ratio > 0.60  # 60% similarity → likely echo

    try:
        async with client.beta.realtime.connect(
            model="gpt-4o-mini-realtime-preview"
        ) as session:

            # Define tools for the Realtime session
            tools = [
                {
                    "type": "function",
                    "name": "web_search",
                    "description": "Perform a web search for current events, facts, or news.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The search query."}
                        },
                        "required": ["query"]
                    }
                },
                {
                    "type": "function",
                    "name": "textbook_search",
                    "description": "Search for academic information in the student's textbooks.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The concept or topic to search for."}
                        },
                        "required": ["query"]
                    }
                }
            ]

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
                    },
                    "tools": tools,
                    "tool_choice": "auto"
                }
            )

            session_ready = asyncio.Event()

            # ==============================
            # RECEIVE LOOP
            # ==============================
            async def receive_messages():
                nonlocal state, last_valid_user_transcript, mute_until

                await session_ready.wait()
                print(f"✅ Voice Assistant session active for Student: {student_id}", flush=True)

                while True:
                    msg = await websocket.receive()

                    if msg["type"] == "websocket.disconnect":
                        break

                    # 🔊 Audio chunks from Flutter
                    if msg.get("bytes"):
                        import base64
                        audio_bytes = msg["bytes"]

                        # Drop stray tiny packets (not real audio)
                        if len(audio_bytes) <= 4:
                            continue

                        # 🔇 MUTE WINDOW: Don't forward audio to OpenAI while
                        # Miki is speaking or shortly after (echo cooldown).
                        # This is the most reliable server-side echo mitigation.
                        if time.monotonic() < mute_until:
                            continue

                        base64_audio = base64.b64encode(audio_bytes).decode("utf-8")
                        await session.input_audio_buffer.append(audio=base64_audio)
                        state = "listening"

                    # ⌨️ Text triggers (for testing or UI buttons)
                    elif msg.get("text"):
                        text_content = msg.get("text")
                        
                        # Handle explicit interrupt from Flutter UI
                        if text_content.strip() == "_INTERRUPT_":
                            print("⚡ Barge-in: Manual _INTERRUPT_ signal received from UI.", flush=True)
                            if assistant_speaking:
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
                            continue
                            
                        print(f"👤 User (Text): {text_content}", flush=True)
                        
                        # Add a text item to the conversation and request a response
                        last_valid_user_transcript = text_content
                        await session.conversation.item.create(
                            item={
                                "type": "message",
                                "role": "user",
                                "content": [{"type": "input_text", "text": text_content}]
                            }
                        )
                        await session.response.create()
                        await save_chat_event(student_id, session_id, "user", text_content)

            # ==============================
            # SEND LOOP
            # ==============================
            async def send_events():
                nonlocal state, assistant_speaking, last_valid_user_transcript, last_assistant_text, mute_until
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
                        # Keep extending the mute window with each new audio chunk
                        mute_until = time.monotonic() + MUTE_COOLDOWN_S

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

                        if not user_text or not user_text.strip():
                            print("⚠️ Ignoring noise transcript.", flush=True)
                            continue

                        clean_text = user_text.strip()

                        # 🔁 ECHO DETECTION: Discard transcripts that closely
                        # match what Miki just said — those are speaker echoes.
                        if _is_echo(clean_text, last_assistant_text):
                            print(f"🔁 Echo detected and discarded: '{clean_text[:60]}'", flush=True)
                            continue

                        last_valid_user_transcript = clean_text
                        print(f"👤 User (Speech): {last_valid_user_transcript}", flush=True)
                        await save_chat_event(student_id, session_id, "user", last_valid_user_transcript)

                    # 🧠 RESPONSE COMPLETE
                    if event.type == "response.done":

                        assistant_speaking = False
                        state = "listening"

                        resp = getattr(event, "response", None)
                        if not resp:
                            continue
                            
                        resp_status = getattr(resp, "status", None)

                        # Log skipped responses for debugging
                        if resp_status != "completed":
                            status_detail = getattr(resp, "status_details", None)
                            if resp_status != "cancelled": # Don't spam for normal barge-ins
                                print(f"⚠️ Response {resp.id} skipped (status={resp_status}, detail={status_detail}).", flush=True)
                            continue

                        # Check if this response has any content
                        outputs = getattr(resp, "output", [])
                        if not outputs:
                            # print(f"ℹ️ Response {resp.id} completed with no output.", flush=True)
                            continue

                        # Final safety check: if we have zero user input context, 
                        # we only proceed if there's actually a message or tool call to show.
                        if not last_valid_user_transcript:
                            has_substantive_output = any(item.type in ["message", "function_call"] for item in outputs)
                            if not has_substantive_output:
                                print(f"⚠️ Skipping response {resp.id} - no user transcript and no substantive output.", flush=True)
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
                                        last_assistant_text = text.strip()  # Track for echo detection
                                        # Extend mute window when the response text is finalised
                                        mute_until = time.monotonic() + MUTE_COOLDOWN_S
                                        try:
                                            # Send back text to Flutter for UI update
                                            await websocket.send_text(json.dumps({"type": "text_response", "text": text}))
                                        except:
                                            pass
                                        await save_chat_event(student_id, session_id, "assistant", text.strip())

                        # Handle Tool Calls
                        has_tool_call = False
                        for item in resp.output:
                            if item.type == "function_call":
                                has_tool_call = True
                                tool_name = item.name
                                tool_call_id = item.call_id
                                args = json.loads(item.arguments)
                                
                                print(f"🛠 Tool Call: {tool_name}({args})", flush=True)
                                
                                result = ""
                                if tool_name == "web_search":
                                    result = await ai_tutor_service.search_web(args.get("query", ""))
                                elif tool_name == "textbook_search":
                                    result = await ai_tutor_service.get_relevant_context(student_class, args.get("query", ""))
                                
                                # Send tool result back to session
                                await session.conversation.item.create(
                                    item={
                                        "type": "function_call_output",
                                        "call_id": tool_call_id,
                                        "output": result or "No information found."
                                    }
                                )
                                # Request a response based on the tool output
                                await session.response.create()

                        # Log usage
                        if resp and hasattr(resp, 'usage') and resp.usage:
                            from app.utils.ai_usage_logger import log_ai_usage
                            await log_ai_usage(student_id, "Voice Assistant", "gpt-4o-mini-realtime-preview", resp.usage)

                        # Reset after a full completed turn (only if no tool calls are pending)
                        if not has_tool_call:
                            if last_valid_user_transcript:
                                # print(f"✅ Turn completed for: {last_valid_user_transcript[:30]}...", flush=True)
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
