"""
Entry point. Wires the game loop: input → update → render.
"""
import sys
import os

# Ensure project root is on path so sub-packages resolve correctly
sys.path.insert(0, os.path.dirname(__file__))

import pygame
from constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS, WINDOW_TITLE,
    GameState
)
from engine.game import GameStateMachine
from engine.input_handler import InputHandler, Action
from ui.renderer import Renderer
from ui.screens import ScreenDrawer


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption(WINDOW_TITLE)
    clock = pygame.time.Clock()

    fsm      = GameStateMachine()
    input_h  = InputHandler()
    renderer = Renderer(screen)
    screens  = ScreenDrawer(screen)

    running = True
    while running:
        dt_ms = clock.tick(FPS)

        # --- Input ---
        events = pygame.event.get()
        actions = input_h.process_events(events)
        actions += input_h.update(dt_ms)

        for action in actions:
            result = fsm.handle_action(action)
            if result == "quit":
                running = False
                break

        # --- Update ---
        soft_dropping = (
            fsm.state == GameState.PLAYING and input_h.is_soft_dropping()
        )
        fsm.update(dt_ms, soft_dropping)

        # --- Render ---
        if fsm.state == GameState.START:
            screens.draw_start_screen()

        else:
            sess = fsm.session
            sc   = sess.scorer

            renderer.draw_board(sess.board)
            if fsm.state == GameState.PLAYING:
                renderer.draw_ghost(sess.board, sess.current)
            renderer.draw_current(sess.current)
            renderer.draw_sidebar(
                next_kind  = sess.peek_next(),
                held_kind  = sess.held.kind if sess.held else None,
                score      = sc.score,
                high_score = sc.high_score,
                level      = sc.level,
                lines      = sc.lines,
            )

            if fsm.state == GameState.PAUSED:
                screens.draw_pause_overlay()
            elif fsm.state == GameState.GAMEOVER:
                screens.draw_gameover_screen(sc.score, sc.high_score)

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
