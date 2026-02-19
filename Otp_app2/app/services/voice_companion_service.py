import os
from openai import AsyncOpenAI
from app.core.database import db
from bson import ObjectId
from datetime import datetime, timezone
from pathlib import Path

# Initialize OpenAI Client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class VoiceCompanionService:
    def __init__(self):
        self.voice = "nova"  # High-quality voice as requested
        self.model_stt = "whisper-1"
        self.model_tts = "tts-1"
        self.model_chat = "gpt-4o"

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
            student = await db.students.find_one({"_id": ObjectId(student_id)})
            student_name = student.get("student_name", "Student") if student else "Student"
            
            # System Prompt for Siri-like Persona
            system_prompt = f"""
            You are 'Miki', a fast, friendly, and high-quality AI Voice Companion.
            Your persona is inspired by Siri: clear, structured, encouraging, and helpful.
            
            INSTRUCTIONS:
            - Keep your responses concise and natural for verbal communication.
            - Address the student as {student_name}.
            - Provide helpful academic and general guidance.
            - Use a conversational and energetic tone.
            """

            messages = [{"role": "system", "content": system_prompt}]

            # Load recent voice chat history
            history_obj = await db.voice_companion_chats.find_one({"student_id": student_id})
            if history_obj:
                recent_msgs = history_obj.get("messages", [])[-10:] # Slightly longer history for voice
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

    async def text_to_speech(self, text: str, output_path: str):
        """Convert text to high-quality audio."""
        try:
            response = await client.audio.speech.create(
                model=self.model_tts,
                voice=self.voice,
                input=text
            )
            response.stream_to_file(output_path)
            return True
        except Exception as e:
            print(f"TTS Error: {e}")
            return False

voice_companion_service = VoiceCompanionService()
