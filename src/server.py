import socket
import threading
import json

HOST = "localhost"
PORT = 5001

# player_socket -> "Player1" / "Player2" / custom name
players = {}

# player_socket -> list of ships
# ship structure: {"positions": [(row, col), ...], "hits": [(row, col), ...], "sunk": bool}
player_ships = {}

# players that sent "ready"
ready_players = set()

# socket of the player whose turn it is
current_turn = None


# -------------------------------------------------
# Helper functions
# -------------------------------------------------
def coord_to_index(coord: str) -> tuple[int, int]:
    """
    Convert a board coordinate like 'A5' into (row, col) indices.
    Rows and columns are 0-based.
    """
    col = ord(coord[0].upper()) - ord("A")
    row = int(coord[1:]) - 1
    return row, col


def send_message(client_socket: socket.socket, payload: dict) -> None:
    """
    Safely send a JSON-encoded message to a client.
    """
    try:
        data = json.dumps(payload).encode()
        client_socket.send(data)
    except Exception as exc:
        print(f"❌ Failed to send message to {players.get(client_socket, 'Unknown')}: {exc}")


# -------------------------------------------------
# Per-client handler
# -------------------------------------------------
def handle_client(client_socket: socket.socket, addr) -> None:
    global current_turn

    print(f"🔌 Client connected: {addr}")

    while True:
        try:
            data = client_socket.recv(2048).decode()

            # Connection closed
            if not data:
                print(f"📴 Connection closed: {addr}")
                break

            message = json.loads(data)
            player_name = players.get(client_socket, str(addr))
            print(f"📨 Message from {player_name}: {message}")

            msg_type = message.get("type")

            # -----------------------------
            # Player joins the game
            # -----------------------------
            if msg_type == "join":
                name = message.get("name", f"Player{len(players) + 1}")
                players[client_socket] = name
                print(f"👤 Player joined: {name}")
                continue

            # -----------------------------
            # Player places ships
            # -----------------------------
            if msg_type == "place":
                ships_payload = message.get("ships", [])
                ships = []

                for ship in ships_payload:
                    start_row, start_col = coord_to_index(ship["start"])
                    end_row, end_col = coord_to_index(ship["end"])
                    positions = []

                    # Horizontal ship
                    if start_row == end_row:
                        for col in range(min(start_col, end_col), max(start_col, end_col) + 1):
                            positions.append((start_row, col))

                    # Vertical ship
                    elif start_col == end_col:
                        for row in range(min(start_row, end_row), max(start_row, end_row) + 1):
                            positions.append((row, start_col))

                    ships.append(
                        {
                            "positions": positions,
                            "hits": [],
                            "sunk": False,
                        }
                    )

                player_ships[client_socket] = ships
                print(f"🚢 {player_name} placed ships.")
                continue

            # -----------------------------
            # Player is ready to start
            # -----------------------------
            if msg_type == "ready":
                ready_players.add(player_name)
                print(f"✅ {player_name} is ready. Total ready: {len(ready_players)}")

                # When two players are ready, start the game
                if len(ready_players) == 2:
                    print("🎮 Both players are ready. Starting game...")

                    # Sort players by name ("Player1" → "Player2")
                    player_list = sorted(players.items(), key=lambda x: x[1])
                    player_sockets = [p[0] for p in player_list]

                    # Notify clients that gameplay can start
                    for c in player_sockets:
                        print(f"📤 Sending 'start_gameplay' to {players[c]}")
                        send_message(c, {"type": "start_gameplay"})

                    # Give the first turn to the first player
                    current_turn = player_sockets[0]
                    send_message(
                        current_turn,
                        {"type": "turn", "message": "Your turn!"},
                    )

                continue

            # -----------------------------
            # Player makes a move (fires at coord)
            # -----------------------------
            if msg_type == "move":
                # Always sort players to keep a stable order (Player1, Player2)
                player_list = sorted(players.items(), key=lambda x: x[1])
                player_sockets = [p[0] for p in player_list]

                # Not this player's turn
                if client_socket != current_turn:
                    error_payload = {"type": "error", "message": "It is not your turn."}
                    send_message(client_socket, error_payload)
                    continue

                coord = message["coord"]
                target_row, target_col = coord_to_index(coord)

                # Determine opponent
                if len(player_sockets) < 2:
                    # Not enough players yet
                    send_message(
                        client_socket,
                        {"type": "error", "message": "Opponent is not connected yet."},
                    )
                    continue

                opponent = player_sockets[0] if client_socket == player_sockets[1] else player_sockets[1]

                hit = False
                sunk = False
                sunk_ship = None

                # Check hit / miss
                for ship in player_ships.get(opponent, []):
                    if (target_row, target_col) in ship["positions"]:
                        if (target_row, target_col) not in ship["hits"]:
                            ship["hits"].append((target_row, target_col))
                        hit = True

                        # Check if this ship is sunk
                        if set(ship["hits"]) == set(ship["positions"]):
                            ship["sunk"] = True
                            sunk = True
                            sunk_ship = ship
                        break

                # Build response for the current player
                if sunk and sunk_ship is not None:
                    response = {
                        "type": "result",
                        "status": "sink",
                        "coord": coord,
                        "sunk_coords": [
                            chr(ord("A") + col) + str(row + 1)
                            for (row, col) in sunk_ship["positions"]
                        ],
                    }
                else:
                    response = {
                        "type": "result",
                        "status": "hit" if hit else "miss",
                        "coord": coord,
                    }

                send_message(client_socket, response)

                # Notify opponent about the move
                opponent_notify = {
                    "type": "opponent_move",
                    "coord": coord,
                    "status": "hit" if hit else "miss",
                }
                send_message(opponent, opponent_notify)

                # Check if the opponent has any ships left
                all_sunk = all(ship["sunk"] for ship in player_ships.get(opponent, []))
                if all_sunk:
                    gameover_payload = {
                        "type": "gameover",
                        "winner": players.get(client_socket, "Unknown"),
                    }
                    for c in player_sockets:
                        send_message(c, gameover_payload)
                else:
                    # Switch turn
                    current_turn = opponent
                    print(f"🔄 Turn changed → now: {players[current_turn]}")
                    send_message(
                        current_turn,
                        {"type": "turn", "message": "Your turn!"},
                    )

                continue

        except Exception as e:
            print(f"❌ Error while handling client {addr}: {e}")
            break

    # Cleanup after disconnect
    if client_socket in players:
        print(f"🧹 Cleaning up player: {players[client_socket]}")
        del players[client_socket]

    if client_socket in player_ships:
        del player_ships[client_socket]

    client_socket.close()


def main() -> None:
    """
    Entry point: creates the server socket and accepts incoming clients.
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((HOST, PORT))
    server_socket.listen()

    print(f"🌊 Battleship server listening on {HOST}:{PORT} ...")

    while True:
        client_socket, addr = server_socket.accept()
        thread = threading.Thread(target=handle_client, args=(client_socket, addr), daemon=True)
        thread.start()


if __name__ == "__main__":
    main()
