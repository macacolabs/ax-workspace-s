"""
Tetromino definitions and SRS (Super Rotation System) wall-kick data.
Pure logic — no pygame dependency.
"""
from __future__ import annotations
import random
from constants import PIECE_KINDS, BOARD_COLS

# Shape matrices: each is a list of (row, col) offsets from pivot
# Using the standard Tetris Guideline spawn orientations.
_SHAPES: dict[str, list[list[int]]] = {
    "I": [[0,0,0,0],
          [1,1,1,1],
          [0,0,0,0],
          [0,0,0,0]],

    "O": [[1,1],
          [1,1]],

    "T": [[0,1,0],
          [1,1,1],
          [0,0,0]],

    "S": [[0,1,1],
          [1,1,0],
          [0,0,0]],

    "Z": [[1,1,0],
          [0,1,1],
          [0,0,0]],

    "J": [[1,0,0],
          [1,1,1],
          [0,0,0]],

    "L": [[0,0,1],
          [1,1,1],
          [0,0,0]],
}

# SRS wall-kick offsets: (from_rotation, to_rotation) → list of (dx, dy) to try
# J, L, S, T, Z share one table; I has its own.
_KICKS_JLSTZ: dict[tuple[int,int], list[tuple[int,int]]] = {
    (0,1): [(0,0),(-1,0),(-1, 1),(0,-2),(-1,-2)],
    (1,0): [(0,0),( 1,0),( 1,-1),(0, 2),( 1, 2)],
    (1,2): [(0,0),( 1,0),( 1,-1),(0, 2),( 1, 2)],
    (2,1): [(0,0),(-1,0),(-1, 1),(0,-2),(-1,-2)],
    (2,3): [(0,0),( 1,0),( 1, 1),(0,-2),( 1,-2)],
    (3,2): [(0,0),(-1,0),(-1,-1),(0, 2),(-1, 2)],
    (3,0): [(0,0),(-1,0),(-1,-1),(0, 2),(-1, 2)],
    (0,3): [(0,0),( 1,0),( 1, 1),(0,-2),( 1,-2)],
}

_KICKS_I: dict[tuple[int,int], list[tuple[int,int]]] = {
    (0,1): [(0,0),(-2,0),( 1,0),(-2,-1),( 1, 2)],
    (1,0): [(0,0),( 2,0),(-1,0),( 2, 1),(-1,-2)],
    (1,2): [(0,0),(-1,0),( 2,0),(-1, 2),( 2,-1)],
    (2,1): [(0,0),( 1,0),(-2,0),( 1,-2),(-2, 1)],
    (2,3): [(0,0),( 2,0),(-1,0),( 2, 1),(-1,-2)],
    (3,2): [(0,0),(-2,0),( 1,0),(-2,-1),( 1, 2)],
    (3,0): [(0,0),( 1,0),(-2,0),( 1,-2),(-2, 1)],
    (0,3): [(0,0),(-1,0),( 2,0),(-1, 2),( 2,-1)],
}


def _rotate_cw(matrix: list[list[int]]) -> list[list[int]]:
    return [list(row) for row in zip(*matrix[::-1])]


class Piece:
    def __init__(self, kind: str):
        self.kind = kind
        self.rotation = 0
        # Build all 4 rotations upfront
        base = [row[:] for row in _SHAPES[kind]]
        self._rotations: list[list[list[int]]] = [base]
        for _ in range(3):
            base = _rotate_cw(base)
            self._rotations.append(base)

        # Spawn position: centered horizontally, just above visible board
        self.matrix = self._rotations[0]
        cols = len(self.matrix[0])
        self.x = BOARD_COLS // 2 - cols // 2
        self.y = 0  # caller offsets by hidden rows if needed

    @property
    def cells(self) -> list[tuple[int,int]]:
        """Return (row, col) of filled cells in board coordinates."""
        result = []
        for r, row in enumerate(self.matrix):
            for c, v in enumerate(row):
                if v:
                    result.append((self.y + r, self.x + c))
        return result

    def get_kicks(self, next_rot: int) -> list[tuple[int,int]]:
        table = _KICKS_I if self.kind == "I" else _KICKS_JLSTZ
        return table.get((self.rotation, next_rot), [(0, 0)])

    def rotated(self, direction: int = 1) -> "Piece":
        """Return a new Piece with rotation applied (does not mutate self)."""
        p = Piece.__new__(Piece)
        p.kind = self.kind
        p._rotations = self._rotations
        p.rotation = (self.rotation + direction) % 4
        p.matrix = self._rotations[p.rotation]
        p.x = self.x
        p.y = self.y
        return p

    def moved(self, dx: int = 0, dy: int = 0) -> "Piece":
        p = Piece.__new__(Piece)
        p.kind = self.kind
        p._rotations = self._rotations
        p.rotation = self.rotation
        p.matrix = self.matrix
        p.x = self.x + dx
        p.y = self.y + dy
        return p


class Bag:
    """7-bag random generator — guarantees each piece appears once per bag."""
    def __init__(self):
        self._bag: list[str] = []
        self._next_bag: list[str] = []
        self._fill()
        self._fill_next()

    def _fill(self):
        self._bag = list(PIECE_KINDS)
        random.shuffle(self._bag)

    def _fill_next(self):
        self._next_bag = list(PIECE_KINDS)
        random.shuffle(self._next_bag)

    def peek(self, count: int = 1) -> list[str]:
        result = self._bag[-count:] if count <= len(self._bag) else (
            self._bag + self._next_bag[-(count - len(self._bag)):]
        )
        return list(reversed(result[:count]))

    def pop(self) -> str:
        if not self._bag:
            self._bag = self._next_bag
            self._fill_next()
        kind = self._bag.pop()
        return kind
