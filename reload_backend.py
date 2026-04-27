#!/usr/bin/env python3
import subprocess, os, time, signal

# Find the uvicorn master process
r = subprocess.run(['pgrep', '-f', 'uvicorn app.main'], capture_output=True, text=True)
pids = [p.strip() for p in r.stdout.strip().split() if p.strip()]
print(f'Uvicorn PIDs: {pids}')

# Send SIGHUP to trigger reload (uvicorn --reload watches for file changes automatically)
# Since we used uvicorn without --reload flag, we need to restart
for pid in pids:
    try:
        os.kill(int(pid), signal.SIGTERM)
        print(f'SIGTERM -> {pid}')
    except ProcessLookupError:
        pass

time.sleep(3)

# Start fresh
print('Starting uvicorn...')
os.chdir('/root/github/agentic-nexus/backend')
log = open('/root/github/agentic-nexus/logs/backend.log', 'w')
proc = subprocess.Popen(
    ['/root/.local/bin/uv', 'run', '--python', '3.12',
     'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000'],
    stdout=log, stderr=log,
    cwd='/root/github/agentic-nexus/backend'
)
print(f'New PID: {proc.pid}')

# Wait for ready
for i in range(20):
    time.sleep(1)
    r2 = subprocess.run(['curl', '-sf', 'http://localhost:8000/health'], capture_output=True, text=True)
    if r2.returncode == 0:
        print(f'Ready after {i+1}s: {r2.stdout}')
        break
else:
    print('Timeout waiting for backend')
    # Show log
    with open('/root/github/agentic-nexus/logs/backend.log') as f:
        print(f.read()[-2000:])

# Test the fix
print('\nTesting POST /api/tasks (expect 503 not 500)...')
r3 = subprocess.run([
    'curl', '-s', '-w', '\nHTTP:%{http_code}',
    '-X', 'POST', 'http://localhost:8000/api/tasks',
    '-H', 'Authorization: Bearer test-token-123',
    '-H', 'Content-Type: application/json',
    '-d', '{"title":"测试任务：AI医疗应用前景","mode":"report","depth":"standard","target_words":5000}'
], capture_output=True, text=True)
print(r3.stdout[:500])
