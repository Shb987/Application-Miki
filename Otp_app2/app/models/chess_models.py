from pydantic import BaseModel, Field
from typing import Optional, Union, Any

class ChessMatchmakingRequest(BaseModel):
    mode: str = Field(..., description='"online_pvp" or "bot"')
    difficulty_level: Union[int, str] = Field(5, description="0 to 20 or string ('easy', 'medium', 'hard') for bot difficulty")

class ChessBotMoveRequest(BaseModel):
    fen: str
    difficulty_level: Union[int, str] = 5

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
