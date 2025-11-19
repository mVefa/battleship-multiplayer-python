import sys
import socket
import json
import threading
import select
import traceback
import ctypes

import pygame
from pygame.locals import *

# ------------------------------
# Basic configuration
# ------------------------------
PLAYER_NAME = "Player1"  # In client2.py, set this to "Player2"

current_screen = "start"
game_winner = None

running = True
start_clicked = False
start_button_rect = None
start_gameplay_flag = False

your_turn = False
enemy_moves = []          # List of (coord, status) tuples from opponent
your_moves = {}           # Dict: {"B3": "hit" / "miss" / "sink"}

pygame.init()

# ------------------------------
# Socket configuration
# ------------------------------
HOST = "localhost"
PORT = 5001

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect((HOST, PORT))
client_socket.settimeout(0.5)  # 0.5s timeout for non-blocking behavior


def listen_server():
    """
    Background thread that listens to server messages
    and updates game state accordingly.
    """
    global start_gameplay_flag, your_turn, your_moves, enemy_moves, current_screen, game_winner

    print("🔊 Listener thread started")

    while True:
        try:
            # Wait up to 100ms to see if there is data to read
            ready_to_read, _, _ = select.select([client_socket], [], [], 0.1)
            if not ready_to_read:
                continue

            data = client_socket.recv(2048).decode()
            if not data:
                continue

            for message in parse_multiple_json_objects(data):
                try:
                    print("📩 Server message:", message)
                    msg_type = message.get("type")

                    if msg_type == "start_gameplay":
                        print("🟢 start_gameplay received")
                        start_gameplay_flag = True

                    elif msg_type == "turn":
                        print("🎯 Your turn")
                        your_turn = True

                    elif msg_type == "result":
                        status = message["status"]
                        coord = message["coord"]

                        if status == "sink":
                            coords = message.get("sunk_coords", [coord])
                            for c in coords:
                                your_moves[c] = "sink"
                        else:
                            your_moves[coord] = status

                        your_turn = False

                    elif msg_type == "opponent_move":
                        coord = message["coord"]
                        status = message["status"]
                        enemy_moves.append((coord, status))

                        # Play sounds for opponent moves
                        if status == "miss":
                            miss_sound.play()
                        elif status in ("hit", "sink"):
                            hit_sound.play()

                    elif msg_type == "gameover":
                        winner = message.get("winner")
                        print(f"🏁 Game over! Winner: {winner}")
                        game_winner = winner
                        current_screen = "gameover"

                except Exception:
                    print("❌ Failed to process message:", message)
                    traceback.print_exc()

        except Exception as e:
            # Non-fatal listening error; keep the loop running
            print("❌ Listener error:", e)
            traceback.print_exc()


def parse_multiple_json_objects(data: str):
    """
    The server may send multiple JSON objects in a single TCP packet.
    This helper splits and decodes them one by one.
    """
    decoder = json.JSONDecoder()
    pos = 0
    while pos < len(data):
        try:
            obj, offset = decoder.raw_decode(data[pos:])
            yield obj
            pos += offset
        except json.JSONDecodeError as e:
            print("🔴 JSON parse error:", e)
            break


# Send initial join message
join_message = {"type": "join", "name": PLAYER_NAME}
client_socket.send(json.dumps(join_message).encode())
print("🔗 Join message sent:", join_message)

# Start background listener
listen_thread = threading.Thread(target=listen_server, daemon=True)
listen_thread.start()
print("Connected to server.")

# ------------------------------
# Screen configuration - Fullscreen
# ------------------------------
# Get screen resolution (Windows-specific)
user32 = ctypes.windll.user32
SCREEN_WIDTH = user32.GetSystemMetrics(0)
SCREEN_HEIGHT = user32.GetSystemMetrics(1) - 40  # leave some space for taskbar

screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
pygame.display.set_caption("Battleship")
clock = pygame.time.Clock()

# ------------------------------
# Constants & colors
# ------------------------------
GRID_SIZE = 10
CELL_SIZE = min(SCREEN_HEIGHT // 15, SCREEN_WIDTH // 25)
GRID_WIDTH = GRID_SIZE * CELL_SIZE

PLAYER_GRID_POS = (
    SCREEN_WIDTH - GRID_WIDTH - int(SCREEN_WIDTH * 0.15),
    int(SCREEN_HEIGHT * 0.15),
)
SHIP_PANEL_POS = (int(SCREEN_WIDTH * 0.1), int(SCREEN_HEIGHT * 0.15))

BG_COLOR = (30, 30, 30)
GRID_COLOR = (0, 128, 255)
SHIP_COLOR = (0, 200, 0)
SELECTED_SHIP_COLOR = (200, 0, 0)

BIG_CELL_SIZE = CELL_SIZE
SMALL_CELL_SIZE = CELL_SIZE // 2

BIG_GRID_POS = (SCREEN_WIDTH // 2, int(SCREEN_HEIGHT * 0.15))         # Opponent grid
SMALL_GRID_POS = (int(SCREEN_WIDTH * 0.1), int(SCREEN_HEIGHT * 0.15))  # Own small grid

# ------------------------------
# Load ship images
# ------------------------------
ship_images = {
    2: pygame.image.load("../assets/images/ship2.png").convert_alpha(),
    3: pygame.image.load("../assets/images/ship3.png").convert_alpha(),
    4: pygame.image.load("../assets/images/ship4.png").convert_alpha(),
    5: pygame.image.load("../assets/images/ship5.png").convert_alpha(),
}

# ------------------------------
# Sound configuration
# ------------------------------
pygame.mixer.init()
miss_sound = pygame.mixer.Sound("../assets/sounds/miss.wav")
hit_sound = pygame.mixer.Sound("../assets/sounds/hit.wav")

# ------------------------------
# Helper functions
# ------------------------------
def get_occupied_cells(ship):
    gx, gy = PLAYER_GRID_POS
    start_col = (ship.x - gx) // CELL_SIZE
    start_row = (ship.y - gy) // CELL_SIZE
    if ship.orientation == "vertical":
        return [(start_row + i, start_col) for i in range(ship.size)]
    else:
        return [(start_row, start_col + i) for i in range(ship.size)]


def is_overlapping(new_ship, all_ships):
    new_cells = set(get_occupied_cells(new_ship))
    for other in all_ships:
        if other is not new_ship and new_cells & set(get_occupied_cells(other)):
            return True
    return False


def is_out_of_bounds(ship):
    gx, gy = PLAYER_GRID_POS
    start_col = (ship.x - gx) // CELL_SIZE
    start_row = (ship.y - gy) // CELL_SIZE
    if ship.orientation == "horizontal":
        return start_col + ship.size > GRID_SIZE or start_row >= GRID_SIZE or start_row < 0
    else:
        return start_row + ship.size > GRID_SIZE or start_col >= GRID_SIZE or start_col < 0


def get_ship_at_pos(pos):
    for ship in ships:
        if ship.get_rect().collidepoint(pos):
            return ship
    return None


def draw_grid(start_x, start_y, cell_size=CELL_SIZE):
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            rect = pygame.Rect(
                start_x + col * cell_size,
                start_y + row * cell_size,
                cell_size,
                cell_size,
            )
            pygame.draw.rect(screen, GRID_COLOR, rect, 2)


def draw_ships():
    for ship in ships:
        ship.draw(screen)


def is_ship_on_grid(ship):
    gx, gy = PLAYER_GRID_POS
    return gx <= ship.x < gx + GRID_WIDTH and gy <= ship.y < gy + GRID_WIDTH


def is_all_ships_placed():
    return all(is_ship_on_grid(ship) for ship in ships)


def index_to_coord(row, col):
    return chr(ord("A") + col) + str(row + 1)


def draw_start_button():
    """Draws the START button and returns its rect."""
    button_width, button_height = 200, 60
    button_x = (SCREEN_WIDTH - button_width) // 2
    button_y = SCREEN_HEIGHT - 120
    rect = pygame.Rect(button_x, button_y, button_width, button_height)

    pygame.draw.rect(screen, (0, 180, 0), rect)
    pygame.draw.rect(screen, (255, 255, 255), rect, 3)

    font = pygame.font.SysFont(None, 40)
    text = font.render("START", True, (255, 255, 255))
    text_rect = text.get_rect(center=rect.center)
    screen.blit(text, text_rect)
    return rect


def draw_own_ships_on_small_grid():
    for ship in ships:
        cells = get_occupied_cells(ship)
        for row, col in cells:
            rect = pygame.Rect(
                SMALL_GRID_POS[0] + col * SMALL_CELL_SIZE,
                SMALL_GRID_POS[1] + row * SMALL_CELL_SIZE,
                SMALL_CELL_SIZE,
                SMALL_CELL_SIZE,
            )
            pygame.draw.rect(screen, SHIP_COLOR, rect)


def draw_move_result(coord, status, is_enemy=False, play_sound=False):
    """
    Draw the visual result of a move on either the big (opponent) grid
    or the small (own) grid.
    """
    row = int(coord[1:]) - 1
    col = ord(coord[0].upper()) - ord("A")

    if is_enemy:
        x = SMALL_GRID_POS[0] + col * SMALL_CELL_SIZE
        y = SMALL_GRID_POS[1] + row * SMALL_CELL_SIZE
        size = SMALL_CELL_SIZE
    else:
        x = BIG_GRID_POS[0] + col * BIG_CELL_SIZE
        y = BIG_GRID_POS[1] + row * BIG_CELL_SIZE
        size = BIG_CELL_SIZE

    center = (x + size // 2, y + size // 2)

    if status == "miss":
        pygame.draw.circle(screen, (255, 255, 255), center, size // 6)
        if play_sound:
            miss_sound.play()

    elif status == "hit":
        if play_sound:
            hit_sound.play()
        inner = pygame.Rect(x, y, size, size).inflate(-size // 3, -size // 3)
        pygame.draw.rect(screen, (220, 20, 60), inner)

    elif status == "sink":
        if play_sound:
            hit_sound.play()
        pygame.draw.line(screen, (255, 255, 255), (x, y), (x + size, y + size), 3)
        pygame.draw.line(screen, (255, 255, 255), (x + size, y), (x, y + size), 3)


def reset_ships():
    """
    Reset ship positions and local game state when starting over.
    """
    global ships, start_clicked, start_gameplay_flag, your_turn, your_moves, enemy_moves

    ships[:] = [Ship(size, x, y) for size, (x, y) in zip(ship_sizes, ship_positions)]
    start_clicked = False
    start_gameplay_flag = False
    your_turn = False
    your_moves.clear()
    enemy_moves.clear()


# ------------------------------
# Ship class
# ------------------------------
class Ship:
    def __init__(self, size, x, y):
        self.size = size
        self.x = x
        self.y = y
        self.orientation = "horizontal"
        self.selected = False
        self.image = ship_images[size]
        self.original_image = self.image  # Store original for rotation

    def get_rect(self):
        if self.orientation == "horizontal":
            width = self.size * CELL_SIZE
            height = CELL_SIZE
        else:
            width = CELL_SIZE
            height = self.size * CELL_SIZE
        return pygame.Rect(self.x, self.y, width, height)

    def draw(self, surface):
        # Draw selection border
        if self.selected:
            pygame.draw.rect(surface, SELECTED_SHIP_COLOR, self.get_rect(), 3)

        # Rotate image based on orientation
        if self.orientation == "vertical":
            rotated_image = pygame.transform.rotate(self.original_image, 90)
        else:
            rotated_image = self.original_image

        rect = self.get_rect()
        scaled_image = pygame.transform.scale(rotated_image, (rect.width, rect.height))
        surface.blit(scaled_image, rect)


# ------------------------------
# Initial ship positions
# ------------------------------
ship_sizes = [2, 3, 4, 5]

ship_positions = []
base_x = int(SCREEN_WIDTH * 0.05)
ship_spacing = int(SCREEN_HEIGHT * 0.15)

for i, size in enumerate(ship_sizes):
    y_pos = int(SCREEN_HEIGHT * 0.2) + i * ship_spacing
    ship_positions.append((base_x, y_pos))

ships = [Ship(size, x, y) for size, (x, y) in zip(ship_sizes, ship_positions)]

# ------------------------------
# Screen handlers
# ------------------------------
def handle_start_screen():
    """
    Start screen with background image and music.
    """
    background_img = pygame.image.load("../assets/images/sea_background.jpg").convert()

    # Background music
    try:
        pygame.mixer.music.load("../assets/sounds/start.mp3")
        pygame.mixer.music.play(-1)
    except Exception:
        pass

    blink = True
    blink_timer = 0
    blink_interval = 500

    while True:
        screen.blit(
            pygame.transform.scale(background_img, (SCREEN_WIDTH, SCREEN_HEIGHT)),
            (0, 0),
        )
        current_time = pygame.time.get_ticks()

        for event in pygame.event.get():
            if event.type == pygame.QUIT or (
                event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
            ):
                pygame.mixer.music.stop()
                pygame.quit()
                sys.exit()
            elif event.type == pygame.KEYDOWN or event.type == pygame.MOUSEBUTTONDOWN:
                pygame.mixer.music.stop()
                return "placement"

        # Title
        font_title = pygame.font.SysFont("comicsansms", 60, bold=True)
        title_text = font_title.render("🛳️ BATTLESHIP 🛳️", True, (255, 255, 255))
        screen.blit(
            title_text,
            title_text.get_rect(center=(SCREEN_WIDTH // 2, 80)),
        )

        # Blinking "press to start" text
        font_info = pygame.font.SysFont("comicsansms", 28, bold=True)
        if current_time - blink_timer > blink_interval:
            blink = not blink
            blink_timer = current_time

        if blink:
            start_text = font_info.render(
                "▶ Click or press any key to start ◀", True, (255, 255, 255)
            )
            screen.blit(
                start_text,
                start_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 100)),
            )

        # Footer
        footer_font = pygame.font.SysFont("arial", 20)
        footer_text = footer_font.render(
            "Press Esc to quit.", True, (255, 255, 255)
        )
        screen.blit(
            footer_text,
            footer_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 40)),
        )

        pygame.display.flip()
        clock.tick(60)


def handle_placement_screen():
    """
    Ship placement: drag ships to the grid, press START when done.
    """
    global start_clicked, start_button_rect

    screen.fill((0, 0, 20))

    # Title
    font_title = pygame.font.SysFont("comicsansms", 48, bold=True)
    title_text = font_title.render("Place Your Ships", True, (255, 255, 255))
    screen.blit(title_text, title_text.get_rect(center=(SCREEN_WIDTH // 2, 40)))

    # Help text
    font_help = pygame.font.SysFont("arial", 20)
    help_text1 = font_help.render(
        "1. Drag ships onto the board.", True, (200, 200, 200)
    )
    help_text2 = font_help.render(
        "2. Press 'R' to rotate the selected ship.", True, (200, 200, 200)
    )
    screen.blit(help_text1, (int(SCREEN_WIDTH * 0.05), int(SCREEN_HEIGHT * 0.1)))
    screen.blit(
        help_text2,
        (int(SCREEN_WIDTH * 0.05), int(SCREEN_HEIGHT * 0.1) + 30),
    )

    for event in pygame.event.get():
        if event.type == pygame.QUIT or (
            event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
        ):
            pygame.quit()
            sys.exit()

        # Rotate selected ship
        if (
            not start_clicked
            and event.type == pygame.KEYDOWN
            and event.key == pygame.K_r
        ):
            for ship in ships:
                if ship.selected:
                    original_orientation = ship.orientation
                    ship.orientation = (
                        "vertical"
                        if ship.orientation == "horizontal"
                        else "horizontal"
                    )
                    if is_out_of_bounds(ship) or is_overlapping(ship, ships):
                        ship.orientation = original_orientation

        # Mouse interactions
        if event.type == pygame.MOUSEBUTTONDOWN:
            if start_clicked:
                continue

            x, y = event.pos

            # START button clicked
            if start_button_rect and start_button_rect.collidepoint((x, y)):
                start_clicked = True

                # Send ship placements to the server
                ships_data = []
                for ship in ships:
                    cells = get_occupied_cells(ship)
                    start = index_to_coord(*cells[0])
                    end = index_to_coord(*cells[-1])
                    ships_data.append({"start": start, "end": end})

                place_message = {"type": "place", "ships": ships_data}
                client_socket.send(json.dumps(place_message).encode())
                print("Ships sent:", place_message)

                ready_message = {"type": "ready"}
                client_socket.send(json.dumps(ready_message).encode())
                print("Ready message sent.")

                return "waiting"

            # Select ship
            clicked_ship = get_ship_at_pos((x, y))
            if clicked_ship:
                for ship in ships:
                    ship.selected = False
                clicked_ship.selected = True
            else:
                # Move selected ship onto grid
                gx, gy = PLAYER_GRID_POS
                if gx <= x < gx + GRID_WIDTH and gy <= y < gy + GRID_WIDTH:
                    col = (x - gx) // CELL_SIZE
                    row = (y - gy) // CELL_SIZE
                    for ship in ships:
                        if ship.selected:
                            old_x, old_y = ship.x, ship.y
                            ship.x = gx + col * CELL_SIZE
                            ship.y = gy + row * CELL_SIZE
                            if is_out_of_bounds(ship) or is_overlapping(ship, ships):
                                ship.x, ship.y = old_x, old_y
                            else:
                                ship.selected = False
                            break

    # Draw main grid and ships
    draw_grid(*PLAYER_GRID_POS)
    draw_ships()

    # Info text if all ships placed
    if is_all_ships_placed():
        font_ready = pygame.font.SysFont("arial", 24)
        ready_text = font_ready.render(
            "All ships are placed!", True, (0, 255, 0)
        )
        screen.blit(
            ready_text,
            (SCREEN_WIDTH // 2 - 120, SCREEN_HEIGHT - 180),
        )

    # Show START button only when all ships placed
    if is_all_ships_placed() and not start_clicked:
        start_button_rect = draw_start_button()

    pygame.display.flip()
    clock.tick(60)
    return "placement"


def handle_waiting_screen():
    """
    Waiting screen shown after sending placements, until the server
    sends 'start_gameplay'.
    """
    global start_gameplay_flag

    for event in pygame.event.get():
        if event.type == pygame.QUIT or (
            event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
        ):
            pygame.quit()
            sys.exit()

    if start_gameplay_flag:
        print("✅ waiting → gameplay")
        return "gameplay"

    screen.fill((0, 0, 20))

    font = pygame.font.SysFont("comicsansms", 50)
    text = font.render("Waiting for opponent...", True, (200, 200, 200))
    screen.blit(
        text, (SCREEN_WIDTH // 2 - 260, SCREEN_HEIGHT // 2 - 50)
    )

    # Simple rotating dot animation
    current_time = pygame.time.get_ticks()
    angle = (current_time // 10) % 360
    radius = 30
    cx, cy = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 50
    vec = pygame.math.Vector2(1, 0).rotate(angle)
    dx = int(radius * vec.x)
    dy = int(radius * vec.y)
    pygame.draw.circle(screen, (0, 128, 255), (cx + dx, cy + dy), 10)

    pygame.display.flip()
    clock.tick(60)
    return "waiting"


def handle_gameplay_screen():
    """
    Main gameplay screen: handles turn logic and drawing boards.
    """
    global your_turn, current_screen

    if current_screen != "gameplay":
        # If a gameover arrived in the listener, switch immediately
        return current_screen

    if your_turn:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (
                event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
            ):
                pygame.quit()
                sys.exit()

            if event.type == pygame.MOUSEBUTTONDOWN:
                x, y = event.pos
                gx, gy = BIG_GRID_POS
                if gx <= x < gx + BIG_CELL_SIZE * GRID_SIZE and gy <= y < gy + BIG_CELL_SIZE * GRID_SIZE:
                    col = (x - gx) // BIG_CELL_SIZE
                    row = (y - gy) // BIG_CELL_SIZE
                    coord = chr(ord("A") + col) + str(row + 1)

                    if coord not in your_moves:
                        move_msg = {"type": "move", "coord": coord}
                        client_socket.send(json.dumps(move_msg).encode())
                        print("📤 Move sent:", coord)
                        your_turn = False
                    else:
                        print("❌ Already targeted:", coord)
    else:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (
                event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
            ):
                pygame.quit()
                sys.exit()

    # Background
    screen.fill((0, 0, 20))

    # Title
    font_title = pygame.font.SysFont("comicsansms", 36, bold=True)
    title_text = font_title.render(
        "🛳️ BATTLESHIP - GAME BOARD 🛳️", True, (255, 255, 255)
    )
    screen.blit(
        title_text,
        title_text.get_rect(center=(SCREEN_WIDTH // 2, 40)),
    )

    # Opponent board (big, right)
    font_opponent = pygame.font.SysFont("arial", 24)
    opponent_text = font_opponent.render("Opponent Board", True, (200, 200, 200))
    screen.blit(
        opponent_text,
        (BIG_GRID_POS[0] + GRID_WIDTH // 2 - 90, BIG_GRID_POS[1] - 40),
    )
    draw_grid(*BIG_GRID_POS, BIG_CELL_SIZE)

    # Own board (small, left)
    font_your = pygame.font.SysFont("arial", 24)
    your_text = font_your.render("Your Board", True, (200, 200, 200))
    screen.blit(
        your_text,
        (SMALL_GRID_POS[0] + (GRID_SIZE * SMALL_CELL_SIZE) // 2 - 60, SMALL_GRID_POS[1] - 40),
    )
    draw_grid(*SMALL_GRID_POS, SMALL_CELL_SIZE)
    draw_own_ships_on_small_grid()

    # Status text
    status_font = pygame.font.SysFont("comicsansms", 30, bold=True)
    if your_turn:
        status_text = status_font.render(
            "✓ YOUR TURN! Click on opponent board.", True, (0, 255, 0)
        )
    else:
        status_text = status_font.render(
            "⏳ Waiting for opponent's move...", True, (255, 165, 0)
        )
    screen.blit(
        status_text,
        status_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 120)),
    )

    # Draw your moves on opponent board
    for coord, status in your_moves.items():
        draw_move_result(coord, status, is_enemy=False)

    # Draw opponent moves on your small board
    for coord, status in enemy_moves:
        draw_move_result(coord, status, is_enemy=True)

    pygame.display.flip()
    clock.tick(60)
    return "gameplay"


def handle_gameover_screen(winner):
    """
    Game over screen with 'Play Again' and 'Exit' buttons.
    """
    print("Game over screen opened")

    font_large = pygame.font.SysFont("comicsansms", 72, bold=True)
    font_small = pygame.font.SysFont("arial", 36)

    # Victory music (optional)
    if winner == PLAYER_NAME:
        try:
            pygame.mixer.music.load("../assets/sounds/win.mp3")
            pygame.mixer.music.play()
        except Exception:
            pass

    play_again_rect = pygame.Rect(
        screen.get_width() // 2 - 150,
        SCREEN_HEIGHT // 2 + 50,
        300,
        80,
    )
    exit_rect = pygame.Rect(
        screen.get_width() // 2 - 150,
        SCREEN_HEIGHT // 2 + 150,
        300,
        80,
    )

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if play_again_rect.collidepoint(event.pos):
                    print("🔄 Play Again selected.")
                    return "start"
                elif exit_rect.collidepoint(event.pos):
                    pygame.quit()
                    sys.exit()

        screen.fill((10, 10, 50))

        current_time = pygame.time.get_ticks()
        glow_value = 100 + int(
            50 * abs(pygame.math.Vector2(1, 0).rotate(current_time // 15 % 360).x)
        )

        if winner == PLAYER_NAME:
            result_color = (255, 215, 0)
            text = "YOU WON!"
        else:
            result_color = (200, 200, 200)
            text = f"{winner} won!"

        text_surface = font_large.render(text, True, result_color)
        text_rect = text_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 3))

        glow_color = (
            min(result_color[0], glow_value),
            min(result_color[1], glow_value),
            min(result_color[2], glow_value),
        )
        glow_text = font_large.render(text, True, glow_color)
        glow_rect = glow_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 3))

        screen.blit(glow_text, glow_rect)
        screen.blit(text_surface, text_rect)

        # Play Again button
        pygame.draw.rect(screen, (0, 180, 0), play_again_rect, border_radius=15)
        pygame.draw.rect(screen, (255, 255, 255), play_again_rect, 3, border_radius=15)
        play_again_text = font_small.render("Play Again", True, (255, 255, 255))
        play_again_text_rect = play_again_text.get_rect(center=play_again_rect.center)
        screen.blit(play_again_text, play_again_text_rect)

        # Exit button
        pygame.draw.rect(screen, (180, 0, 0), exit_rect, border_radius=15)
        pygame.draw.rect(screen, (255, 255, 255), exit_rect, 3, border_radius=15)
        exit_text = font_small.render("Exit", True, (255, 255, 255))
        exit_text_rect = exit_text.get_rect(center=exit_rect.center)
        screen.blit(exit_text, exit_text_rect)

        pygame.display.flip()
        clock.tick(60)


# ------------------------------
# Main game loop
# ------------------------------
while running:
    if current_screen == "start":
        reset_ships()
        current_screen = handle_start_screen()

    elif current_screen == "placement":
        current_screen = handle_placement_screen()

    elif current_screen == "waiting":
        current_screen = handle_waiting_screen()

    elif current_screen == "gameplay":
        result = handle_gameplay_screen()
        if result != "gameplay":
            current_screen = result

    elif current_screen == "gameover":
        current_screen = handle_gameover_screen(game_winner)

pygame.quit()
sys.exit()
