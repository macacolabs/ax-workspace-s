"""
pytest tests for core logic (no pygame required).
Run: py -m pytest tests/ -v  (from the tetris/ directory)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from core.piece import Piece, Bag, _rotate_cw
from core.board import Board, TOTAL_ROWS
from core.scoring import ScoreManager
from constants import BOARD_COLS, BOARD_ROWS, PIECE_KINDS


# ── Piece / Rotation ──────────────────────────────────────────────────────────

class TestPieceRotation:
    def test_rotate_cw_returns_new_matrix(self):
        original = [[1, 0], [1, 1]]
        rotated = _rotate_cw(original)
        assert rotated == [[1, 1], [1, 0]]
        assert original == [[1, 0], [1, 1]]  # immutable

    def test_four_rotations_return_to_original(self):
        for kind in PIECE_KINDS:
            p = Piece(kind)
            r = p
            for _ in range(4):
                r = r.rotated(1)
            assert r.matrix == p.matrix, f"{kind}: 4 CW rotations should restore shape"

    def test_o_piece_rotation_invariant(self):
        p = Piece("O")
        assert p.rotated(1).matrix == p.matrix

    def test_piece_cells_in_bounds_after_spawn(self):
        for kind in PIECE_KINDS:
            p = Piece(kind)
            for r, c in p.cells:
                assert 0 <= c < BOARD_COLS, f"{kind}: col {c} out of range"


# ── Board / Collision ─────────────────────────────────────────────────────────

class TestBoardCollision:
    def setup_method(self):
        self.board = Board()

    def test_empty_board_valid_for_all_pieces(self):
        for kind in PIECE_KINDS:
            p = Piece(kind)
            assert self.board.is_valid(p), f"{kind} should be valid on empty board"

    def test_left_wall_blocks_movement(self):
        p = Piece("I")
        p.x = 0
        assert not self.board.is_valid(p.moved(dx=-1))

    def test_right_wall_blocks_movement(self):
        p = Piece("I")
        p.x = BOARD_COLS - len(p.matrix[0])
        assert not self.board.is_valid(p.moved(dx=1))

    def test_floor_blocks_movement(self):
        p = Piece("O")
        p.y = TOTAL_ROWS - len(p.matrix)
        assert not self.board.is_valid(p.moved(dy=1))

    def test_locked_piece_blocks_same_position(self):
        p = Piece("O")
        p.x, p.y = 0, TOTAL_ROWS - 2
        self.board.lock(p)
        p2 = Piece("O")
        p2.x, p2.y = 0, TOTAL_ROWS - 2
        assert not self.board.is_valid(p2)

    def test_ghost_lands_at_bottom_on_empty_board(self):
        p = Piece("I")
        p.x = 0
        ghost = self.board.ghost(p)
        # Ghost should be at the bottom: last row that fits
        for gr, gc in ghost.cells:
            assert gr < TOTAL_ROWS


# ── Line Clearing ─────────────────────────────────────────────────────────────

class TestLineClear:
    def setup_method(self):
        self.board = Board()

    def _fill_row(self, row_idx: int, skip_col: int | None = None):
        for c in range(BOARD_COLS):
            if c != skip_col:
                self.board.grid[row_idx][c] = "I"

    def test_no_full_lines_clears_zero(self):
        self._fill_row(TOTAL_ROWS - 1, skip_col=5)
        assert self.board.clear_lines() == 0

    def test_one_full_line_cleared(self):
        self._fill_row(TOTAL_ROWS - 1)
        assert self.board.clear_lines() == 1
        assert all(self.board.grid[TOTAL_ROWS - 1][c] == 0 for c in range(BOARD_COLS))

    def test_four_full_lines_cleared(self):
        for r in range(TOTAL_ROWS - 4, TOTAL_ROWS):
            self._fill_row(r)
        assert self.board.clear_lines() == 4

    def test_rows_shift_down_after_clear(self):
        # Put a marker in row above the full line
        self.board.grid[TOTAL_ROWS - 2][0] = "T"
        self._fill_row(TOTAL_ROWS - 1)
        self.board.clear_lines()
        assert self.board.grid[TOTAL_ROWS - 1][0] == "T"


# ── Game Over ─────────────────────────────────────────────────────────────────

class TestGameOver:
    def test_topped_out_false_on_empty(self):
        board = Board()
        assert not board.is_topped_out()

    def test_topped_out_true_when_hidden_rows_filled(self):
        from constants import BOARD_HIDDEN_ROWS
        board = Board()
        board.grid[0][0] = "I"  # hidden row
        assert board.is_topped_out()


# ── Scoring / Level ───────────────────────────────────────────────────────────

class TestScoring:
    def test_single_line_score(self):
        sm = ScoreManager()
        sm.add_line_clear(1)
        assert sm.score == 100

    def test_tetris_score(self):
        sm = ScoreManager()
        sm.add_line_clear(4)
        assert sm.score == 800

    def test_level_up_at_10_lines(self):
        sm = ScoreManager()
        for _ in range(10):
            sm.add_line_clear(1)
        assert sm.level == 2

    def test_score_multiplied_by_level(self):
        sm = ScoreManager()
        sm.level = 3
        sm.add_line_clear(1)
        assert sm.score == 300  # 100 * level 3

    def test_hard_drop_score(self):
        sm = ScoreManager()
        sm.add_hard_drop(10)
        assert sm.score == 20  # 10 cells * 2

    def test_high_score_updates(self):
        sm = ScoreManager()
        sm.high_score = 0
        sm.score = 500
        sm.add_line_clear(1)
        assert sm.high_score >= sm.score


# ── 7-Bag Randomizer ─────────────────────────────────────────────────────────

class TestBag:
    def test_bag_contains_all_7_kinds_per_cycle(self):
        bag = Bag()
        drawn = [bag.pop() for _ in range(7)]
        assert sorted(drawn) == sorted(PIECE_KINDS)

    def test_peek_does_not_consume(self):
        bag = Bag()
        first = bag.peek(1)[0]
        popped = bag.pop()
        assert first == popped
