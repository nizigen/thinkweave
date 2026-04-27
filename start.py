import subprocess, os, sys, time

os.chdir('/root/github/agentic-nexus/backend')
log = open('/root/github/agentic-nexus/logs/backend.log', 'w')
proc = subprocess.Popen(
    ['/root/.local/bin/uv', 'run', '--python', '3.12',
     'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000'],
    stdout=log, stderr=log
)
print(f'PID={proc.pid}')
# write pid file
with open('/tmp/backend.pid', 'w') as f:
    f.write(str(proc.pid))
