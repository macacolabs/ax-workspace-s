import pygame
import random
import sys

# --- Constants ---
COLS, ROWS = 10, 20
CELL = 32
SIDEBAR = 200
WIDTH = COLS * CELL + SIDEBAR
HEIGHT = ROWS * CELL
FPS = 60

COLORS = {
    0: (30, 30, 30),
    "I": (0, 240, 240),
    "O": (240, 240, 0),
    "T": (160, 0, 240),
    "S": (0, 240, 0),
    "Z": (240, 0, 0),
    "J": (0, 0, 240),
    "L": (240, 160, 0),
    "ghost": (60, 60, 60),
    "bg": (15, 15, 15),
    "grid": (40, 40, 40),
    "sidebar": (22, 22, 22),
    "text": (220, 220, 220),
    "highlight": (240, 200, 0),
}

SHAPES = {
    "I": [[1, 1, 1, 1]],
    "O": [[1, 1], [1, 1]],
    "T": [[0, 1, 0], [1, 1, 1]],
    "S": [[0, 1, 1], [1, 1, 0]],
    "Z": [[1, 1, 0], [0, 1, 1]],
    "J": [[1, 0, 0], [1, 1, 1]],
    "L": [[0, 0, 1], [1, 1, 1]],
}

SCORE_TABLE = {1: 100, 2: 300, 3: 500, 4: 800}
LEVEL_SPEED = {1: 800, 2: 650, 3: 520, 4: 400, 5: 300, 6: 220, 7: 160, 8: 110, 9: 70, 10: 40}


def rotate_cw(matrix):
    return [list(row) for row in zip(*matrix[::-1])]


class Piece:
    def __init__(self, kind=None):
        self.kind = kind or random.choice(list(SHAPES))
        self.matrix = [row[:] for row in SHAPES[self.kind]]
        self.x = COLS // 2 - len(self.matrix[0]) // 2
        self.y = 0

    def rotated(self):
        p = Piece(self.kind)
        p.matrix = rotate_cw(self.matrix)
        p.x, p.y = self.x, self.y
        return p


class Board:
    def __init__(self):
        self.grid = [[0] * COLS for _ in range(ROWS)]

    def valid(self, piece, dx=0, dy=0):
        for r, row in enumerate(piece.matrix):
            for c, cell in enumerate(row):
                if cell:
                    nx, ny = piece.x + c + dx, piece.y + r + dy
                    if nx < 0 or nx >= COLS or ny >= ROWS:
                        return False
                    if ny >= 0 and self.grid[ny][nx]:
                        return False
        return True

    def lock(self, piece):
        for r, row in enumerate(piece.matrix):
            for c, cell in enumerate(row):
                if cell:
                    self.grid[piece.y + r][piece.x + c] = piece.kind

    def clear_lines(self):
        full = [r for r in range(ROWS) if all(self.grid[r])]
        for r in full:
            del self.grid[r]
            self.grid.insert(0, [0] * COLS)
        return len(full)

    def ghost_y(self, piece):
        dy = 0
        while self.valid(piece, dy=dy + 1):
            dy += 1
        return piece.y + dy


class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Tetris")
        self.clock = pygame.time.Clock()
        self.font_big = pygame.font.SysFont("consolas", 28, bold=True)
        self.font_med = pygame.font.SysFont("consolas", 20)
        self.font_sm = pygame.font.SysFont("consolas", 15)
        self.reset()

    def reset(self):
        self.board = Board()
        self.bag = []
        self.current = self.next_piece()
        self.held = None
        self.can_hold = True
        self.score = 0
        self.lines = 0
        self.level = 1
        self.drop_interval = LEVEL_SPEED[1]
        self.drop_timer = 0
        self.das_timer = 0
        self.das_delay = 160
        self.arr_interval = 50
        self.arr_timer = 0
        self.game_over = False
        self.paused = False

    def next_piece(self):
        if not self.bag:
            self.bag = list(SHAPES.keys()) * 1
            random.shuffle(self.bag)
        return Piece(self.bag.pop())

    def peek_next(self):
        if not self.bag:
            self.bag = list(SHAPES.keys())
            random.shuffle(self.bag)
        return self.bag[-1]

    def hold(self):
        if not self.can_hold:
            return
        if self.held:
            self.current, self.held = Piece(self.held.kind), Piece(self.current.kind)
        else:
            self.held = Piece(self.current.kind)
            self.current = self.next_piece()
        self.can_hold = False

    def hard_drop(self):
        dy = 0
        while self.board.valid(self.current, dy=dy + 1):
            dy += 1
        self.score += dy * 2
        self.current.y += dy
        self.place()

    def place(self):
        self.board.lock(self.current)
        cleared = self.board.clear_lines()
        if cleared:
            self.score += SCORE_TABLE.get(cleared, 0) * self.level
            self.lines += cleared
            self.level = min(10, self.lines // 10 + 1)
            self.drop_interval = LEVEL_SPEED[self.level]
        self.current = self.next_piece()
        self.can_hold = True
        if not self.board.valid(self.current):
            self.game_over = True

    def try_rotate(self):
        rotated = self.current.rotated()
        # Wall kick offsets
        for dx in [0, -1, 1, -2, 2]:
            if self.board.valid(rotated, dx=dx):
                rotated.x += dx
                self.current = rotated
                return

    def handle_input(self, dt):
        keys = pygame.key.get_pressed()
        move = 0
        if keys[pygame.K_LEFT]:
            move = -1
        elif keys[pygame.K_RIGHT]:
            move = 1

        if move:
            self.das_timer += dt
            if self.das_timer >= self.das_delay:
                self.arr_timer += dt
                if self.arr_timer >= self.arr_interval:
                    if self.board.valid(self.current, dx=move):
                        self.current.x += move
                    self.arr_timer = 0
        else:
            self.das_timer = 0
            self.arr_timer = 0

        if keys[pygame.K_DOWN]:
            self.drop_timer += dt * 8
        else:
            self.drop_timer += dt

    def update(self, dt):
        if self.game_over or self.paused:
            return
        self.handle_input(dt)
        if self.drop_timer >= self.drop_interval:
            self.drop_timer = 0
            if self.board.valid(self.current, dy=1):
                self.current.y += 1
            else:
                self.place()

    def draw_cell(self, surface, x, y, kind, alpha=255):
        color = COLORS.get(kind, COLORS[0])
        rect = pygame.Rect(x * CELL, y * CELL, CELL - 1, CELL - 1)
        if alpha < 255:
            s = pygame.Surface((CELL - 1, CELL - 1), pygame.SRCALPHA)
            s.fill((*color, alpha))
            surface.blit(s, (x * CELL, y * CELL))
        else:
            pygame.draw.rect(surface, color, rect)
            pygame.draw.rect(surface, tuple(min(c + 60, 255) for c in color), rect, 2)

    def draw_piece_preview(self, surface, kind, ox, oy, cell_size=24):
        matrix = SHAPES[kind]
        color = COLORS[kind]
        for r, row in enumerate(matrix):
            for c, cell in enumerate(row):
                if cell:
                    rect = pygame.Rect(ox + c * cell_size, oy + r * cell_size, cell_size - 1, cell_size - 1)
                    pygame.draw.rect(surface, color, rect)
                    pygame.draw.rect(surface, tuple(min(v + 60, 255) for v in color), rect, 1)

    def draw(self):
        self.screen.fill(COLORS["bg"])
        board_surf = self.screen.subsurface(pygame.Rect(0, 0, COLS * CELL, HEIGHT))

        # Grid lines
        for r in range(ROWS):
            for c in range(COLS):
                rect = pygame.Rect(c * CELL, r * CELL, CELL - 1, CELL - 1)
                pygame.draw.rect(board_surf, COLORS["grid"], rect, 1)

        # Locked cells
        for r in range(ROWS):
            for c in range(COLS):
                if self.board.grid[r][c]:
                    self.draw_cell(board_surf, c, r, self.board.grid[r][c])

        # Ghost
        if not self.game_over:
            gy = self.board.ghost_y(self.current)
            for r, row in enumerate(self.current.matrix):
                for c, cell in enumerate(row):
                    if cell and gy + r != self.current.y + r:
                        self.draw_cell(board_surf, self.current.x + c, gy + r, "ghost")

            # Current piece
            for r, row in enumerate(self.current.matrix):
                for c, cell in enumerate(row):
                    if cell:
                        self.draw_cell(board_surf, self.current.x + c, self.current.y + r, self.current.kind)

        # Sidebar
        sx = COLS * CELL
        sidebar = self.screen.subsurface(pygame.Rect(sx, 0, SIDEBAR, HEIGHT))
        sidebar.fill(COLORS["sidebar"])

        # Next piece
        self.render_text(sidebar, "NEXT", SIDEBAR // 2, 18, self.font_med, COLORS["highlight"], center=True)
        next_kind = self.peek_next()
        nw = len(SHAPES[next_kind][0]) * 24
        nh = len(SHAPES[next_kind]) * 24
        self.draw_piece_preview(sidebar, next_kind, (SIDEBAR - nw) // 2, 45)

        # Hold piece
        self.render_text(sidebar, "HOLD", SIDEBAR // 2, 130, self.font_med, COLORS["highlight"], center=True)
        if self.held:
            hw = len(SHAPES[self.held.kind][0]) * 24
            self.draw_piece_preview(sidebar, self.held.kind, (SIDEBAR - hw) // 2, 155)

        # Stats
        y = 240
        for label, value in [("SCORE", f"{self.score:,}"), ("LINES", str(self.lines)), ("LEVEL", str(self.level))]:
            self.render_text(sidebar, label, SIDEBAR // 2, y, self.font_sm, COLORS["text"], center=True)
            self.render_text(sidebar, value, SIDEBAR // 2, y + 18, self.font_med, COLORS["highlight"], center=True)
            y += 60

        # Controls hint
        controls = ["← → Move", "↑ Rotate", "↓ Soft drop", "Space Hard drop", "C Hold", "P Pause", "R Restart"]
        for i, line in enumerate(controls):
            self.render_text(sidebar, line, 10, HEIGHT - 130 + i * 17, self.font_sm, (100, 100, 100))

        # Overlays
        if self.game_over:
            self.draw_overlay("GAME OVER", f"Score: {self.score:,}", "R to restart")
        elif self.paused:
            self.draw_overlay("PAUSED", "", "P to resume")

        pygame.display.flip()

    def render_text(self, surface, text, x, y, font, color, center=False):
        surf = font.render(text, True, color)
        if center:
            x -= surf.get_width() // 2
        surface.blit(surf, (x, y))

    def draw_overlay(self, title, sub, hint):
        overlay = pygame.Surface((COLS * CELL, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        self.screen.blit(overlay, (0, 0))
        cx = COLS * CELL // 2
        self.render_text(self.screen, title, cx, HEIGHT // 2 - 50, self.font_big, COLORS["highlight"], center=True)
        if sub:
            self.render_text(self.screen, sub, cx, HEIGHT // 2, self.font_med, COLORS["text"], center=True)
        self.render_text(self.screen, hint, cx, HEIGHT // 2 + 40, self.font_sm, (150, 150, 150), center=True)

    def run(self):
        last_time = pygame.time.get_ticks()
        while True:
            now = pygame.time.get_ticks()
            dt = now - last_time
            last_time = now

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r:
                        self.reset()
                    elif event.key == pygame.K_p:
                        self.paused = not self.paused
                    elif not self.game_over and not self.paused:
                        if event.key == pygame.K_LEFT:
                            if self.board.valid(self.current, dx=-1):
                                self.current.x -= 1
                            self.das_timer = 0
                        elif event.key == pygame.K_RIGHT:
                            if self.board.valid(self.current, dx=1):
                                self.current.x += 1
                            self.das_timer = 0
                        elif event.key == pygame.K_UP:
                            self.try_rotate()
                        elif event.key == pygame.K_SPACE:
                            self.hard_drop()
                        elif event.key in (pygame.K_c, pygame.K_LSHIFT):
                            self.hold()

            self.update(dt)
            self.draw()
            self.clock.tick(FPS)


if __name__ == "__main__":
    Game().run()
