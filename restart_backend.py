#!/usr/bin/env python3.12
import subprocess, signal, os, time

# Find uvicorn processes
r = subprocess.run(['pgrep', '-f', 'uvicorn app.main'], capture_output=True, text=True)
pids = [p.strip() for p in r.stdout.strip().split() if p.strip()]
print(f'Found PIDs: {pids}')

# Send SIGTERM
for pid in pids:
    try:
        os.kill(int(pid), signal.SIGTERM)
        print(f'Sent SIGTERM to {pid}')
    except Exception as e:
        print(f'Error: {e}')

time.sleep(3)

# Start new uvicorn
print('Starting new uvicorn...')
os.chdir('/root/github/agentic-nexus/backend')
log = open('/root/github/agentic-nexus/logs/backend.log', 'w')
proc = subprocess.Popen(
    ['/root/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu/bin/python3.12',
     '-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000'],
    stdout=log, stderr=log
)
print(f'New backend PID: {proc.pid}')
time.sleep(5)

# Verify
r2 = subprocess.run(['curl', '-sf', 'http://localhost:8000/health'], capture_output=True, text=True)
print(f'Health check: {r2.stdout}')
