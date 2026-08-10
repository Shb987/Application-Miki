from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List
from app.models.chess_models import ChessBotMoveRequest, ChessMoveCommand
from app.services.chess_service import ChessService

router = APIRouter()

@router.post("/bot/move")
async def get_bot_move(request: ChessBotMoveRequest):
    """
    Given a FEN string, asks the Stockfish backend to calculate the best move.
    Used for PvE matches.
    """
    bot_move = ChessService.get_bot_move(request.fen, request.difficulty_level)
    
    # Calculate the resulting FEN after applying the bot's move
    result = ChessService.calculate_new_fen(request.fen, bot_move)
    
    return {
        "bot_move": bot_move,
        "new_fen": result["fen"],
        "status": result["status"],
        "is_check": result["is_check"]
    }

@router.post("/validate_move")
async def validate_move(fen: str, command: ChessMoveCommand):
    """Utility endpoint to test a move on a given FEN string"""
    result = ChessService.calculate_new_fen(fen, command.move)
    return result

# --- WEBSOCKET FOR PVP MATCHMAKING ---
# Maps session_id -> list of active WebSocket connections
active_connections: Dict[str, List[WebSocket]] = {}

@router.websocket("/ws/{session_id}")
async def chess_websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    if session_id not in active_connections:
        active_connections[session_id] = []
    active_connections[session_id].append(websocket)
    
    try:
        while True:
            # We expect a JSON payload {"fen": "...", "move": "e2e4"} from Flutter
            data = await websocket.receive_json()
            
            # Ideally:
            # 1. Read actual game FEN from MongoDB
            # 2. ChessService.calculate_new_fen(db_fen, data["move"])
            # 3. Update MongoDB
            # 4. Broadcast the new dict state to everyone:
            
            for connection in active_connections[session_id]:
                await connection.send_json({
                    "event": "move_made",
                    "data": data
                })
                
    except WebSocketDisconnect:
        active_connections[session_id].remove(websocket)
        if not active_connections[session_id]:
            del active_connections[session_id]
