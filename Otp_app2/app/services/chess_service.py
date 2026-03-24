import chess
from stockfish import Stockfish
from fastapi import HTTPException
from typing import Dict, Any
import os

class ChessService:
    @staticmethod
    def get_stockfish_instance(difficulty: int) -> Stockfish:
        # Default expects 'stockfish' binary to be in PATH
        stockfish_path = os.environ.get("STOCKFISH_PATH", "stockfish")
        try:
            stockfish = Stockfish(path=stockfish_path)
            stockfish.set_skill_level(difficulty)
            return stockfish
        except Exception as e:
            raise HTTPException(
                status_code=500, 
                detail=f"Stockfish engine not found or failed to load. Make sure the 'stockfish' executable is installed on the system and added to PATH, or set the STOCKFISH_PATH environment variable to the .exe location. Internal error: {str(e)}"
            )

    @staticmethod
    def get_bot_move(fen: str, difficulty: int = 5) -> str:
        """Returns the best move as a UCI string (e.g., 'e2e4')"""
        stockfish = ChessService.get_stockfish_instance(difficulty)
        if stockfish.is_fen_valid(fen):
            stockfish.set_fen_position(fen)
            best_move = stockfish.get_best_move()
            return best_move
        else:
            raise HTTPException(status_code=400, detail="Invalid FEN string provided to bot.")

    @staticmethod
    def calculate_new_fen(fen: str, move_uci: str) -> Dict[str, Any]:
        """Validates the uci move and returns the new FEN along with game status"""
        board = chess.Board(fen)
        try:
            move = chess.Move.from_uci(move_uci)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid move format: {move_uci}. Expects UCI (e.g., 'e2e4')")
            
        if move not in board.legal_moves:
            raise HTTPException(status_code=400, detail=f"Illegal move: {move_uci}")
            
        board.push(move)
        
        status = "playing"
        if board.is_checkmate():
            status = "checkmate"
        elif board.is_stalemate():
            status = "stalemate"
        elif board.is_insufficient_material() or board.is_seventyfive_moves() or board.is_fivefold_repetition():
            status = "draw"
            
        return {
            "fen": board.fen(),
            "status": status,
            "is_check": board.is_check()
        }
