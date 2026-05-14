"""
All pygame drawing. Knows nothing about game logic — only reads state.
"""
from __future__ import annotations
import pygame
from constants import (
    BOARD_COLS, BOARD_ROWS, CELL_SIZE, SIDEBAR_WIDTH,
    SCREEN_WIDTH, SCREEN_HEIGHT, Color
)
from core.piece import Piece
from core.board import Board


def _lighten(color: tuple, amount: int = 50) -> tuple:
    return tuple(min(255, c + amount) for c in color[:3])


class Renderer:
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.board_surf = screen.subsurface(pygame.Rect(0, 0, BOARD_COLS * CELL_SIZE, SCREEN_HEIGHT))
        self.sidebar_surf = screen.subsurface(
            pygame.Rect(BOARD_COLS * CELL_SIZE, 0, SIDEBAR_WIDTH, SCREEN_HEIGHT)
        )
        self._init_fonts()

    def _init_fonts(self):
        pygame.font.init()
        try:
            self.font_title  = pygame.font.SysFont("consolas", 32, bold=True)
            self.font_large  = pygame.font.SysFont("consolas", 24, bold=True)
            self.font_medium = pygame.font.SysFont("consolas", 18)
            self.font_small  = pygame.font.SysFont("consolas", 13)
        except Exception:
            self.font_title  = pygame.font.Font(None, 40)
            self.font_large  = pygame.font.Font(None, 30)
            self.font_medium = pygame.font.Font(None, 22)
            self.font_small  = pygame.font.Font(None, 16)

    # --- primitives ---
    def _draw_cell(self, surf: pygame.Surface, col: int, row: int,
                   color: tuple, border: bool = True):
        x = col * CELL_SIZE
        y = row * CELL_SIZE
        rect = pygame.Rect(x, y, CELL_SIZE - 1, CELL_SIZE - 1)
        pygame.draw.rect(surf, color, rect)
        if border:
            pygame.draw.rect(surf, _lighten(color, 55), rect, 2)

    def _text(self, surf: pygame.Surface, text: str, x: int, y: int,
              font: pygame.font.Font, color: tuple, center: bool = False):
        s = font.render(text, True, color)
        if center:
            x -= s.get_width() // 2
        surf.blit(s, (x, y))

    def _draw_piece_preview(self, surf: pygame.Surface, kind: str,
                             ox: int, oy: int, cell: int = 22):
        from core.piece import _SHAPES
        matrix = _SHAPES[kind]
        color = Color.PIECES[kind]
        for r, row in enumerate(matrix):
            for c, v in enumerate(row):
                if v:
                    rect = pygame.Rect(ox + c * cell, oy + r * cell, cell - 1, cell - 1)
                    pygame.draw.rect(surf, color, rect)
                    pygame.draw.rect(surf, _lighten(color), rect, 1)

    # --- board ---
    def draw_board(self, board: Board):
        self.board_surf.fill(Color.BG)
        visible = board.visible_rows()
        for r in range(BOARD_ROWS):
            for c in range(BOARD_COLS):
                cell_val = visible[r][c]
                if cell_val:
                    self._draw_cell(self.board_surf, c, r, Color.PIECES[cell_val])
                else:
                    rect = pygame.Rect(c * CELL_SIZE, r * CELL_SIZE, CELL_SIZE - 1, CELL_SIZE - 1)
                    pygame.draw.rect(self.board_surf, Color.GRID, rect, 1)

    def draw_ghost(self, board: Board, current: Piece):
        ghost = board.ghost(current)
        from constants import BOARD_HIDDEN_ROWS
        for gr, gc in ghost.cells:
            vis_r = gr - BOARD_HIDDEN_ROWS
            if 0 <= vis_r < BOARD_ROWS:
                # only draw ghost where current piece isn't
                if (gr, gc) not in set(current.cells):
                    self._draw_cell(self.board_surf, gc, vis_r, Color.GHOST, border=False)

    def draw_current(self, current: Piece):
        from constants import BOARD_HIDDEN_ROWS
        color = Color.PIECES[current.kind]
        for r, c in current.cells:
            vis_r = r - BOARD_HIDDEN_ROWS
            if 0 <= vis_r < BOARD_ROWS:
                self._draw_cell(self.board_surf, c, vis_r, color)

    # --- sidebar ---
    def draw_sidebar(self, next_kind: str, held_kind: str | None,
                     score: int, high_score: int, level: int, lines: int):
        sb = self.sidebar_surf
        sb.fill(Color.SIDEBAR_BG)
        cx = SIDEBAR_WIDTH // 2

        # separator line
        pygame.draw.line(sb, Color.BORDER, (0, 0), (0, SCREEN_HEIGHT), 2)

        y = 14
        # --- NEXT ---
        self._text(sb, "NEXT", cx, y, self.font_medium, Color.HIGHLIGHT, center=True)
        y += 26
        from core.piece import _SHAPES
        nw = len(_SHAPES[next_kind][0]) * 22
        self._draw_piece_preview(sb, next_kind, (SIDEBAR_WIDTH - nw) // 2, y)
        y += 80

        # --- HOLD ---
        self._text(sb, "HOLD", cx, y, self.font_medium, Color.HIGHLIGHT, center=True)
        y += 26
        if held_kind:
            hw = len(_SHAPES[held_kind][0]) * 22
            self._draw_piece_preview(sb, held_kind, (SIDEBAR_WIDTH - hw) // 2, y)
        else:
            self._text(sb, "---", cx, y + 10, self.font_small, Color.TEXT_DIM, center=True)
        y += 80

        # --- Stats ---
        for label, value in [
            ("SCORE",  f"{score:,}"),
            ("BEST",   f"{high_score:,}"),
            ("LEVEL",  str(level)),
            ("LINES",  str(lines)),
        ]:
            self._text(sb, label, cx, y, self.font_small, Color.TEXT_DIM, center=True)
            y += 16
            self._text(sb, value, cx, y, self.font_large, Color.HIGHLIGHT, center=True)
            y += 32

        # --- Controls ---
        controls = [
            ("← →",   "Move"),
            ("↑ / X",  "Rotate CW"),
            ("Z",      "Rotate CCW"),
            ("↓",      "Soft Drop"),
            ("Space",  "Hard Drop"),
            ("C/Shift","Hold"),
            ("P/Esc",  "Pause"),
            ("R",      "Restart"),
        ]
        y = SCREEN_HEIGHT - len(controls) * 18 - 10
        pygame.draw.line(sb, Color.BORDER, (10, y - 8), (SIDEBAR_WIDTH - 10, y - 8), 1)
        for key, desc in controls:
            self._text(sb, f"{key:<8} {desc}", 12, y, self.font_small, Color.TEXT_DIM)
            y += 18

    # --- overlay helpers ---
    def draw_overlay(self, lines: list[tuple[str, pygame.font.Font, tuple]]):
        overlay = pygame.Surface((BOARD_COLS * CELL_SIZE, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill(Color.OVERLAY)
        self.screen.blit(overlay, (0, 0))
        cx = BOARD_COLS * CELL_SIZE // 2
        total_h = sum(f.get_height() + 12 for _, f, _ in lines)
        y = SCREEN_HEIGHT // 2 - total_h // 2
        for text, font, color in lines:
            s = font.render(text, True, color)
            self.screen.blit(s, (cx - s.get_width() // 2, y))
            y += s.get_height() + 12
