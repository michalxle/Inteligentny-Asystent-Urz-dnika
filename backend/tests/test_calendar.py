from datetime import datetime
from io import BytesIO
from openpyxl import Workbook
from app.services.calendar_import import preview

def test_calendar_formulas_and_inconsistent_dates():
    w=Workbook();s=w.active;s.append(['title']);s.append(['Lp','Nr','Kto','Co','Wpływ','Termin','Odpowiedź'])
    s.append([1,'TEST.1','Test','Test',datetime(2026,1,15),'=E3+14',None])
    s.append([2,'TEST.2','Test','Test',datetime(2026,1,15),datetime(2025,1,29),datetime(2025,1,20)])
    s.append([3,'TEST.3','Test','Test',datetime(2026,8,5),'19.08.2026/18.09.2026 - doprecyzowanie',None])
    b=BytesIO();w.save(b);rows=preview(b.getvalue())['rows']
    assert rows[0]['deadline'].isoformat()=='2026-01-29'
    assert len(rows[1]['warnings'])==2
    assert rows[2]['warnings'] and rows[2]['deadline'].isoformat()=='2026-08-19'
