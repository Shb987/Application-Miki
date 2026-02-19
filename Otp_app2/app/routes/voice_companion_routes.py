from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from app.core.database import db
from app.utils.user_auth import get_current_user
from app.services.voice_companion_service import voice_companion_service
from fastapi.responses import FileResponse
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
    Siri-like interaction: 
    1. Transcribe incoming audio.
    2. Get AI response with persona and history.
    3. Generate response audio using high-quality TTS.
    4. Return the response audio.
    """
    session_id = str(uuid.uuid4())
    input_filename = f"{session_id}_in.wav"
    input_path = TEMP_AUDIO_DIR / input_filename
    output_filename = f"{session_id}_out.mp3"
    output_path = TEMP_AUDIO_DIR / output_filename

    try:
        # Save uploaded audio
        with input_path.open("wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)

        # 1. Transcribe
        user_text = await voice_companion_service.transcribe_audio(str(input_path))
        if not user_text:
            raise HTTPException(status_code=400, detail="Could not transcribe audio.")

        # 2. Get AI text response
        ai_text = await voice_companion_service.get_voice_response(student_id, user_text)

        # 3. Generate TTS
        success = await voice_companion_service.text_to_speech(ai_text, str(output_path))
        if not success:
            raise HTTPException(status_code=500, detail="Failed to generate voice response.")

        # 4. Return audio file
        # Note: We avoid putting AI response text in headers directly because emojis cause latin-1 encoding errors.
        return FileResponse(
            path=output_path, 
            media_type="audio/mpeg", 
            filename="miki_response.mp3"
        )

    except Exception as e:
        print(f"Interaction Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Cleanup input file immediately, output will be handled by FileResponse? 
        # Actually FileResponse doesn't cleanup by default. 
        # We might need a background task for cleanup if we want to be clean.
        if input_path.exists():
            os.remove(input_path)

@router.post("/session/start")
async def start_session(student_id: str, current_user: dict = Depends(get_current_user)):
    """Initialize a 'Wake-up' event and return a greeting."""
    greeting = f"Hello! Miki here, ready to help. What's on your mind today?"
    output_path = TEMP_AUDIO_DIR / f"{uuid.uuid4()}_wake.mp3"
    
    success = await voice_companion_service.text_to_speech(greeting, str(output_path))
    if not success:
        return {"status": "success", "message": greeting}
        
    return FileResponse(path=output_path, media_type="audio/mpeg", filename="greeting.mp3")

@router.post("/session/end")
async def end_session(student_id: str, current_user: dict = Depends(get_current_user)):
    """Close the session with a goodbye."""
    goodbye = "Goodbye! I'll be here whenever you need me. Have a great day!"
    output_path = TEMP_AUDIO_DIR / f"{uuid.uuid4()}_bye.mp3"
    
    success = await voice_companion_service.text_to_speech(goodbye, str(output_path))
    if not success:
        return {"status": "success", "message": goodbye}
        
    return FileResponse(path=output_path, media_type="audio/mpeg", filename="goodbye.mp3")
