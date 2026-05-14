"""
Start screen and game-over screen rendering.
"""
from __future__ import annotations
import pygame
from constants import BOARD_COLS, CELL_SIZE, SCREEN_HEIGHT, Color


class ScreenDrawer:
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        pygame.font.init()
        try:
            self.font_huge   = pygame.font.SysFont("consolas", 52, bold=True)
            self.font_title  = pygame.font.SysFont("consolas", 32, bold=True)
            self.font_medium = pygame.font.SysFont("consolas", 20)
            self.font_small  = pygame.font.SysFont("consolas", 15)
        except Exception:
            self.font_huge   = pygame.font.Font(None, 64)
            self.font_title  = pygame.font.Font(None, 42)
            self.font_medium = pygame.font.Font(None, 26)
            self.font_small  = pygame.font.Font(None, 20)

    def _blit_centered(self, text: str, font: pygame.font.Font,
                        color: tuple, y: int, board_only: bool = True):
        s = font.render(text, True, color)
        cx = (BOARD_COLS * CELL_SIZE) // 2 if board_only else self.screen.get_width() // 2
        self.screen.blit(s, (cx - s.get_width() // 2, y))

    def draw_start_screen(self):
        self.screen.fill(Color.BG)
        cy = SCREEN_HEIGHT // 2
        self._blit_centered("TETRIS", self.font_huge, Color.HIGHLIGHT, cy - 100)
        self._blit_centered("Press ENTER to start", self.font_medium, Color.TEXT, cy - 10)
        self._blit_centered("R  →  Restart anytime", self.font_small, Color.TEXT_DIM, cy + 30)
        self._blit_centered("P  →  Pause / Resume",  self.font_small, Color.TEXT_DIM, cy + 52)

    def draw_gameover_screen(self, score: int, high_score: int):
        overlay = pygame.Surface(
            (BOARD_COLS * CELL_SIZE, SCREEN_HEIGHT), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 190))
        self.screen.blit(overlay, (0, 0))

        cy = SCREEN_HEIGHT // 2
        self._blit_centered("GAME OVER", self.font_title, (240, 60, 60), cy - 80)
        self._blit_centered(f"Score  {score:,}", self.font_medium, Color.HIGHLIGHT, cy - 20)
        self._blit_centered(f"Best   {high_score:,}", self.font_medium, Color.TEXT,      cy + 14)
        self._blit_centered("ENTER to play again", self.font_small, Color.TEXT_DIM, cy + 56)
        self._blit_centered("R  →  Restart",        self.font_small, Color.TEXT_DIM, cy + 78)

    def draw_pause_overlay(self):
        overlay = pygame.Surface(
            (BOARD_COLS * CELL_SIZE, SCREEN_HEIGHT), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))
        cy = SCREEN_HEIGHT // 2
        self._blit_centered("PAUSED", self.font_title, Color.HIGHLIGHT, cy - 30)
        self._blit_centered("P / Esc  →  Resume", self.font_small, Color.TEXT_DIM, cy + 20)
