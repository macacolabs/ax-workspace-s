"""
Translates raw pygame key events into game actions.
Handles DAS (Delayed Auto Shift) and ARR (Auto Repeat Rate).
"""
import pygame
from constants import DAS_DELAY, ARR_INTERVAL


class Action:
    MOVE_LEFT  = "move_left"
    MOVE_RIGHT = "move_right"
    SOFT_DROP  = "soft_drop"
    HARD_DROP  = "hard_drop"
    ROTATE_CW  = "rotate_cw"
    ROTATE_CCW = "rotate_ccw"
    HOLD       = "hold"
    PAUSE      = "pause"
    START      = "start"
    RESTART    = "restart"
    QUIT       = "quit"


_KEYDOWN_MAP = {
    pygame.K_UP:     Action.ROTATE_CW,
    pygame.K_x:      Action.ROTATE_CW,
    pygame.K_z:      Action.ROTATE_CCW,
    pygame.K_SPACE:  Action.HARD_DROP,
    pygame.K_c:      Action.HOLD,
    pygame.K_LSHIFT: Action.HOLD,
    pygame.K_RSHIFT: Action.HOLD,
    pygame.K_p:      Action.PAUSE,
    pygame.K_ESCAPE: Action.PAUSE,
    pygame.K_RETURN: Action.START,
    pygame.K_r:      Action.RESTART,
}


class InputHandler:
    def __init__(self):
        self._das_dir: int = 0          # -1 left, +1 right, 0 none
        self._das_timer: float = 0.0
        self._arr_timer: float = 0.0

    def reset(self):
        self._das_dir = 0
        self._das_timer = 0.0
        self._arr_timer = 0.0

    def process_events(self, events: list) -> list[str]:
        actions = []
        for event in events:
            if event.type == pygame.QUIT:
                actions.append(Action.QUIT)
            elif event.type == pygame.KEYDOWN:
                action = _KEYDOWN_MAP.get(event.key)
                if action:
                    actions.append(action)
                # DAS: first press fires immediately
                if event.key == pygame.K_LEFT:
                    actions.append(Action.MOVE_LEFT)
                    self._das_dir = -1
                    self._das_timer = 0.0
                    self._arr_timer = 0.0
                elif event.key == pygame.K_RIGHT:
                    actions.append(Action.MOVE_RIGHT)
                    self._das_dir = 1
                    self._das_timer = 0.0
                    self._arr_timer = 0.0
            elif event.type == pygame.KEYUP:
                if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    keys = pygame.key.get_pressed()
                    if keys[pygame.K_LEFT]:
                        self._das_dir = -1
                        self._das_timer = 0.0
                    elif keys[pygame.K_RIGHT]:
                        self._das_dir = 1
                        self._das_timer = 0.0
                    else:
                        self._das_dir = 0
        return actions

    def update(self, dt_ms: float) -> list[str]:
        """Call each frame to get DAS/ARR repeated move actions."""
        if self._das_dir == 0:
            return []
        self._das_timer += dt_ms
        if self._das_timer < DAS_DELAY:
            return []
        self._arr_timer += dt_ms
        actions = []
        while self._arr_timer >= ARR_INTERVAL:
            self._arr_timer -= ARR_INTERVAL
            actions.append(Action.MOVE_LEFT if self._das_dir == -1 else Action.MOVE_RIGHT)
        return actions

    def is_soft_dropping(self) -> bool:
        keys = pygame.key.get_pressed()
        return bool(keys[pygame.K_DOWN])
