Battleship Multiplayer (Python)

A two-player Battleship game built with Python, Pygame, and TCP sockets.
This project was originally developed as a Computer Networks course assignment and runs on a local network using a server–client architecture.

Features

Two-player multiplayer gameplay (Player1 vs Player2)

TCP socket communication

Server–client architecture

Fullscreen graphical interface using Pygame

Drag-and-drop ship placement

Rotate ships with the R key

Visual and audio feedback for hit, miss, and sink

Animated screens (start, waiting, gameplay, game-over)

Project Structure

battleship-game/
├── src/
│ ├── server.py
│ ├── client1.py
│ ├── client2.py
│
├── assets/
│ ├── images/
│ │ ├── ship2.png
│ │ ├── ship3.png
│ │ ├── ship4.png
│ │ ├── ship5.png
│ │ └── sea_background.jpg
│ └── sounds/
│ ├── hit.wav
│ ├── miss.wav
│ ├── start.mp3
│ └── win.mp3 (optional)
│
└── README.md

How to Run

Install dependencies:
pip install pygame

Start the server:
cd battleship-game/src
python server.py

Start Player 1:
cd battleship-game/src
python client1.py

Start Player 2:
cd battleship-game/src
python client2.py

Gameplay

Players place ships on their board

When both players are ready, the server starts the game

Players take turns targeting grid cells

Server handles all hit/miss/sink logic

First player to sink all enemy ships wins

Technologies Used

Python

Pygame

TCP sockets

Threading

JSON protocol

Notes

Designed for local network multiplayer

Fully compatible with Windows fullscreen mode

Code refactored and cleaned for public release

License

This project is free to use for educational purposes.