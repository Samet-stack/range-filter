#!/usr/bin/env bash
# Stop the terminal server.
PID=$(ss -ltnp | grep ":7071 " | grep -oP 'pid=\K[0-9]+')
if [ -n "$PID" ]; then kill "$PID" && echo "Terminal arrete."; else echo "Terminal deja arrete."; fi
