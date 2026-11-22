import io, re, zipfile
from datetime import datetime, date, timedelta
from openpyxl import load_workbook

def preview(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(i.file_size for i in z.infolist())>100*1024*1024:raise ValueError('Arkusz przekracza limit rozpakowanych danych')
    wb=load_workbook(io.BytesIO(data),data_only=False,read_only=True);sheet=wb.active
    rows=[]
    for values in sheet.iter_rows(min_row=3,max_row=min(sheet.max_row,1002),max_col=9,values_only=True):
        _,ref,applicant,title,received,deadline,answered,owner,_=values
        if not ref:continue
        warnings=[]
        def day(value):return value.date() if isinstance(value,datetime) else value if isinstance(value,date) else None
        rec=day(received);due=day(deadline);ans=day(answered)
        if not rec:warnings.append('Niepoprawna data wpływu')
        if isinstance(deadline,str) and deadline.startswith('='):
            if re.fullmatch(r'=E\d+\+14',deadline) and rec:due=rec+timedelta(days=14)
            else:warnings.append('Formuła terminu wymaga ręcznej weryfikacji')
        if not due:
            dates=re.findall(r'\d{2}\.\d{2}\.\d{4}',str(deadline))
            if dates:due=datetime.strptime(dates[0],'%d.%m.%Y').date()
            warnings.append('Termin opisowy lub niepoprawny — potwierdź datę i historię powiadomień')
        if due and rec and due<rec:warnings.append('Termin wcześniejszy od wpływu')
        if ans and rec and ans<rec:warnings.append('Odpowiedź wcześniejsza od wpływu')
        elif ans and due and ans>due:warnings.append('Odpowiedź po terminie — sprawdź, czy przedłużono termin (kwerenda) i odnotuj to w sprawie')
        rows.append({'reference':str(ref),'title':str(title or ''),'applicant':str(applicant or ''),'received':rec,'deadline':due,'answered':ans,'owner':str(owner or ''),'questions':[],'delivery':'','warnings':warnings,'source_deadline':str(deadline)})
    wb.close();return {'rows':rows,'note':'Wszystkie rekordy wymagają weryfikacji. Oryginalne pliki pozostają niezmienione.'}
