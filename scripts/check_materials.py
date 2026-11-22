import sys,json
from pathlib import Path
project_root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(project_root/'backend' if (project_root/'backend').exists() else project_root))
from app.services.documents import extract,export_letter
root=Path(__file__).resolve().parents[1]
materials=root.parent/'Hacknation 2026 - UMB'
results=[]
for pattern in ['*599*.docx','*Wniosek*590*.pdf','*Wniosek*543*.pdf','*Wniosek*16.2026.pdf']:
    source=next(materials.rglob(pattern))
    # DOC conversion must not write next to the source supplied by the organizer.
    import shutil
    target=root/'.data/tmp'/source.name;shutil.copyfile(source,target)
    text,pages,pdf=extract(target)
    if '543' in source.name:assert len(text)>300,'OCR drukowanego skanu zwrócił zbyt mało treści'
    results.append({'file':source.name,'pages':len(pages),'characters':len(text),'ocr':any(p['ocr'] for p in pages)})
for fmt in ['txt','docx','pdf','doc']:
    target=root/'.data/tmp'/('kontrola-eksportu.'+fmt)
    export_letter('Zażółć gęślą jaźń. Treść testowa po anonimizacji.',fmt,target)
    results.append({'export':fmt,'bytes':target.stat().st_size})
(root/'.data/material-checks.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print(json.dumps(results,ensure_ascii=False))
