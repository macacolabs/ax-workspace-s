"""
Score, level, high-score persistence.
Pure logic — no pygame dependency.
"""
import os
from constants import (
    LINE_SCORE, SOFT_DROP_SCORE, HARD_DROP_SCORE,
    LINES_PER_LEVEL, MAX_LEVEL, LEVEL_SPEEDS, HIGHSCORE_FILE
)


class ScoreManager:
    def __init__(self):
        self.score = 0
        self.lines = 0
        self.level = 1
        self.high_score = self._load_high_score()

    # --- drop scoring ---
    def add_soft_drop(self, cells: int) -> None:
        self.score += cells * SOFT_DROP_SCORE

    def add_hard_drop(self, cells: int) -> None:
        self.score += cells * HARD_DROP_SCORE

    # --- line clear scoring ---
    def add_line_clear(self, count: int) -> None:
        if count <= 0:
            return
        self.score += LINE_SCORE.get(count, 0) * self.level
        self.lines += count
        new_level = min(MAX_LEVEL, self.lines // LINES_PER_LEVEL + 1)
        self.level = new_level
        if self.score > self.high_score:
            self.high_score = self.score

    def drop_interval_ms(self) -> int:
        return LEVEL_SPEEDS.get(self.level, LEVEL_SPEEDS[MAX_LEVEL])

    def save_high_score(self) -> None:
        os.makedirs(os.path.dirname(HIGHSCORE_FILE), exist_ok=True)
        with open(HIGHSCORE_FILE, "w") as f:
            f.write(str(self.high_score))

    def _load_high_score(self) -> int:
        try:
            with open(HIGHSCORE_FILE) as f:
                return int(f.read().strip())
        except (FileNotFoundError, ValueError):
            return 0
