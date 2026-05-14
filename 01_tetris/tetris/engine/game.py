"""
Game state machine: START → PLAYING ↔ PAUSED → GAMEOVER → (restart) → PLAYING
Owns the board, current/next/held pieces, scoring, and drop timing.
"""
from __future__ import annotations
from constants import GameState, BOARD_HIDDEN_ROWS, SOFT_DROP_FACTOR
from core.board import Board
from core.piece import Piece, Bag
from core.scoring import ScoreManager
from engine.input_handler import Action


class GameSession:
    """One complete game (board + pieces + score). Reuse via reset()."""

    def __init__(self):
        self.scorer = ScoreManager()
        self._reset_session()

    def _reset_session(self):
        self.board = Board()
        self.bag = Bag()
        self.current: Piece = self._spawn(self.bag.pop())
        self.held: Piece | None = None
        self.can_hold = True
        self._drop_timer: float = 0.0
        self._lock_timer: float = 0.0
        self._lock_max_resets = 15
        self._lock_resets_left = self._lock_max_resets
        self._on_ground = False

    def reset(self):
        self.scorer = ScoreManager()
        self._reset_session()

    # --- spawn ---
    def _spawn(self, kind: str) -> Piece:
        p = Piece(kind)
        p.y -= BOARD_HIDDEN_ROWS  # shift into hidden area so it appears at top
        p.y = max(0, p.y)        # clamp to row 0 in total grid coords
        return p

    def peek_next(self) -> str:
        return self.bag.peek(1)[0]

    # --- actions ---
    def apply_action(self, action: str) -> None:
        if action == Action.MOVE_LEFT:
            self._try_move(-1, 0)
        elif action == Action.MOVE_RIGHT:
            self._try_move(1, 0)
        elif action == Action.ROTATE_CW:
            self._try_rotate(1)
        elif action == Action.ROTATE_CCW:
            self._try_rotate(-1)
        elif action == Action.HARD_DROP:
            self._hard_drop()
        elif action == Action.HOLD:
            self._do_hold()

    def _try_move(self, dx: int, dy: int) -> bool:
        candidate = self.current.moved(dx, dy)
        if self.board.is_valid(candidate):
            self.current = candidate
            if dy == 0 and self._on_ground:  # lateral move resets lock
                self._reset_lock()
            return True
        return False

    def _try_rotate(self, direction: int) -> bool:
        rotated = self.current.rotated(direction)
        next_rot = rotated.rotation
        for dx, dy in self.current.get_kicks(next_rot):
            candidate = rotated.moved(dx, dy)
            if self.board.is_valid(candidate):
                self.current = candidate
                if self._on_ground:
                    self._reset_lock()
                return True
        return False

    def _hard_drop(self):
        ghost = self.board.ghost(self.current)
        cells_dropped = ghost.y - self.current.y
        self.scorer.add_hard_drop(cells_dropped)
        self.current = ghost
        self._lock_piece()

    def _do_hold(self):
        if not self.can_hold:
            return
        kind = self.current.kind
        if self.held is None:
            self.current = self._spawn(self.bag.pop())
        else:
            self.current = self._spawn(self.held.kind)
        self.held = Piece(kind)
        self.can_hold = False
        self._drop_timer = 0.0
        self._on_ground = False

    def _lock_piece(self):
        self.board.lock(self.current)
        cleared = self.board.clear_lines()
        self.scorer.add_line_clear(cleared)
        self.current = self._spawn(self.bag.pop())
        self.can_hold = True
        self._drop_timer = 0.0
        self._lock_timer = 0.0
        self._lock_resets_left = self._lock_max_resets
        self._on_ground = False

    def _reset_lock(self):
        if self._lock_resets_left > 0:
            self._lock_timer = 0.0
            self._lock_resets_left -= 1

    # --- update ---
    def update(self, dt_ms: float, soft_dropping: bool) -> bool:
        """
        Advance game by dt_ms milliseconds.
        Returns True if game-over condition is met.
        """
        interval = self.scorer.drop_interval_ms()
        if soft_dropping:
            interval = max(1, interval // SOFT_DROP_FACTOR)

        self._drop_timer += dt_ms
        moved_down = False
        while self._drop_timer >= interval:
            self._drop_timer -= interval
            if self._try_move(0, 1):
                moved_down = True
                if soft_dropping:
                    self.scorer.add_soft_drop(1)
            else:
                break

        # Lock delay
        on_ground = not self.board.is_valid(self.current.moved(dy=1))
        if on_ground != self._on_ground:
            self._on_ground = on_ground
            self._lock_timer = 0.0

        if on_ground:
            self._lock_timer += dt_ms
            lock_delay = 500  # ms
            if self._lock_timer >= lock_delay:
                self._lock_piece()

        # Game over check: new piece immediately invalid OR hidden rows occupied
        if self.board.is_topped_out() or not self.board.is_valid(self.current):
            return True
        return False


class GameStateMachine:
    """Top-level state machine wiring GameSession + state transitions."""

    def __init__(self):
        self.state = GameState.START
        self.session = GameSession()

    def start_game(self):
        self.session.reset()
        self.state = GameState.PLAYING

    def toggle_pause(self):
        if self.state == GameState.PLAYING:
            self.state = GameState.PAUSED
        elif self.state == GameState.PAUSED:
            self.state = GameState.PLAYING

    def handle_action(self, action: str):
        if action == Action.QUIT:
            return "quit"
        if action == Action.RESTART:
            self.start_game()
            return
        if self.state == GameState.START:
            if action == Action.START:
                self.start_game()
        elif self.state == GameState.PLAYING:
            if action == Action.PAUSE:
                self.toggle_pause()
            else:
                self.session.apply_action(action)
        elif self.state == GameState.PAUSED:
            if action == Action.PAUSE:
                self.toggle_pause()
        elif self.state == GameState.GAMEOVER:
            if action == Action.START:
                self.start_game()

    def update(self, dt_ms: float, soft_dropping: bool):
        if self.state != GameState.PLAYING:
            return
        game_over = self.session.update(dt_ms, soft_dropping)
        if game_over:
            self.session.scorer.save_high_score()
            self.state = GameState.GAMEOVER
