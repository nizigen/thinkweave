import subprocess, os, signal, time

# 读取旧 PID 并终止
try:
    with open('/tmp/backend.pid') as f:
        old_pid = int(f.read().strip())
    os.kill(old_pid, signal.SIGTERM)
    time.sleep(2)
    print(f'Killed old PID {old_pid}')
except Exception as e:
    print(f'No old process: {e}')

# 启动新进程
os.chdir('/root/github/agentic-nexus/backend')
log = open('/root/github/agentic-nexus/logs/backend.log', 'w')
proc = subprocess.Popen(
    ['/root/.local/bin/uv', 'run', '--python', '3.12',
     'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000'],
    stdout=log, stderr=log
)
with open('/tmp/backend.pid', 'w') as f:
    f.write(str(proc.pid))
print(f'New PID={proc.pid}')
