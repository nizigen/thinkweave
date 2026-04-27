import subprocess, sys, os
os.chdir('/root/github/agentic-nexus/backend')
proc = subprocess.Popen(
    ['/root/.local/bin/uv', 'run', '--python', '3.12',
     'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000'],
    stdout=open('/root/github/agentic-nexus/logs/backend.log', 'w'),
    stderr=subprocess.STDOUT
)
print(f'Backend PID: {proc.pid}')
proc.wait()
