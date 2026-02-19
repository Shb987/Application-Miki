import os
from openai import AsyncOpenAI
from app.core.database import db
from bson import ObjectId
from datetime import datetime, timezone
from pathlib import Path

# Initialize OpenAI Client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

import asyncio

class VoiceCompanionService:
    def __init__(self):
        self.voice = "nova"  # High-quality voice as requested
        self.model_stt = "whisper-1"
        self.model_tts = "tts-1"
        self.model_chat = "gpt-4o-mini" # Faster model for voice interaction

    async def transcribe_audio(self, audio_file_path: str) -> str:
        """Transcribe audio file to text using Whisper."""
        try:
            with open(audio_file_path, "rb") as audio_file:
                transcript = await client.audio.transcriptions.create(
                    model=self.model_stt, 
                    file=audio_file
                )
            return transcript.text
        except Exception as e:
            print(f"STT Error: {e}")
            return ""

    async def get_voice_response(self, student_id: str, text: str) -> str:
        """Generate AI text response with Siri-like persona and history context."""
        try:
            # Reverting back to sequential await for stability unless parallel is proven safe with this motor version
            student = await db.students.find_one({"_id": ObjectId(student_id)})
            history_obj = await db.voice_companion_chats.find_one({"student_id": student_id})
            
            student_name = student.get("student_name", "Student") if student else "Student"
            
            # System Prompt for Siri-like Persona
            system_prompt = f"""
            You are 'Miki', a fast, friendly, and high-quality AI Voice Companion.
            Your persona is inspired by Siri: clear, structured, encouraging, and helpful.
            
            INSTRUCTIONS:
            - Keep your responses VERY concise and natural for verbal communication.
            - Address the student as {student_name}.
            - Provide helpful academic and general guidance.
            - Use a conversational and energetic tone.
            """

            messages = [{"role": "system", "content": system_prompt}]

            # Load recent voice chat history
            if history_obj:
                recent_msgs = history_obj.get("messages", [])[-6:] # Shorter history for speed
                for m in recent_msgs:
                    messages.append({"role": m["role"], "content": m["content"]})

            messages.append({"role": "user", "content": text})

            response = await client.chat.completions.create(
                model=self.model_chat,
                messages=messages,
                temperature=0.7
            )
            ai_text = response.choices[0].message.content

            # Save history
            new_msgs = [
                {"role": "user", "content": text, "timestamp": datetime.now(timezone.utc)},
                {"role": "assistant", "content": ai_text, "timestamp": datetime.now(timezone.utc)}
            ]
            await db.voice_companion_chats.update_one(
                {"student_id": student_id},
                {
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                    "$push": {"messages": {"$each": new_msgs}}
                },
                upsert=True
            )

            return ai_text
        except Exception as e:
            print(f"Chat Error: {e}")
            return "I'm sorry, I hit a snag. Could you say that again?"

    async def stream_text_to_speech(self, text: str):
        """Stream text to high-quality audio chunks."""
        try:
            # Using the newer with_streaming_response or just iter_bytes
            response = await client.audio.speech.create(
                model=self.model_tts,
                voice=self.voice,
                input=text
            )
            # OpenAI's response object from speech.create provides a stream
            return response
        except Exception as e:
            print(f"TTS Streaming Error: {e}")
            return None

voice_companion_service = VoiceCompanionService()
