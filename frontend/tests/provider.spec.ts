import {test,expect,Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const dist=resolve(dirname(fileURLToPath(import.meta.url)),'../dist');

// UI contract tests: all API responses are local mocks. No external provider is contacted.
const empty={provider:'custom',base_url:'',model:'',vision_enabled:false,vision_model:'',json_mode:true,competition_mode:true,model_license:'',model_parameters_b:0,model_card:'',vision_license:'',vision_parameters_b:0,vision_card:'',revision:'mock-0',has_key:false,ready:false,issues:['Укажите Base URL и ID текстовой модели']};
const ready={...empty,base_url:'https://provider.example/v1',model:'mock/text-7b',competition_mode:false,has_key:true,ready:true,issues:[]};
async function fixture(page:Page,initial=empty){
 let state={...initial};let puts=0,probes=0,catalogs=0,failSave=false;const sent:Record<string,unknown>[]=[];
 await page.route('**/*',async route=>{
  const request=route.request(),url=new URL(request.url()),path=url.pathname;
  const json=(data:unknown,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
  if(path==='/api/provider'){
   if(request.method()==='PUT'){
    puts++;if(failSave)return route.abort('failed');
    const body=request.postDataJSON();sent.push(body);const {api_key,clear_key,...config}=body;
    state={...config,has_key:clear_key?false:!!api_key||(state.has_key&&state.base_url===config.base_url),revision:'mock-'+puts,ready:!!config.base_url&&!!config.model&&(!config.competition_mode||(['MIT','Apache-2.0'].includes(config.model_license)&&config.model_parameters_b>0&&config.model_parameters_b<=35&&!!config.model_card)),issues:[]};
    if(!state.ready)state.issues=['Текстовая модель: нужны MIT/Apache-2.0, не более 35B параметров и карточка модели'];return json(state);
   }
   if(request.method()==='DELETE'){state={...empty};return json(state)}return json(state);
  }
  if(path==='/api/provider/models'){catalogs++;return json({detail:'mock catalog unavailable'},400)}
  if(path==='/api/provider/test'){probes++;return json({ok:true,message:'Mock: короткий ответ получен.',model:state.model,vision:'disabled',seconds:0.2})}
  if(path==='/api/templates'||path==='/api/jobs')return json([]);
  if(path==='/api/health')return json({live_configured:state.ready});
  if(path.startsWith('/api/'))return json({detail:'Unexpected mock request'},404);
  const file=path.startsWith('/assets/')?resolve(dist,'.'+path):resolve(dist,'index.html');
  const contentType=file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'text/html';
  return route.fulfill({contentType,body:readFileSync(file)});
 });
 await page.goto('http://provider-ui.mock/');
 await page.getByRole('button',{name:'Настройки подключения модели'}).click();
 await expect(page.getByRole('heading',{name:'Подключение модели',exact:true})).toBeVisible();
 await expect(page.getByRole('combobox',{name:'Провайдер',exact:true})).toBeVisible();
 return {counts:()=>({puts,probes,catalogs}),sent,state:()=>state,failSave:()=>{failSave=true}};
}

test('mock API: save OpenRouter, clear secret and explicitly select live mode',async({page})=>{
 const f=await fixture(page);
 await page.getByRole('combobox',{name:'Провайдер',exact:true}).selectOption('openrouter');
 await expect(page.getByLabel('Base URL',{exact:true})).toHaveValue('https://openrouter.ai/api/v1');
 await page.getByLabel('API-ключ',{exact:true}).fill('secret-only-in-memory');
 await page.getByLabel('ID текстовой модели',{exact:true}).fill('mock/text-7b');
 await page.getByLabel('Конкурсный режим').uncheck();
 await expect(page.getByText(/Режим разработки: ограничения/)).toBeVisible();
 await page.getByRole('button',{name:'Сохранить настройки'}).click();
 await expect(page.getByText('Настройки сохранены. Соединение ещё не проверено.')).toBeVisible();
 await expect(page.getByLabel('API-ключ',{exact:true})).toHaveValue('');
 expect(f.sent[0].api_key).toBe('secret-only-in-memory');
 expect(f.sent[0]).not.toHaveProperty('has_key');expect(f.sent[0]).not.toHaveProperty('revision');
 expect(f.counts()).toEqual({puts:1,probes:0,catalogs:0});
 expect(await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}))).not.toContain('secret-only-in-memory');
 await page.getByRole('button',{name:'Закрыть',exact:true}).click();
 await expect(page.getByText('AI-модель: mock/text-7b')).toBeVisible();
 await expect(page.getByRole('combobox',{name:'Режим',exact:true})).toHaveValue('offline');
 await page.getByRole('combobox',{name:'Режим',exact:true}).selectOption('live');
 await page.reload();await page.getByRole('button',{name:'Настройки подключения модели'}).click();
 await expect(page.getByLabel('API-ключ',{exact:true})).toHaveValue('');
 await expect(page.getByLabel('API-ключ',{exact:true})).toHaveAttribute('placeholder','Ключ сохранён — оставьте поле пустым');
 expect(f.counts().probes).toBe(0);
});

test('mock API: catalog failure allows manual ID; paid probe is explicit and becomes stale after edits',async({page})=>{
 const f=await fixture(page,ready);
 expect(f.counts().probes).toBe(0);
 await page.getByRole('button',{name:'Загрузить каталог'}).click();
 await expect(page.getByText(/Каталог недоступен. Введите ID/)).toBeVisible();
 await page.getByLabel('ID текстовой модели',{exact:true}).fill('mock/manual-model');
 await expect(page.getByRole('button',{name:'Проверить соединение',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'Сохранить настройки'}).click();
 await expect(page.getByText('Настройки сохранены. Соединение ещё не проверено.')).toBeVisible();
 expect(f.counts().probes).toBe(0);
 await page.getByRole('button',{name:'Проверить соединение',exact:true}).click();
 await expect(page.getByText('Соединение проверено',{exact:true})).toBeVisible();expect(f.counts().probes).toBe(1);
 await page.getByLabel('ID текстовой модели',{exact:true}).fill('mock/changed');
 await expect(page.getByText('Соединение проверено',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Проверить соединение',exact:true})).toBeDisabled();
});

test('mock API: invalid URL cannot save, failed save preserves draft, leaving clears key',async({page})=>{
 const f=await fixture(page,ready);
 await page.getByLabel('Base URL',{exact:true}).fill('not a URL');
 await page.getByRole('button',{name:'Сохранить настройки'}).click();
 expect(f.counts().puts).toBe(0);
 await page.getByLabel('Base URL',{exact:true}).fill('http://localhost:11434/v1');
 await expect(page.getByText(/Старый ключ не переносится/)).toBeVisible();
 await page.getByLabel('API-ключ',{exact:true}).fill('draft-secret');f.failSave();
 await page.getByRole('button',{name:'Сохранить настройки'}).click();
 await expect(page.getByRole('alert')).toContainText('Введённые данные остались в форме');
 await expect(page.getByLabel('API-ключ',{exact:true})).toHaveValue('draft-secret');
 await expect(page.getByLabel('Base URL',{exact:true})).toHaveValue('http://localhost:11434/v1');
 await page.getByRole('button',{name:'Закрыть',exact:true}).click();
 await page.getByRole('button',{name:'Настройки подключения модели'}).click();
 await expect(page.getByLabel('API-ключ',{exact:true})).toHaveValue('');
 await expect(page.getByLabel('Base URL',{exact:true})).toHaveValue(ready.base_url);
});

test('mock API: competition declarations and optional vision metadata are separate',async({page})=>{
 const f=await fixture(page,ready);
 await page.getByLabel('Конкурсный режим').check();
 await page.getByRole('button',{name:'Сохранить настройки'}).click();
 await expect(page.getByText('Подключение требует настройки',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Проверить соединение',exact:true})).toBeDisabled();
 await page.getByRole('combobox',{name:'Лицензия текстовой модели',exact:true}).selectOption('Apache-2.0');
 await page.getByLabel('Параметры текстовой модели, млрд',{exact:true}).fill('7');
 await page.getByLabel('Карточка текстовой модели',{exact:true}).fill('https://model.example/text');
 await page.getByLabel('Подключить визуальную модель').check();
 await page.getByLabel('ID визуальной модели',{exact:true}).fill('mock/vision-7b');
 await page.getByRole('combobox',{name:'Лицензия визуальной модели',exact:true}).selectOption('MIT');
 await page.getByLabel('Параметры визуальной модели, млрд',{exact:true}).fill('7');
 await page.getByLabel('Карточка визуальной модели',{exact:true}).fill('https://model.example/vision');
 await page.getByRole('button',{name:'Сохранить настройки'}).click();
 await expect(page.getByText('Настройки сохранены. Соединение ещё не проверено.')).toBeVisible();
 expect(f.sent.at(-1)).toMatchObject({model_license:'Apache-2.0',vision_license:'MIT',model_card:'https://model.example/text',vision_card:'https://model.example/vision',vision_enabled:true});
 expect(f.counts().probes).toBe(0);
});

test('mock API: mobile settings remain reachable and do not overflow',async({page})=>{
 await page.setViewportSize({width:390,height:844});await fixture(page,ready);
 await expect(page.getByLabel('Base URL',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await page.getByLabel('ID текстовой модели',{exact:true}).fill('mock/new-model');
 await page.getByRole('button',{name:'Сохранить настройки'}).click();
 await expect(page.getByText('Настройки сохранены. Соединение ещё не проверено.')).toBeVisible();
});
