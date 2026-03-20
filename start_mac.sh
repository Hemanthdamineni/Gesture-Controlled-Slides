#!/bin/bash
cd "$(dirname "$0")"
nohup pixi run python main.py > /dev/null 2>&1 &
disown
