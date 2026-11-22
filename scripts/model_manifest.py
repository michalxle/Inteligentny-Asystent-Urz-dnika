import json,hashlib,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
files=[]
for base in ['.data/models/multilingual-e5-base','.data/models/pl_core_news_lg','.data/tessdata']:
    for path in sorted((root/base).rglob('*')):
        if not path.is_file() or '.cache' in path.parts:continue
        with path.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
        files.append({'file':str(path.relative_to(root)),'sha256':sha,'bytes':path.stat().st_size})
path=root/'.data/models/bielik-q8.gguf'
if path.exists():
    with path.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    files.append({'file':str(path.relative_to(root)),'sha256':sha,'bytes':path.stat().st_size})
(root/'.data/model-manifest.json').write_text(json.dumps({'resources':files},indent=2))
print('Zapisano manifest lokalnych modeli i OCR.')
