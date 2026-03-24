from pydantic import BaseModel, Field
from typing import Optional

class ChessMatchmakingRequest(BaseModel):
    mode: str = Field(..., description='"online_pvp" or "bot"')
    difficulty_level: int = Field(5, description="0 to 20 for bot difficulty")

class ChessBotMoveRequest(BaseModel):
    fen: str
    difficulty_level: int = 5

class ChessMoveCommand(BaseModel):
    move: str = Field(..., description="UCI format like 'e2e4' or 'e7e8q'")

class ChessGameStateResponse(BaseModel):
    session_id: str
    fen: str
    status: str
    message: Optional[str] = None
    winner_id: Optional[str] = None
    player_white_id: Optional[str] = None
    player_black_id: Optional[str] = None
