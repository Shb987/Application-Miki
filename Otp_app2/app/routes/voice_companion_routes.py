from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from app.core.database import db
from app.utils.user_auth import get_current_user
from app.services.voice_companion_service import voice_companion_service
from fastapi.responses import StreamingResponse
import os
import uuid
from pathlib import Path
import shutil

router = APIRouter(prefix="/voice-assistant")

TEMP_AUDIO_DIR = Path("temp/audio")
TEMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

@router.post("/interact")
async def voice_interact(
    student_id: str, 
    audio: UploadFile = File(...), 
    current_user: dict = Depends(get_current_user)
):
    """
    Siri-like interaction with Streaming: 
    1. Transcribe incoming audio.
    2. Get AI response with persona and history.
    3. Stream response audio directly from OpenAI.
    """
    session_id = str(uuid.uuid4())
    input_filename = f"{session_id}_in.wav"
    input_path = TEMP_AUDIO_DIR / input_filename

    try:
        # Save uploaded audio
        with input_path.open("wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)

        # 1. Transcribe
        user_text = await voice_companion_service.transcribe_audio(str(input_path))
        if not user_text:
            raise HTTPException(status_code=400, detail="Could not transcribe audio.")
        
        print(f"🎙️ Transcribed User Voice: {user_text}")

        # 2. Get AI text response
        ai_text = await voice_companion_service.get_voice_response(student_id, user_text)
        print(f"🤖 Miki Response: {ai_text}")

        # 3. Stream TTS response
        audio_stream = await voice_companion_service.stream_text_to_speech(ai_text)
        if not audio_stream:
            raise HTTPException(status_code=500, detail="Failed to generate voice response.")

        return StreamingResponse(audio_stream.iter_bytes(), media_type="audio/mpeg")

    except Exception as e:
        print(f"Interaction Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if input_path.exists():
            os.remove(input_path)

@router.post("/session/start")
async def start_session(student_id: str, current_user: dict = Depends(get_current_user)):
    """Initialize a 'Wake-up' event and stream a greeting."""
    greeting = f"Hello! Miki here, ready to help. What's on your mind today?"
    audio_stream = await voice_companion_service.stream_text_to_speech(greeting)
    if not audio_stream:
        return {"status": "success", "message": greeting}
        
    return StreamingResponse(audio_stream.iter_bytes(), media_type="audio/mpeg")

@router.post("/session/end")
async def end_session(student_id: str, current_user: dict = Depends(get_current_user)):
    """Close the session with a goodbye stream."""
    goodbye = "Goodbye! I'll be here whenever you need me. Have a great day!"
    audio_stream = await voice_companion_service.stream_text_to_speech(goodbye)
    if not audio_stream:
        return {"status": "success", "message": goodbye}
        
    return StreamingResponse(audio_stream.iter_bytes(), media_type="audio/mpeg")
    
# Historical Cleanup (Optional but good practice)
# We can add a background task to clean up old temp files if any remain.
