from enum import Enum, auto

# --- Board ---
BOARD_COLS = 10
BOARD_ROWS = 20
BOARD_HIDDEN_ROWS = 2  # rows above visible area for spawn

# --- Display ---
CELL_SIZE = 32
SIDEBAR_WIDTH = 200
SCREEN_WIDTH = BOARD_COLS * CELL_SIZE + SIDEBAR_WIDTH
SCREEN_HEIGHT = BOARD_ROWS * CELL_SIZE
FPS = 60

# --- Timing (ms) ---
DAS_DELAY = 167       # delay before auto-repeat starts
ARR_INTERVAL = 33     # auto-repeat interval
SOFT_DROP_FACTOR = 8  # multiplier on normal drop speed
LOCK_DELAY = 500      # ms before piece locks after landing

# --- Level speed table (ms per row drop) ---
LEVEL_SPEEDS = {
    1: 800, 2: 717, 3: 633, 4: 550, 5: 467,
    6: 383, 7: 300, 8: 217, 9: 133, 10: 100,
    11: 83,  12: 67,  13: 50,  14: 33,  15: 17,
}
MAX_LEVEL = 15
LINES_PER_LEVEL = 10

# --- Scoring (Guideline) ---
LINE_SCORE = {1: 100, 2: 300, 3: 500, 4: 800}
SOFT_DROP_SCORE = 1   # per cell
HARD_DROP_SCORE = 2   # per cell

# --- Colors (R, G, B) ---
class Color:
    BG          = (15,  15,  15)
    GRID        = (35,  35,  35)
    SIDEBAR_BG  = (22,  22,  22)
    TEXT        = (220, 220, 220)
    TEXT_DIM    = (100, 100, 100)
    HIGHLIGHT   = (240, 200,   0)
    GHOST       = (55,  55,  55)
    BORDER      = (60,  60,  60)
    OVERLAY     = (0,   0,   0, 180)  # RGBA
    WHITE       = (255, 255, 255)

    PIECES = {
        "I": (0,   240, 240),
        "O": (240, 240,   0),
        "T": (160,   0, 240),
        "S": (0,   240,   0),
        "Z": (240,   0,   0),
        "J": (0,     0, 240),
        "L": (240, 160,   0),
    }

# --- Game States ---
class GameState(Enum):
    START    = auto()
    PLAYING  = auto()
    PAUSED   = auto()
    GAMEOVER = auto()

# --- Piece kinds ---
PIECE_KINDS = list("IOTSZJL")

# --- Files ---
HIGHSCORE_FILE = "data/highscore.dat"
WINDOW_TITLE = "Tetris"
