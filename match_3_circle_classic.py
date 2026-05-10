#!/usr/bin/env python3
# =============================================================================
# Match 3 — Full Powerup Edition
#
# HOW TO PLAY:
#   Click a gem to select it (yellow ring), then click an adjacent gem to swap.
#   Match 3+ gems of the same color in a row or column to clear them.
#   Clearing gems damages the tiles underneath them (center 6x6 area).
#   WIN when all tile layers in the center 6x6 are cleared.
#
# POWERUPS — created automatically by special matches:
#   LINE BOMB  (match exactly 4)     gold ring  + cross symbol
#   COLOR BOMB (match 5 or more)     pink ring  + star dots
#   AREA BOMB  (match L or T shape)  teal ring  + square symbol
#
# POWERUP ACTIVATION:
#   - Double-click a powerup to fire it immediately
#   - Swap a powerup with any normal gem to fire it
#   - Swap two powerups together to FUSE them (stronger effect)
#
# FUSION TABLE (swap powerup A with powerup B):
#   Line  + Line  → Cross Bomb  — full row AND column
#   Line  + Area  → Mega Area   — 5x5 blast
#   Line  + Color → Color Line  — all gems of that color + their rows/cols
#   Area  + Area  → Mega Area   — 5x5 blast
#   Area  + Color → Color Area  — all gems of that color + 3x3 around each
#   Color + Color → Wipe Board  — clears the entire board
#
# LEVEL = number of layers on each center tile (higher = more hits needed)
# DIFFICULTY = number of gem colors in play (higher = harder to match)
#
# Controls: Mouse only | ESC = return to menu anytime
# High score saved to match3_highscore.json next to this script.
# To run: python3 match3.py
# =============================================================================

import pygame
import random
import sys
import json
import os
import math

# ── CONSTANTS ─────────────────────────────────────────────────────────────────

GRID      = 8               # 8x8 board
CELL      = 64              # pixels per cell
GRID_PX   = GRID * CELL     # 512px total grid size
TOP_BAR   = 80              # height of score/progress bar above the grid
SCREEN_W  = GRID_PX
SCREEN_H  = GRID_PX + TOP_BAR

GEM_R     = 24              # gem circle radius in pixels
MIN_MATCH = 3               # minimum gems in a line to count as a match

# Animation durations in milliseconds — tweak these for feel
SWAP_MS   = 220             # swap slide animation duration
FLASH_MS  = 520             # matched gems flash white before clearing
FALL_MS   = 280             # gems fall down after a clear

# UI / background colors
BG        = (15,  12,  30)
GRID_BG   = (22,  18,  42)
GRID_LINE = (38,  32,  60)
WHITE     = (255, 255, 255)
GRAY      = (130, 120, 150)
SEL_COL   = (255, 240,  80)  # yellow — selected gem ring + hint highlight

# Tile colors are computed dynamically in draw_tile() based on layers remaining
# 0 layers = green (cleared), many layers = dark red, fades to purple near last hit

# Powerup glow ring colors — one per powerup type, drawn around the gem
POWERUP_COLORS = {
    "line":  (255, 220,  50),   # gold
    "color": (255, 100, 255),   # magenta
    "area":  (100, 255, 200),   # teal
}

# All 10 possible gem colors ordered from easiest-to-distinguish to hardest
# Difficulty setting slices this list: difficulty 3 uses only the first 3 colors
ALL_GEM_COLORS = [
    (230,  55,  55),  # 0 red
    (55,  130, 235),  # 1 blue
    (55,  210,  75),  # 2 green
    (235, 185,  35),  # 3 yellow
    (185,  55, 235),  # 4 purple
    (235, 110,  35),  # 5 orange
    (40,  200, 200),  # 6 cyan
    (235,  80, 160),  # 7 pink
    (140, 200,  40),  # 8 lime
    (255, 255, 255),  # 9 white
]

# Active gem colors — updated at game start based on difficulty selection
GEM_COLORS = ALL_GEM_COLORS[:5]
NUM_GEMS   = len(GEM_COLORS)

# Active level — updated at game start. Controls how many tile layers each
# center tile starts with. Level 1 = 1 hit per tile, Level 50 = 50 hits.
LEVEL = 1

# High score file — saved next to the script, falls back to cwd if unavailable
try:
    SCORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "match3_highscore.json")
except NameError:
    SCORE_FILE = os.path.join(os.getcwd(), "match3_highscore.json")


# ── HIGH SCORE ────────────────────────────────────────────────────────────────

def load_highscore():
    try:
        with open(SCORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("highscore", 0)
    except Exception:
        return 0

def save_highscore(score):
    try:
        with open(SCORE_FILE, "w", encoding="utf-8") as f:
            json.dump({"highscore": score}, f)
    except Exception:
        pass


# ── GEM DATA STRUCTURE ────────────────────────────────────────────────────────
# Each cell in the grid stores a dict with two fields:
#   "color" : int  — index into GEM_COLORS (0 to NUM_GEMS-1)
#   "power" : str|None — None = normal gem, or "line"/"color"/"area" = powerup
#
# Helper functions wrap the dict so the rest of the code never touches it raw.

def make_gem(color, power=None):
    # Create a new gem dict. power=None means a regular gem.
    return {"color": color, "power": power}

def gem_color(g):
    # Safe accessor — returns color index, or None if g is None
    return g["color"] if g else None

def gem_power(g):
    # Safe accessor — returns power string or None
    return g["power"] if g else None

def is_powerup(g):
    # Returns True if this gem has a powerup type set
    return g is not None and g["power"] is not None


# ── GRID LOGIC ────────────────────────────────────────────────────────────────

def make_grid():
    # Build a fresh 8x8 gem grid with no pre-existing matches and no powerups.
    # Uses a simple backtracking approach: for each cell, remove colors that
    # would immediately create a run of 3 to the left or above.
    gems = [[None]*GRID for _ in range(GRID)]
    for r in range(GRID):
        for c in range(GRID):
            choices = list(range(NUM_GEMS))
            # Exclude color if 2 to the left are the same
            if c >= 2 and gem_color(gems[r][c-1]) == gem_color(gems[r][c-2]):
                choices = [x for x in choices if x != gem_color(gems[r][c-1])]
            # Exclude color if 2 above are the same
            if r >= 2 and gem_color(gems[r-1][c]) == gem_color(gems[r-2][c]):
                choices = [x for x in choices if x != gem_color(gems[r-1][c])]
            gems[r][c] = make_gem(random.choice(choices) if choices else random.randrange(NUM_GEMS))

    # Build tile grid — only center 6x6 (rows 1-6, cols 1-6) starts with layers.
    # Outer border starts at 0 (already cleared) to avoid unwinnable corners.
    # Each tile starts with LEVEL layers — each match on that tile removes 1 layer.
    tiles = [[0]*GRID for _ in range(GRID)]
    for r in range(1, GRID-1):
        for c in range(1, GRID-1):
            tiles[r][c] = LEVEL

    return gems, tiles

def find_matches(gems):
    # Scan the grid for all runs of 3+ same-color gems (horizontal and vertical).
    # Powerup gems are NOT counted as part of any run — they break runs.
    #
    # Returns:
    #   matched : set of (r,c) — all cells that are part of a match
    #   runs    : list of dicts {"cells": [(r,c),...], "dir": "h"|"v"}
    #             used by detect_powerup_type() to figure out what powerup to spawn
    matched = set()
    runs    = []

    # Horizontal scan — row by row
    for r in range(GRID):
        c = 0
        while c < GRID:
            run = 1
            # Extend run as long as same color AND neither gem is a powerup
            while c + run < GRID \
                  and gem_color(gems[r][c+run]) == gem_color(gems[r][c]) \
                  and not is_powerup(gems[r][c+run]) \
                  and not is_powerup(gems[r][c]):
                run += 1
            if run >= MIN_MATCH:
                cells = [(r, c+k) for k in range(run)]
                for cell in cells: matched.add(cell)
                runs.append({"cells": cells, "dir": "h"})
            c += run  # skip past this run entirely

    # Vertical scan — column by column
    for c in range(GRID):
        r = 0
        while r < GRID:
            run = 1
            while r + run < GRID \
                  and gem_color(gems[r+run][c]) == gem_color(gems[r][c]) \
                  and not is_powerup(gems[r+run][c]) \
                  and not is_powerup(gems[r][c]):
                run += 1
            if run >= MIN_MATCH:
                cells = [(r+k, c) for k in range(run)]
                for cell in cells: matched.add(cell)
                runs.append({"cells": cells, "dir": "v"})
            r += run

    return matched, runs

def detect_powerup_type(runs, swap_cell):
    # Given the runs created by a swap, decide what powerup (if any) to create.
    # swap_cell = (r,c) of the gem the player just swapped — powerup spawns here.
    #
    # Priority:
    #   1. L or T shape (a horizontal and vertical run share a cell) → area bomb
    #   2. Match 5+  → color bomb
    #   3. Match 4   → line bomb
    #   4. Match 3   → no powerup

    # Check for L/T: find a horizontal and vertical run that share any cell
    h_sets = [set(run["cells"]) for run in runs if run["dir"] == "h"]
    v_sets = [set(run["cells"]) for run in runs if run["dir"] == "v"]
    for h in h_sets:
        for v in v_sets:
            if h & v:  # they share at least one cell = L or T shape
                return "area", swap_cell

    # Check for long runs — color bomb beats line bomb
    best_power = None
    for run in runs:
        n = len(run["cells"])
        if n >= 5:
            best_power = "color"
        elif n == 4 and best_power != "color":
            best_power = "line"

    if best_power:
        # Spawn at the swapped cell if it was part of the run
        for run in runs:
            if swap_cell and swap_cell in run["cells"]:
                return best_power, swap_cell
        # Fallback: center cell of the first qualifying run
        for run in runs:
            if len(run["cells"]) >= (5 if best_power == "color" else 4):
                mid = run["cells"][len(run["cells"])//2]
                return best_power, mid

    return None, None

def apply_gravity(gems):
    # Drop all gems down to fill gaps (None cells) left after a clear.
    # Works column by column: collect non-None gems, pad the top with None.
    for c in range(GRID):
        col    = [gems[r][c] for r in range(GRID) if gems[r][c] is not None]
        padded = [None] * (GRID - len(col)) + col
        for r in range(GRID):
            gems[r][c] = padded[r]

def fill_empty(gems):
    # Fill any remaining None cells at the top with fresh random gems (no powerups)
    for r in range(GRID):
        for c in range(GRID):
            if gems[r][c] is None:
                gems[r][c] = make_gem(random.randrange(NUM_GEMS))

def damage_tiles(tiles, cells):
    # Remove one layer from each tile in the given cell set.
    # Tiles at 0 are already fully cleared — they can't go below 0.
    for r, c in cells:
        if 0 <= r < GRID and 0 <= c < GRID:
            if tiles[r][c] > 0:
                tiles[r][c] -= 1

def tiles_cleared(tiles):
    # Win condition: all center 6x6 tiles are at 0 layers
    return all(tiles[r][c] == 0 for r in range(1, GRID-1) for c in range(1, GRID-1))

def has_any_move(gems):
    # Check if any valid swap exists on the board.
    # A valid swap is one that either creates a match OR involves a powerup.
    # Used for game over detection — if False, no moves left.
    for r in range(GRID):
        for c in range(GRID):
            if c + 1 < GRID:
                gems[r][c], gems[r][c+1] = gems[r][c+1], gems[r][c]
                m, _ = find_matches(gems)
                has_p = is_powerup(gems[r][c]) or is_powerup(gems[r][c+1])
                gems[r][c], gems[r][c+1] = gems[r][c+1], gems[r][c]
                if m or has_p: return True
            if r + 1 < GRID:
                gems[r][c], gems[r+1][c] = gems[r+1][c], gems[r][c]
                m, _ = find_matches(gems)
                has_p = is_powerup(gems[r][c]) or is_powerup(gems[r+1][c])
                gems[r][c], gems[r+1][c] = gems[r+1][c], gems[r][c]
                if m or has_p: return True
    return False

def find_hint(gems):
    # Find the first valid swap and return the two cells as a list.
    # Powerup cells are always valid hints — any swap with them does something.
    # Returns [] if no valid moves exist.
    for r in range(GRID):
        for c in range(GRID):
            if c + 1 < GRID:
                if is_powerup(gems[r][c]) or is_powerup(gems[r][c+1]):
                    return [(r,c), (r,c+1)]
                gems[r][c], gems[r][c+1] = gems[r][c+1], gems[r][c]
                m, _ = find_matches(gems)
                gems[r][c], gems[r][c+1] = gems[r][c+1], gems[r][c]
                if m: return [(r,c), (r,c+1)]
            if r + 1 < GRID:
                if is_powerup(gems[r][c]) or is_powerup(gems[r+1][c]):
                    return [(r,c), (r+1,c)]
                gems[r][c], gems[r+1][c] = gems[r+1][c], gems[r][c]
                m, _ = find_matches(gems)
                gems[r][c], gems[r+1][c] = gems[r+1][c], gems[r][c]
                if m: return [(r,c), (r+1,c)]
    return []

def do_shuffle(gems):
    # Reshuffle all gems randomly.
    # Tries up to 200 times to find a layout with no existing matches
    # AND at least one valid move. Falls back to a plain shuffle if it fails
    # (should be extremely rare).
    flat = [gems[r][c] for r in range(GRID) for c in range(GRID)]
    for _ in range(200):
        random.shuffle(flat)
        for r in range(GRID):
            for c in range(GRID):
                gems[r][c] = flat[r*GRID+c]
        m, _ = find_matches(gems)
        if not m and has_any_move(gems):
            return
    # Fallback — just shuffle without guarantee
    random.shuffle(flat)
    for r in range(GRID):
        for c in range(GRID):
            gems[r][c] = flat[r*GRID+c]

def score_for_match(n_cells, chain):
    # Score formula:
    #   Base:        10 per gem cleared
    #   Size bonus:  +10 for each gem beyond the minimum 3
    #   Chain bonus: +30 per chain level above 1 (chain 2 = +30, chain 3 = +60...)
    return n_cells*10 + max(0, n_cells - MIN_MATCH)*10 + max(0, chain-1)*30


# ── POWERUP ACTIVATION ────────────────────────────────────────────────────────

def activate_powerup(gems, r, c, tiles):
    # Fire a single powerup at (r,c) and return the set of cells it will clear.
    # The powerup gem itself is always included in the clear set.
    power = gem_power(gems[r][c])
    color = gem_color(gems[r][c])
    cells = set()

    if power == "line":
        # Clears the entire row OR column — picks whichever damages more tiles
        row_dmg = sum(1 for cc in range(GRID) if tiles[r][cc] > 0)
        col_dmg = sum(1 for rr in range(GRID) if tiles[rr][c] > 0)
        if col_dmg >= row_dmg:
            cells = {(rr, c) for rr in range(GRID)}   # vertical
        else:
            cells = {(r, cc) for cc in range(GRID)}   # horizontal

    elif power == "color":
        # Clears ALL gems on the board that share this powerup's color
        cells = {(rr, cc) for rr in range(GRID) for cc in range(GRID)
                 if gem_color(gems[rr][cc]) == color}

    elif power == "area":
        # Clears a 3x3 area centered on this powerup
        cells = {(rr, cc) for rr in range(r-1, r+2) for cc in range(c-1, c+2)
                 if 0 <= rr < GRID and 0 <= cc < GRID}

    cells.add((r, c))  # always clear the powerup itself
    return cells

def fuse_powerups(gems, r_a, c_a, r_b, c_b, tiles):
    # Fuse two powerups that were swapped together — returns the combined clear set.
    # Uses frozenset to make the combination order-independent (A+B == B+A).
    p_a   = gem_power(gems[r_a][c_a])
    p_b   = gem_power(gems[r_b][c_b])
    col_a = gem_color(gems[r_a][c_a])   # color used for color-based fusions
    pair  = frozenset([p_a, p_b])
    cells = set()

    if pair == frozenset(["line", "line"]):
        # Cross bomb — full row AND full column of both powerup positions
        for cc in range(GRID): cells.add((r_a, cc)); cells.add((r_b, cc))
        for rr in range(GRID): cells.add((rr, c_a)); cells.add((rr, c_b))

    elif pair in (frozenset(["line", "area"]), frozenset(["area", "area"])):
        # Mega area — 5x5 blast centered between the two powerups
        cr = (r_a + r_b) // 2
        cc = (c_a + c_b) // 2
        cells = {(rr, ccc) for rr in range(cr-2, cr+3)
                            for ccc in range(cc-2, cc+3)
                            if 0 <= rr < GRID and 0 <= ccc < GRID}

    elif pair == frozenset(["line", "color"]):
        # Color Line — every gem matching the powerup color + their full row and col
        for rr in range(GRID):
            for cc in range(GRID):
                if gem_color(gems[rr][cc]) == col_a:
                    cells.add((rr, cc))
                    for ccc in range(GRID): cells.add((rr, ccc))   # full row
                    for rrr in range(GRID): cells.add((rrr, cc))   # full col

    elif pair == frozenset(["area", "color"]):
        # Color Area — every gem matching the powerup color + 3x3 around each
        for rr in range(GRID):
            for cc in range(GRID):
                if gem_color(gems[rr][cc]) == col_a:
                    for dr in range(-1, 2):
                        for dc in range(-1, 2):
                            nr, nc = rr+dr, cc+dc
                            if 0 <= nr < GRID and 0 <= nc < GRID:
                                cells.add((nr, nc))

    elif pair == frozenset(["color", "color"]):
        # Wipe board — clears every single cell
        cells = {(rr, cc) for rr in range(GRID) for cc in range(GRID)}

    # Always clear both powerup gems themselves
    cells.add((r_a, c_a))
    cells.add((r_b, c_b))
    return cells


# ── DRAW HELPERS ──────────────────────────────────────────────────────────────

def cell_center(r, c):
    # Returns the pixel (x, y) center of a grid cell
    return c*CELL + CELL//2, TOP_BAR + r*CELL + CELL//2

def draw_tile(surface, r, c, tile_val):
    # Draw the tile background for a cell.
    # Color gradient based on layers remaining vs LEVEL:
    #   0 layers (cleared) = green
    #   many layers        = dark red
    #   few layers left    = bright purple
    x, y = c*CELL, TOP_BAR + r*CELL
    if tile_val == 0:
        color = (40, 160, 80)   # fully cleared = green
    else:
        # t = 1.0 at full layers, approaches 0 at last layer
        t = min(1.0, tile_val / max(1, LEVEL))
        if t > 0.5:
            # Dark red → purple (many layers remaining)
            s = (t - 0.5) * 2
            color = (int(160*s + 120*(1-s)), int(20*s + 40*(1-s)), int(20*s + 160*(1-s)))
        else:
            # Purple → bright purple (few layers remaining)
            s = t * 2
            color = (int(120*s + 180*(1-s)), int(40*s + 60*(1-s)), int(160*s + 220*(1-s)))

    pygame.draw.rect(surface, color, (x+2, y+2, CELL-4, CELL-4), border_radius=6)

    # Show layer count number on tile when more than 1 layer remains
    if tile_val > 1:
        fnt = pygame.font.SysFont("monospace", 14, bold=True)
        txt = fnt.render(str(tile_val), True, (255,255,255))
        surface.blit(txt, txt.get_rect(center=(x + CELL//2, y + CELL//2 + 18)))

def draw_gem(surface, g, cx, cy, radius=GEM_R, selected=False, flash=0):
    # Draw a gem at pixel position (cx, cy).
    # selected=True  → yellow selection ring drawn around it
    # powerup gem    → colored glow ring + symbol inside
    # flash=0..200   → white overlay during match flash animation
    if g is None: return
    color = GEM_COLORS[gem_color(g)]
    r, g2, b = color
    power = gem_power(g)

    # Yellow selection ring (also used for hint highlight)
    if selected:
        s = pygame.Surface((radius*2+12, radius*2+12), pygame.SRCALPHA)
        pygame.draw.circle(s, (*SEL_COL, 200), (radius+6, radius+6), radius+5)
        surface.blit(s, (cx-radius-6, cy-radius-6))

    # Powerup glow ring — color depends on type
    if power:
        pcol = POWERUP_COLORS[power]
        s    = pygame.Surface((radius*2+8, radius*2+8), pygame.SRCALPHA)
        pygame.draw.circle(s, (*pcol, 220), (radius+4, radius+4), radius+3)
        surface.blit(s, (cx-radius-4, cy-radius-4))

    # Main gem circle
    pygame.draw.circle(surface, (r, g2, b), (cx, cy), radius)

    # Powerup symbol drawn inside the gem for quick identification
    if power == "line":
        # Cross — suggests row/col clearing
        pygame.draw.line(surface, WHITE, (cx-radius+4, cy), (cx+radius-4, cy), 3)
        pygame.draw.line(surface, WHITE, (cx, cy-radius+4), (cx, cy+radius-4), 3)
    elif power == "color":
        # Pentagon of dots — suggests multiple targets
        for i in range(5):
            angle = math.radians(i * 72)
            dx = int(math.cos(angle) * (radius//2))
            dy = int(math.sin(angle) * (radius//2))
            pygame.draw.circle(surface, WHITE, (cx+dx, cy+dy), 3)
    elif power == "area":
        # Small square — suggests area blast
        hw = radius//2 - 2
        pygame.draw.rect(surface, WHITE, (cx-hw, cy-hw, hw*2, hw*2), 2)

    # Shine highlight — lighter circle in top-left for 3D look
    shine_col = (min(255,r+90), min(255,g2+90), min(255,b+90))
    pygame.draw.circle(surface, shine_col, (cx-radius//3, cy-radius//3), radius//3)

    # White flash overlay — fades in at start of match flash, used during "flashing" state
    if flash > 0:
        s = pygame.Surface((radius*2+4, radius*2+4), pygame.SRCALPHA)
        pygame.draw.circle(s, (255, 255, 255, flash), (radius+2, radius+2), radius)
        surface.blit(s, (cx-radius-2, cy-radius-2))

def draw_text_centered(surface, font, text, color, y):
    surf = font.render(text, True, color)
    surface.blit(surf, surf.get_rect(center=(SCREEN_W//2, y)))


# ── FLOAT TEXT ────────────────────────────────────────────────────────────────
# Floating "+score" text that drifts upward and fades out after a match.

class FloatText:
    def __init__(self, text, x, y, color=WHITE, duration=900):
        self.text     = text
        self.x        = float(x)
        self.y        = float(y)
        self.color    = color
        self.duration = duration
        self.timer    = duration   # counts down to 0 then removed

    def update(self, dt):
        self.timer -= dt
        self.y     -= 50 * dt / 1000   # drift upward at 50px/sec

    @property
    def alive(self): return self.timer > 0

    @property
    def alpha(self): return max(0, int(255 * self.timer / self.duration))


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    # Declare module-level globals that get updated when a game starts
    # (difficulty and level change GEM_COLORS, NUM_GEMS, LEVEL globally
    #  so that make_grid() and draw functions pick up the new values)
    global GEM_COLORS, NUM_GEMS, LEVEL

    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Match 3")
    clock  = pygame.time.Clock()

    font_big   = pygame.font.SysFont("monospace", 46, bold=True)
    font_med   = pygame.font.SysFont("monospace", 24, bold=True)
    font_small = pygame.font.SysFont("monospace", 18)
    font_score = pygame.font.SysFont("monospace", 22, bold=True)

    highscore  = load_highscore()
    difficulty = 5   # number of gem colors (1–10), chosen on start screen
    level      = 1   # tile layers per center tile (1–50), chosen on start screen

    # ── game variables ──
    gems, tiles   = make_grid()
    score         = 0
    selected      = None        # (r,c) of currently selected gem, or None
    float_texts   = []          # active floating score popups
    chain         = 0           # current chain count — resets when combo ends
    new_best      = False       # True if score beat highscore this game
    hint_cells    = []          # [(r,c),(r,c)] of hinted swap, [] = no hint active
    shuffles      = 3           # shuffle uses remaining this game

    # ── state machine ──
    # "start"     — difficulty/level selection screen
    # "playing"   — waiting for player input
    # "swapping"  — swap slide animation playing
    # "reverting" — invalid swap sliding back to original position
    # "flashing"  — matched/cleared gems flashing white before being removed
    # "falling"   — new gems falling down after a clear
    # "win"       — all center tiles cleared, show win screen
    # "gameover"  — no valid moves remain
    state      = "start"
    anim_timer = 0   # countdown timer for current animation state (ms)

    # Swap animation
    swap_a = None   # (r,c) of first gem in swap
    swap_b = None   # (r,c) of second gem in swap
    swap_t = 0.0    # animation progress: 0.0=start, 1.0=complete

    # Cells currently flashing before being cleared
    matched_cells = set()

    # Fall animation tracking
    fall_offsets = [[0.0]*GRID for _ in range(GRID)]  # reserved for future per-cell offsets
    fall_rows    = [0]*GRID    # per-column: how many cells each column's gems fell

    # ── inner helpers ──

    def pixel_to_cell(mx, my):
        # Convert screen pixel (mx, my) → grid (row, col), or None if outside grid
        if my < TOP_BAR: return None
        r = (my - TOP_BAR) // CELL
        c = mx // CELL
        if 0 <= r < GRID and 0 <= c < GRID: return r, c
        return None

    def add_float(text, cells, color=WHITE):
        # Spawn a floating score text at the average pixel position of a cell set
        if not cells: return
        ar = sum(r for r,c in cells) / len(cells)
        ac = sum(c for r,c in cells) / len(cells)
        fx, fy = cell_center(ar, ac)
        float_texts.append(FloatText(text, fx, fy, color))

    def process_clear(cells, ch, label_override=None):
        # Called whenever gems are confirmed cleared (match, powerup, or fusion).
        # Scores the clear, damages tiles, spawns float text, saves highscore.
        # Also checks for win IMMEDIATELY — don't wait for combo to finish.
        nonlocal score, new_best, state
        pts   = score_for_match(len(cells), ch)
        score += pts
        damage_tiles(tiles, cells)
        color = SEL_COL if ch > 1 else WHITE
        label = label_override or (f"+{pts}" if ch <= 1 else f"CHAIN x{ch}! +{pts}")
        add_float(label, cells, color)
        if score > highscore:
            save_highscore(score)
            new_best = True
        # Immediate win check — triggers even mid-combo
        if tiles_cleared(tiles):
            state = "win"

    def start_flash(cells, ch, label=None):
        # Begin the flash animation for a set of cells about to be cleared.
        # Sets matched_cells, resets anim_timer, transitions to "flashing" state.
        nonlocal matched_cells, anim_timer, state, chain
        chain         = ch
        matched_cells = set(cells)
        anim_timer    = FLASH_MS
        state         = "flashing"
        process_clear(cells, ch, label)

    def resolve_swap(a, b):
        # Called after a swap animation completes — determines what happens.
        # Three cases in priority order:
        #   1. Both gems are powerups → FUSE them
        #   2. One gem is a powerup   → activate it
        #   3. Neither is a powerup  → check for normal match, revert if none
        nonlocal state, swap_t, swap_a, swap_b, chain

        ga = gems[a[0]][a[1]]
        gb = gems[b[0]][b[1]]

        if is_powerup(ga) and is_powerup(gb):
            # Both powerups — fuse and activate combined effect
            cells = fuse_powerups(gems, a[0], a[1], b[0], b[1], tiles)
            pa, pb = gem_power(ga), gem_power(gb)
            start_flash(cells, 1, f"FUSE {pa}+{pb}! +{score_for_match(len(cells),1)}")
            return

        if is_powerup(ga):
            cells = activate_powerup(gems, a[0], a[1], tiles)
            start_flash(cells, 1, f"{gem_power(ga).upper()}! +{score_for_match(len(cells),1)}")
            return

        if is_powerup(gb):
            cells = activate_powerup(gems, b[0], b[1], tiles)
            start_flash(cells, 1, f"{gem_power(gb).upper()}! +{score_for_match(len(cells),1)}")
            return

        # Normal match check
        matched, runs = find_matches(gems)
        if matched:
            # Check if the match qualifies for a powerup spawn
            power_type, power_cell = detect_powerup_type(runs, b)
            cells_to_clear = set(matched)
            if power_type and power_cell:
                # Don't clear the spawn cell — upgrade it to a powerup gem instead
                cells_to_clear.discard(power_cell)
                pr, pc = power_cell
                gems[pr][pc] = make_gem(gem_color(gems[pr][pc]), power_type)
            chain = 1
            start_flash(cells_to_clear, 1)
        else:
            # No match and no powerup — undo the swap
            gems[a[0]][a[1]], gems[b[0]][b[1]] = gems[b[0]][b[1]], gems[a[0]][a[1]]
            swap_a, swap_b = b, a   # reverse direction for revert animation
            swap_t = 0.0
            state  = "reverting"

    def start_new_game():
        # Reset all game variables and build a fresh grid.
        # Called when START is pressed or Next Level is clicked.
        nonlocal gems, tiles, score, selected, float_texts, chain
        nonlocal new_best, hint_cells, shuffles, fall_offsets, fall_rows, state
        gems, tiles  = make_grid()
        score        = 0
        selected     = None
        float_texts  = []
        chain        = 0
        new_best     = False
        hint_cells   = []
        shuffles     = 3
        fall_offsets = [[0.0]*GRID for _ in range(GRID)]
        fall_rows    = [0]*GRID
        state        = "playing"

    # ── main loop ─────────────────────────────────────────────────────────────
    while True:
        dt = clock.tick(60)   # cap at 60 FPS, dt = ms since last frame

        # ── event handling ────────────────────────────────────────────────────
        for event in pygame.event.get():

            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit(0)

            if event.type == pygame.KEYDOWN:
                if state == "start":
                    pass   # start screen is mouse-only
                elif state in ("win", "gameover"):
                    if event.key == pygame.K_r:
                        state = "start"   # R = back to menu
                    elif event.key in (pygame.K_q, pygame.K_ESCAPE):
                        pygame.quit(); sys.exit(0)

            # ESC mid-game → return to menu, works even during animations/combos
            if state in ("playing","swapping","reverting","flashing","falling") \
               and event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                state = "start"; selected = None; hint_cells = []; matched_cells = set()

            # ── start screen clicks ──
            if state == "start" and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                # Difficulty left/right arrows
                if 180 <= mx <= 230 and 328 <= my <= 368:
                    difficulty = max(1, difficulty-1)
                elif 280 <= mx <= 330 and 328 <= my <= 368:
                    difficulty = min(10, difficulty+1)
                # Level left/right arrows
                elif 180 <= mx <= 230 and 408 <= my <= 448:
                    level = max(1, level-1)
                elif 280 <= mx <= 330 and 408 <= my <= 448:
                    level = min(50, level+1)
                # START button — apply selections and begin game
                elif 180 <= mx <= 332 and 455 <= my <= 493:
                    GEM_COLORS = ALL_GEM_COLORS[:difficulty]
                    NUM_GEMS   = difficulty
                    LEVEL      = level
                    start_new_game()

            # ── next level button on win screen ──
            if state == "win" and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                if 156 <= mx <= 356 and 345 <= my <= 383:
                    level += 1
                    LEVEL  = level
                    GEM_COLORS = ALL_GEM_COLORS[:difficulty]
                    NUM_GEMS   = difficulty
                    start_new_game()

            if state != "playing": continue

            # ── playing state clicks ──
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx2, my2 = event.pos
                cell = pixel_to_cell(mx2, my2)

                # Top bar button region
                if my2 < TOP_BAR:
                    # HINT — highlights a valid swap pair in yellow
                    if SCREEN_W-140 <= mx2 <= SCREEN_W-75 and 8 <= my2 <= 38:
                        hint_cells = find_hint(gems)
                    # SHUFFLE — reshuffles the board (limited uses)
                    elif SCREEN_W-70 <= mx2 <= SCREEN_W-5 and 8 <= my2 <= 38:
                        if shuffles > 0:
                            shuffles -= 1; hint_cells = []; do_shuffle(gems)
                    continue

                if my2 > TOP_BAR + GRID_PX - 1: continue
                if cell is None: selected = None; continue

                hint_cells = []   # any board click clears hint highlight

                if selected is None:
                    selected = cell   # first click — select this gem
                elif cell == selected:
                    # Clicked same gem again
                    if is_powerup(gems[cell[0]][cell[1]]):
                        # Double-click powerup = activate it directly
                        cells = activate_powerup(gems, cell[0], cell[1], tiles)
                        start_flash(cells, 1, f"{gem_power(gems[cell[0]][cell[1]]).upper()}!")
                        selected = None
                    else:
                        selected = None   # deselect normal gem
                else:
                    dr = abs(cell[0]-selected[0])
                    dc = abs(cell[1]-selected[1])
                    if dr + dc == 1:
                        # Adjacent gem clicked — commit swap and start animation
                        gems[selected[0]][selected[1]], gems[cell[0]][cell[1]] = \
                            gems[cell[0]][cell[1]], gems[selected[0]][selected[1]]
                        swap_a = selected; swap_b = cell; swap_t = 0.0
                        selected = None; state = "swapping"
                    else:
                        selected = cell   # not adjacent — select new gem instead

        # ── animation state updates ───────────────────────────────────────────

        if state == "swapping":
            # Advance swap slide progress (0 → 1)
            swap_t += dt / SWAP_MS
            if swap_t >= 1.0:
                swap_t = 1.0
                resolve_swap(swap_a, swap_b)   # decide what happens after swap

        elif state == "reverting":
            # Slide back to original position (1 → 0)
            swap_t -= dt / SWAP_MS
            if swap_t <= 0.0:
                swap_t = 0.0; state = "playing"

        elif state == "flashing":
            # Countdown before clearing matched_cells
            anim_timer -= dt
            if anim_timer <= 0:
                # Count cleared cells per column for fall animation
                cleared_per_col = [0]*GRID
                for r, c in matched_cells:
                    if gems[r][c] is not None:
                        cleared_per_col[c] += 1
                        gems[r][c] = None      # remove cleared gem
                matched_cells = set()
                apply_gravity(gems)            # drop remaining gems down
                fill_empty(gems)               # fill top with new gems
                fall_rows  = [cleared_per_col[c] for c in range(GRID)]
                state      = "falling"
                anim_timer = FALL_MS

        elif state == "falling":
            # Countdown for gems to visually land
            anim_timer -= dt
            if anim_timer <= 0:
                fall_offsets = [[0.0]*GRID for _ in range(GRID)]
                fall_rows    = [0]*GRID
                # Check for chain matches after gems settled
                new_m, new_runs = find_matches(gems)
                if new_m:
                    # Chain match found — check for powerup spawn, then flash again
                    power_type, power_cell = detect_powerup_type(new_runs, None)
                    cells_to_clear = set(new_m)
                    if power_type and power_cell:
                        cells_to_clear.discard(power_cell)
                        pr, pc = power_cell
                        gems[pr][pc] = make_gem(gem_color(gems[pr][pc]), power_type)
                    chain += 1
                    start_flash(cells_to_clear, chain)
                else:
                    # No chain — combo over, check end conditions
                    chain = 0; state = "playing"
                    if tiles_cleared(tiles): state = "win"
                    elif not has_any_move(gems): state = "gameover"

        # Update floating score texts — remove dead ones
        float_texts = [ft for ft in float_texts if ft.alive]
        for ft in float_texts: ft.update(dt)

        # ── draw ──────────────────────────────────────────────────────────────
        screen.fill(BG)

        # ── start screen ──
        if state == "start":
            draw_text_centered(screen, font_big,   "MATCH 3",                 (180,100,255), 120)
            draw_text_centered(screen, font_small, "Match 4 = Line Bomb",     (255,220,50),  205)
            draw_text_centered(screen, font_small, "Match 5 = Color Bomb",    (255,100,255), 237)
            draw_text_centered(screen, font_small, "Match L/T = Area Bomb",   (100,255,200), 269)
            draw_text_centered(screen, font_small, "Swap 2 powerups to FUSE", WHITE,         301)

            # Difficulty selector — left/right arrows + number + color dots preview
            draw_text_centered(screen, font_med, "Colors (Difficulty)", GRAY, 318)
            pygame.draw.polygon(screen, WHITE, [(230,328),(180,348),(230,368)])   # left arrow
            pygame.draw.polygon(screen, WHITE, [(282,328),(332,348),(282,368)])   # right arrow
            diff_surf = font_big.render(str(difficulty), True, SEL_COL)
            screen.blit(diff_surf, diff_surf.get_rect(center=(SCREEN_W//2, 348)))
            dot_r = 9; spacing = dot_r*2+4
            sx = SCREEN_W//2 - (difficulty-1)*spacing//2
            for i in range(difficulty):
                pygame.draw.circle(screen, ALL_GEM_COLORS[i], (sx+i*spacing, 375), dot_r)

            # Level selector — left/right arrows + number
            draw_text_centered(screen, font_med, "Level (Tile Layers)", GRAY, 398)
            pygame.draw.polygon(screen, WHITE, [(230,408),(180,428),(230,448)])   # left arrow
            pygame.draw.polygon(screen, WHITE, [(282,408),(332,428),(282,448)])   # right arrow
            lvl_surf = font_big.render(str(level), True, (100,255,200))
            screen.blit(lvl_surf, lvl_surf.get_rect(center=(SCREEN_W//2, 428)))

            # START button
            pygame.draw.rect(screen, (180,100,255), (180,455,152,38), border_radius=8)
            draw_text_centered(screen, font_med, "START", WHITE, 474)

            if highscore > 0:
                draw_text_centered(screen, font_small, f"Best: {highscore}", (255,200,50), 505)

        else:
            # ── top bar ──
            pygame.draw.rect(screen, (20,16,38), (0, 0, SCREEN_W, TOP_BAR))
            screen.blit(font_med.render(f"Score: {score}", True, WHITE), (10, 10))

            # Level / difficulty indicator in center of top bar
            lvl_txt = font_small.render(f"Lv.{level}  D.{difficulty}", True, (100,255,200))
            screen.blit(lvl_txt, (SCREEN_W//2 - lvl_txt.get_width()//2, 14))

            # HINT button — turns yellow when a hint is active
            hint_col = SEL_COL if hint_cells else (100,180,255)
            pygame.draw.rect(screen, hint_col, (SCREEN_W-140, 8, 60, 30), border_radius=5)
            hs = font_small.render("HINT", True, BG)
            screen.blit(hs, hs.get_rect(center=(SCREEN_W-110, 23)))

            # SHUFFLE button — grays out when no uses remain
            shuf_col = (100,200,100) if shuffles > 0 else (60,80,60)
            pygame.draw.rect(screen, shuf_col, (SCREEN_W-70, 8, 62, 30), border_radius=5)
            ss = font_small.render(f"x{shuffles}", True, BG)
            screen.blit(ss, ss.get_rect(center=(SCREEN_W-39, 23)))

            # Tile progress bar — shows total layer hits cleared vs total needed
            total_t   = (GRID-2) * (GRID-2) * LEVEL   # 36 tiles * layers each
            cleared_t = sum(LEVEL - tiles[r][c] for r in range(1,GRID-1) for c in range(1,GRID-1))
            bw, bh    = SCREEN_W-20, 14
            bx, by    = 10, 52
            pygame.draw.rect(screen, (80,30,110), (bx, by, bw, bh), border_radius=4)  # empty bar bg
            fw = int(bw * cleared_t / total_t)
            if fw > 0:
                pygame.draw.rect(screen, (55,210,75), (bx, by, fw, bh), border_radius=4)
            ps = font_small.render(f"{cleared_t}/{total_t}", True, GRAY)
            screen.blit(ps, (bx+bw-ps.get_width(), by-18))

            # ── grid ──
            pygame.draw.rect(screen, GRID_BG, (0, TOP_BAR, GRID_PX, GRID_PX))

            # Draw tile backgrounds first — gems sit visually on top of them
            for r in range(GRID):
                for c in range(GRID):
                    draw_tile(screen, r, c, tiles[r][c])

            # Grid lines
            for i in range(GRID+1):
                pygame.draw.line(screen, GRID_LINE, (i*CELL, TOP_BAR), (i*CELL, TOP_BAR+GRID_PX))
                pygame.draw.line(screen, GRID_LINE, (0, TOP_BAR+i*CELL), (GRID_PX, TOP_BAR+i*CELL))

            # Fall animation progress — 0.0=just started falling, 1.0=landed
            fall_progress = 1.0 - max(0.0, anim_timer/FALL_MS) if state == "falling" else 1.0

            # ── draw gems ──
            for r in range(GRID):
                for c in range(GRID):
                    if gems[r][c] is None: continue
                    cx, cy = cell_center(r, c)

                    # Swap/revert animation — offset gem toward its destination
                    if state in ("swapping", "reverting"):
                        t = swap_t
                        if (r,c) == swap_a:
                            cx += int((swap_b[1]-swap_a[1]) * CELL * t)
                            cy += int((swap_b[0]-swap_a[0]) * CELL * t)
                        elif (r,c) == swap_b:
                            cx += int((swap_a[1]-swap_b[1]) * CELL * t)
                            cy += int((swap_a[0]-swap_b[0]) * CELL * t)

                    # Fall animation — gems start above their target and fall down
                    # fall_rows[c] = how many cells this column's gems dropped
                    if state == "falling" and fall_rows[c] > 0:
                        cy -= int(CELL * fall_rows[c] * (1.0 - fall_progress))

                    is_sel   = (selected == (r,c)) or ((r,c) in hint_cells)
                    is_match = (r,c) in matched_cells
                    # Flash intensity — max at start of flash, fades to 0
                    flash_v  = int(200*(anim_timer/FLASH_MS)) if is_match and state=="flashing" and anim_timer>0 else 0

                    draw_gem(screen, gems[r][c], cx, cy, selected=is_sel, flash=flash_v)

            # ── floating score texts ──
            for ft in float_texts:
                s  = font_score.render(ft.text, True, ft.color)
                ts = pygame.Surface(s.get_size(), pygame.SRCALPHA)
                ts.blit(s, (0,0)); ts.set_alpha(ft.alpha)
                screen.blit(ts, (int(ft.x)-s.get_width()//2, int(ft.y)))

            # ── win overlay ──
            if state == "win":
                ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                ov.fill((0,0,0,160)); screen.blit(ov, (0,0))
                draw_text_centered(screen, font_big,   "YOU WIN!",               (55,210,75),  180)
                draw_text_centered(screen, font_med,   f"Score: {score}",        WHITE,        250)
                draw_text_centered(screen, font_med if new_best else font_small,
                                   "New Best!" if new_best else f"Best: {highscore}",
                                   (255,200,50), 288)
                draw_text_centered(screen, font_small, f"Level {level} cleared!", (100,255,200), 320)
                # Next Level button
                pygame.draw.rect(screen, (55,180,100), (156,345,200,38), border_radius=8)
                draw_text_centered(screen, font_med, f"Level {level+1}  ▶", WHITE, 364)
                draw_text_centered(screen, font_small, "R - Menu    Q - Quit", GRAY, 400)

            # ── game over overlay ──
            elif state == "gameover":
                ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                ov.fill((0,0,0,160)); screen.blit(ov, (0,0))
                draw_text_centered(screen, font_big,   "NO MORE MOVES",          (220,60,60),  190)
                draw_text_centered(screen, font_med,   f"Score: {score}",        WHITE,        265)
                draw_text_centered(screen, font_med if new_best else font_small,
                                   "New Best!" if new_best else f"Best: {highscore}",
                                   (255,200,50), 305)
                draw_text_centered(screen, font_small, "R - Menu    Q - Quit",   GRAY,         365)

        pygame.display.flip()


if __name__ == "__main__":
    main()
