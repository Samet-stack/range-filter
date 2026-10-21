#!/usr/bin/env bash
# Start the terminal in the background (if not already running) and open it in the Windows browser.
PORT=7071
if ss -ltn | grep -q ":$PORT "; then
  echo "Terminal deja lance."
else
  nohup ~/kronos/.venv/bin/python -I ~/range-filter/terminal/server.py > ~/range-filter/terminal/server.log 2>&1 &
  for _ in $(seq 1 30); do curl -s -o /dev/null http://127.0.0.1:$PORT/ && break; sleep 1; done
  echo "Terminal lance."
fi
(cd /mnt/c && cmd.exe /c start http://localhost:$PORT >/dev/null 2>&1) || true
echo "Adresse : http://localhost:$PORT"
