from lct_design.models import ContentPackage
from lct_design.outline import build_sections,numbers
from lct_design.planner import plan_content
from lct_design.template import analyze_template

BRIEF='Пилот: 120 компаний, 3 месяца. Цель — 5 000 платящих компаний за первый год.'

def test_numbers_are_normalized():
    assert numbers('5 000 и 2,5% и 120')=={'5000','2.5','120'}

def test_ungrounded_numbers_are_removed_but_grounded_content_stays():
    data={'slides':[
        {'title':'Почта для малого бизнеса','bullets':['Своё доменное имя','Перенос почты']},
        {'title':'Пилот подтвердил спрос','bullets':['120 компаний за 3 месяца','Рост выручки на 40%'],'notes':'Выросли на 40%.'},
        {'title':'Выручка 7 млн','bullets':['x']},
        {'title':'Цель года','bullets':['5000 платящих компаний'],'chart':{'categories':['Пилот','Цель'],'series':{'Компании':[120,5000]}}},
        {'title':'Прогноз','bullets':['Рост'],'chart':{'categories':['2026','2027'],'series':{'Компании':[120,9000]}}},
    ]}
    sections,warnings=build_sections(data,BRIEF,5)
    titles=[s.title for s in sections]
    assert 'Выручка 7 млн' not in titles and len(sections)==4
    pilot=next(s for s in sections if s.title=='Пилот подтвердил спрос')
    assert pilot.bullets==['120 компаний за 3 месяца'] and pilot.notes==''
    assert next(s for s in sections if s.title=='Цель года').chart is not None
    assert next(s for s in sections if s.title=='Прогноз').chart is None
    assert any('40' not in w and 'не из брифа' in w for w in warnings)

def test_brief_only_live_plan_writes_requested_slides(template,monkeypatch):
    calls=[]
    def infer(system,payload,*args,**kwargs):
        calls.append(payload)
        if 'brief' in payload:
            return {'slides':[{'title':'Вывод '+'абвгдежзик'[i],'bullets':['Пилот на 120 компаниях'],'notes':'Пилот шёл 3 месяца.'} for i in range(10)]},{'total_tokens':5},'m'
        return {'slides':[{'source_ids':[s['id']],'title':s['title'],'layouts':{}} for s in payload['sources']]},{'total_tokens':7},'m'
    monkeypatch.setattr('lct_design.planner.infer_json',infer)
    plan=plan_content(ContentPackage(title='VK Mail',brief=BRIEF,purpose='feature'),analyze_template(template),10,'live')
    assert len(plan.slides)==10 and plan.outline_usage=={'total_tokens':5}
    assert calls[0]['purpose']=='feature' and calls[0]['slide_count']==10
    assert plan.slides[0].speaker_notes=='Пилот шёл 3 месяца.'

def test_structured_items_lead_note_and_button_are_grounded():
    data={'slides':[{'title':'Пилот подтвердил спрос','lead':'Итоги за 3 месяца','note':'Данные за 7 недель',
        'items':[{'heading':'Компании','value':'120','text':'участвовали в пилоте'},{'heading':'Рост','value':'40%','text':'выручки'}]},
        {'title':'Одобрите запуск','button':'Открыть план'}]}
    sections,warnings=build_sections(data,BRIEF,2)
    first=sections[0]
    assert first.lead=='Итоги за 3 месяца' and first.note==''
    assert [(i.heading,i.value) for i in first.items]==[('Компании','120'),('Рост','')] or [(i.heading,i.value) for i in first.items]==[('Компании','120')]
    assert sections[1].button=='Открыть план'
