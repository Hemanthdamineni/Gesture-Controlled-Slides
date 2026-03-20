#!/bin/bash
cd "$(dirname "$0")"
nohup pixi run python main.py > gesture_log.txt 2>&1 &
disown
echo "GestureSlides started. PID: $!"
