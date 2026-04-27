#!/usr/bin/env python3
import subprocess, os, time

os.chdir('/root/github/agentic-nexus/backend')
log = open('/root/github/agentic-nexus/logs/backend.log', 'w')

proc = subprocess.Popen(
    ['/root/.local/bin/uv', 'run', '--python', '3.12',
     'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000'],
    stdout=log, stderr=log,
    cwd='/root/github/agentic-nexus/backend'
)
print(f'Backend PID: {proc.pid}')
time.sleep(8)

r = subprocess.run(['curl', '-s', 'http://localhost:8000/health'], capture_output=True, text=True)
print(f'Health: {r.stdout}')

r2 = subprocess.run(
    ['curl', '-s', '-H', 'Authorization: Bearer test-token-123', 'http://localhost:8000/api/agents'],
    capture_output=True, text=True
)
print(f'Agents: {r2.stdout[:300]}')
