import time
import chess
from fastapi import HTTPException
from typing import Dict, Any, Optional, List, Union

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


def order_moves(board: chess.Board) -> List[chess.Move]:
    """
    Orders legal moves to maximize alpha-beta pruning efficiency.
    Evaluates Captures (MVV-LVA), Promotions, and Checks first.
    """
    def move_score(move: chess.Move) -> int:
        score = 0
        if board.is_capture(move):
            attacker = board.piece_at(move.from_square)
            victim = board.piece_at(move.to_square)
            att_val = PIECE_VALUES.get(attacker.piece_type, 100) if attacker else 100
            vic_val = PIECE_VALUES.get(victim.piece_type, 100) if victim else 100
            score += 10000 + (vic_val * 10 - att_val)
        if move.promotion:
            score += 9000
        if board.gives_check(move):
            score += 5000
        return score

    return sorted(board.legal_moves, key=move_score, reverse=True)


def alpha_beta(board: chess.Board, depth: int, alpha: float, beta: float, maximizing: bool, start_time: float, max_seconds: float) -> float:
    if depth == 0 or board.is_game_over() or (time.time() - start_time) > max_seconds:
        return evaluate_board(board)

    ordered_moves = order_moves(board)

    if maximizing:
        max_eval = -float('inf')
        for move in ordered_moves:
            board.push(move)
            eval_ = alpha_beta(board, depth - 1, alpha, beta, False, start_time, max_seconds)
            board.pop()
            max_eval = max(max_eval, eval_)
            alpha = max(alpha, eval_)
            if beta <= alpha:
                break
        return max_eval
    else:
        min_eval = float('inf')
        for move in ordered_moves:
            board.push(move)
            eval_ = alpha_beta(board, depth - 1, alpha, beta, True, start_time, max_seconds)
            board.pop()
            min_eval = min(min_eval, eval_)
            beta = min(beta, eval_)
            if beta <= alpha:
                break
        return min_eval


def parse_difficulty(difficulty: Any) -> int:
    if isinstance(difficulty, str):
        diff_str = difficulty.strip().lower()
        if "easy" in diff_str:
            return 3
        elif "medium" in diff_str:
            return 8
        elif "hard" in diff_str or "expert" in diff_str:
            return 15
    try:
        return int(difficulty)
    except (ValueError, TypeError):
        return 5


def difficulty_to_depth_and_time(difficulty_val: Any) -> tuple:
    """
    Returns (search_depth, max_seconds_timeout) for the given difficulty level.
    With move ordering (MVV-LVA), depth 3 takes ~0.05s and depth 4 takes ~0.25s.
    """
    d = parse_difficulty(difficulty_val)
    if d <= 4:
        return 2, 0.2  # Easy: Depth 2, 200ms max
    elif d <= 12:
        return 3, 0.5  # Medium: Depth 3, 500ms max
    else:
        return 4, 0.8  # Hard: Depth 4, 800ms max


class ChessService:

    @staticmethod
    def get_bot_move(fen: str, difficulty: Union[int, str] = 5) -> Optional[str]:
        """Returns the best move as a UCI string (e.g., 'e2e4') using optimized minimax engine."""
        try:
            board = chess.Board(fen)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid FEN string provided.")

        if board.is_game_over():
            return None

        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return None
        if len(legal_moves) == 1:
            return legal_moves[0].uci()

        depth, max_seconds = difficulty_to_depth_and_time(difficulty)
        start_time = time.time()

        best_move: Optional[chess.Move] = legal_moves[0]
        is_maximizing = (board.turn == chess.WHITE)
        best_eval = -float('inf') if is_maximizing else float('inf')

        ordered_moves = order_moves(board)

        for move in ordered_moves:
            board.push(move)
            eval_ = alpha_beta(board, depth - 1, -float('inf'), float('inf'), not is_maximizing, start_time, max_seconds)
            board.pop()

            if is_maximizing:
                if eval_ > best_eval:
                    best_eval = eval_
                    best_move = move
            else:
                if eval_ < best_eval:
                    best_eval = eval_
                    best_move = move

            if (time.time() - start_time) > max_seconds:
                break

        return best_move.uci() if best_move else legal_moves[0].uci()

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
