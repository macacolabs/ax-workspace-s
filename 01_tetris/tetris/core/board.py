"""
Board grid, collision detection, line clearing.
Pure logic — no pygame dependency.
"""
from __future__ import annotations
from constants import BOARD_COLS, BOARD_ROWS, BOARD_HIDDEN_ROWS
from core.piece import Piece

TOTAL_ROWS = BOARD_ROWS + BOARD_HIDDEN_ROWS


class Board:
    def __init__(self):
        # grid[0] = top-most hidden row, grid[TOTAL_ROWS-1] = bottom
        self.grid: list[list[str | int]] = [[0] * BOARD_COLS for _ in range(TOTAL_ROWS)]

    def is_valid(self, piece: Piece) -> bool:
        for r, c in piece.cells:
            if c < 0 or c >= BOARD_COLS:
                return False
            if r >= TOTAL_ROWS:
                return False
            if r >= 0 and self.grid[r][c]:
                return False
        return True

    def ghost(self, piece: Piece) -> Piece:
        p = piece
        while self.is_valid(p.moved(dy=1)):
            p = p.moved(dy=1)
        return p

    def lock(self, piece: Piece) -> None:
        for r, c in piece.cells:
            if 0 <= r < TOTAL_ROWS:
                self.grid[r][c] = piece.kind

    def clear_lines(self) -> int:
        """Remove full rows, shift down, return count cleared."""
        full = [r for r in range(TOTAL_ROWS) if all(self.grid[r])]
        for r in full:
            del self.grid[r]
            self.grid.insert(0, [0] * BOARD_COLS)
        return len(full)

    def is_topped_out(self) -> bool:
        """True if any cell in the hidden rows is filled."""
        return any(self.grid[r][c] for r in range(BOARD_HIDDEN_ROWS) for c in range(BOARD_COLS))

    def visible_rows(self) -> list[list[str | int]]:
        """Return only the BOARD_ROWS visible rows (skip hidden area)."""
        return self.grid[BOARD_HIDDEN_ROWS:]
