import random
import copy

class SudokuGenerator:
    def __init__(self, size, block_rows, block_cols):
        self.size = size
        self.block_rows = block_rows
        self.block_cols = block_cols

    def is_valid(self, board, row, col, num):
        # Check row and column
        for i in range(self.size):
            if board[row][i] == num:
                return False
            if board[i][col] == num:
                return False
                
        # Check block
        start_row = row - row % self.block_rows
        start_col = col - col % self.block_cols
        
        for i in range(self.block_rows):
            for j in range(self.block_cols):
                if board[i + start_row][j + start_col] == num:
                    return False
        return True

    def solve(self, board):
        for row in range(self.size):
            for col in range(self.size):
                if board[row][col] == 0:
                    numbers = list(range(1, self.size + 1))
                    random.shuffle(numbers)
                    for num in numbers:
                        if self.is_valid(board, row, col, num):
                            board[row][col] = num
                            if self.solve(board):
                                return True
                            board[row][col] = 0
                    return False
        return True

    def count_solutions(self, board, limit=2):
        for row in range(self.size):
            for col in range(self.size):
                if board[row][col] == 0:
                    count = 0
                    for num in range(1, self.size + 1):
                        if self.is_valid(board, row, col, num):
                            board[row][col] = num
                            count += self.count_solutions(board, limit)
                            board[row][col] = 0
                            if count >= limit:
                                return count
                    return count
        return 1

    def generate(self, difficulty: str):
        board = [[0 for _ in range(self.size)] for _ in range(self.size)]
        
        # Generate full solved board
        self.solve(board)
        solution = copy.deepcopy(board)
        
        # Remove numbers based on difficulty
        empty_percentages = {
            "easy": 0.4,
            "easy+": 0.5,
            "medium": 0.6,
            "hard": 0.7,
            "expert": 0.75
        }
        
        percentage = empty_percentages.get(difficulty.lower(), 0.5)
        cells_to_remove = int(self.size * self.size * percentage)
        
        cells = [(r, c) for r in range(self.size) for c in range(self.size)]
        random.shuffle(cells)
        
        puzzle = copy.deepcopy(board)
        removed_count = 0
        
        for r, c in cells:
            if removed_count >= cells_to_remove:
                break
                
            temp = puzzle[r][c]
            puzzle[r][c] = 0
            
            solutions_count = self.count_solutions(puzzle, limit=2)
            
            if solutions_count == 1:
                removed_count += 1
            else:
                puzzle[r][c] = temp
                
        return puzzle, solution

def get_level_config(level: int):
    if 1 <= level <= 5:
        return {"grid_size": 6, "block_rows": 2, "block_cols": 3, "difficulty": "easy"}
    elif 6 <= level <= 10:
        return {"grid_size": 6, "block_rows": 2, "block_cols": 3, "difficulty": "easy+"}
    elif 11 <= level <= 15:
        return {"grid_size": 6, "block_rows": 2, "block_cols": 3, "difficulty": "medium"}
    elif 16 <= level <= 20:
        return {"grid_size": 6, "block_rows": 2, "block_cols": 3, "difficulty": "hard"}
    elif 21 <= level <= 25:
        return {"grid_size": 6, "block_rows": 2, "block_cols": 3, "difficulty": "expert"}
    elif 26 <= level <= 30:
        return {"grid_size": 9, "block_rows": 3, "block_cols": 3, "difficulty": "easy"}
    elif 31 <= level <= 35:
        return {"grid_size": 9, "block_rows": 3, "block_cols": 3, "difficulty": "easy+"}
    elif 36 <= level <= 40:
        return {"grid_size": 9, "block_rows": 3, "block_cols": 3, "difficulty": "medium"}
    elif 41 <= level <= 45:
        return {"grid_size": 9, "block_rows": 3, "block_cols": 3, "difficulty": "hard"}
    elif 46 <= level <= 50:
        return {"grid_size": 9, "block_rows": 3, "block_cols": 3, "difficulty": "expert"}
    else:
        return None
