"""Run local API, worker and Vite. PostgreSQL and Ollama are started separately."""
import os,sys,subprocess,signal,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
logs=root/'.data/logs';logs.mkdir(parents=True,exist_ok=True)
(root/'.data/dev.pid').write_text(str(os.getpid()))
env={**os.environ,'PYTHONPATH':str(root/'backend'),'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','TOKENIZERS_PARALLELISM':'false'}
commands=[('api',[sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000'],root),('worker',[sys.executable,'-m','app.worker'],root),('frontend',['npm','run','dev'],root/'frontend')]
processes=[];streams=[]
def stop(*_):
    for p in processes:
        if p.poll() is None:p.terminate()
    for p in processes:
        try:p.wait(timeout=8)
        except subprocess.TimeoutExpired:p.kill()
    for stream in streams:stream.close()
    sys.exit(0)
signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
for name,command,cwd in commands:
    stream=(logs/(name+'.log')).open('a');streams.append(stream)
    processes.append(subprocess.Popen(command,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT))
print('Aplikacja: http://127.0.0.1:5173/ | API: http://127.0.0.1:8000/docs',flush=True)
print('Logi: .data/logs/ | Ctrl+C zatrzymuje procesy aplikacji.',flush=True)
while True:
    for name,p in zip([x[0] for x in commands],processes):
        if p.poll() is not None:print(name+' zakończył pracę; sprawdź log.',flush=True);stop()
    time.sleep(1)
