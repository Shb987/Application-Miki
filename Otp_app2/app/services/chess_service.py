import chess
from fastapi import HTTPException
from typing import Dict, Any, Optional

# ---------------------------------------------------------------
# Pure Python Chess Engine using Minimax + Alpha-Beta Pruning
# No external executable required.
# ---------------------------------------------------------------

# Piece values for the evaluation function
PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000,
}

# Positional bonus tables (from White's perspective)
PAWN_TABLE = [
     0,  0,  0,  0,  0,  0,  0,  0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
     5,  5, 10, 25, 25, 10,  5,  5,
     0,  0,  0, 20, 20,  0,  0,  0,
     5, -5,-10,  0,  0,-10, -5,  5,
     5, 10, 10,-20,-20, 10, 10,  5,
     0,  0,  0,  0,  0,  0,  0,  0,
]

KNIGHT_TABLE = [
    -50,-40,-30,-30,-30,-30,-40,-50,
    -40,-20,  0,  0,  0,  0,-20,-40,
    -30,  0, 10, 15, 15, 10,  0,-30,
    -30,  5, 15, 20, 20, 15,  5,-30,
    -30,  0, 15, 20, 20, 15,  0,-30,
    -30,  5, 10, 15, 15, 10,  5,-30,
    -40,-20,  0,  5,  5,  0,-20,-40,
    -50,-40,-30,-30,-30,-30,-40,-50,
]

BISHOP_TABLE = [
    -20,-10,-10,-10,-10,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5, 10, 10,  5,  0,-10,
    -10,  5,  5, 10, 10,  5,  5,-10,
    -10,  0, 10, 10, 10, 10,  0,-10,
    -10, 10, 10, 10, 10, 10, 10,-10,
    -10,  5,  0,  0,  0,  0,  5,-10,
    -20,-10,-10,-10,-10,-10,-10,-20,
]

ROOK_TABLE = [
     0,  0,  0,  0,  0,  0,  0,  0,
     5, 10, 10, 10, 10, 10, 10,  5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
     0,  0,  0,  5,  5,  0,  0,  0,
]

QUEEN_TABLE = [
    -20,-10,-10, -5, -5,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5,  5,  5,  5,  0,-10,
     -5,  0,  5,  5,  5,  5,  0, -5,
      0,  0,  5,  5,  5,  5,  0, -5,
    -10,  5,  5,  5,  5,  5,  0,-10,
    -10,  0,  5,  0,  0,  0,  0,-10,
    -20,-10,-10, -5, -5,-10,-10,-20,
]

KING_MIDDLEGAME_TABLE = [
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -20,-30,-30,-40,-40,-30,-30,-20,
    -10,-20,-20,-20,-20,-20,-20,-10,
     20, 20,  0,  0,  0,  0, 20, 20,
     20, 30, 10,  0,  0, 10, 30, 20,
]

POSITION_TABLES = {
    chess.PAWN: PAWN_TABLE,
    chess.KNIGHT: KNIGHT_TABLE,
    chess.BISHOP: BISHOP_TABLE,
    chess.ROOK: ROOK_TABLE,
    chess.QUEEN: QUEEN_TABLE,
    chess.KING: KING_MIDDLEGAME_TABLE,
}


def get_piece_positional_score(piece_type: int, square: int, is_white: bool) -> int:
    table = POSITION_TABLES.get(piece_type, [0] * 64)
    # White reads table top-to-bottom (rank 8 first), Black mirrors it
    idx = square if not is_white else chess.square_mirror(square)
    return table[idx]


def evaluate_board(board: chess.Board) -> int:
    """
    Static board evaluation. Positive = good for White, Negative = good for Black.
    """
    if board.is_checkmate():
        return -100000 if board.turn == chess.WHITE else 100000
    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    score = 0
    for square in chess.SQUARES:
        piece = board.piece_at(square)
        if piece:
            value = PIECE_VALUES.get(piece.piece_type, 0)
            positional = get_piece_positional_score(piece.piece_type, square, piece.color == chess.WHITE)
            if piece.color == chess.WHITE:
                score += value + positional
            else:
                score -= value + positional
    return score


def alpha_beta(board: chess.Board, depth: int, alpha: int, beta: int, maximizing: bool) -> int:
    if depth == 0 or board.is_game_over():
        return evaluate_board(board)

    if maximizing:
        max_eval = -float('inf')
        for move in board.legal_moves:
            board.push(move)
            eval_ = alpha_beta(board, depth - 1, alpha, beta, False)
            board.pop()
            max_eval = max(max_eval, eval_)
            alpha = max(alpha, eval_)
            if beta <= alpha:
                break
        return max_eval
    else:
        min_eval = float('inf')
        for move in board.legal_moves:
            board.push(move)
            eval_ = alpha_beta(board, depth - 1, alpha, beta, True)
            board.pop()
            min_eval = min(min_eval, eval_)
            beta = min(beta, eval_)
            if beta <= alpha:
                break
        return min_eval


def difficulty_to_depth(difficulty: int) -> int:
    """
    Maps a 0–20 difficulty level to a minimax search depth (1–5).
    Depth 4-5 is strong enough to challenge most casual players.
    """
    if difficulty <= 3:
        return 1
    elif difficulty <= 7:
        return 2
    elif difficulty <= 12:
        return 3
    elif difficulty <= 17:
        return 4
    else:
        return 5


class ChessService:

    @staticmethod
    def get_bot_move(fen: str, difficulty: int = 5) -> str:
        """Returns the best move as a UCI string (e.g., 'e2e4') using minimax engine."""
        try:
            board = chess.Board(fen)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid FEN string provided.")

        if board.is_game_over():
            raise HTTPException(status_code=400, detail="Game is already over.")

        depth = difficulty_to_depth(difficulty)
        best_move: Optional[chess.Move] = None
        is_maximizing = board.turn == chess.WHITE

        best_eval = -float('inf') if is_maximizing else float('inf')

        for move in board.legal_moves:
            board.push(move)
            eval_ = alpha_beta(board, depth - 1, -float('inf'), float('inf'), not is_maximizing)
            board.pop()

            if is_maximizing and eval_ > best_eval:
                best_eval = eval_
                best_move = move
            elif not is_maximizing and eval_ < best_eval:
                best_eval = eval_
                best_move = move

        if best_move is None:
            raise HTTPException(status_code=500, detail="Engine could not find a move.")

        return best_move.uci()

    @staticmethod
    def calculate_new_fen(fen: str, move_uci: str) -> Dict[str, Any]:
        """Validates the UCI move and returns the new FEN along with game status."""
        try:
            board = chess.Board(fen)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid FEN string.")

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
