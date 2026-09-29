import {chromium} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
const output=path.resolve('../output/unseen');
await fs.mkdir(output,{recursive:true});
const browser=await chromium.launch();
const context=await browser.newContext({baseURL:process.env.LCT_TEST_URL||'http://127.0.0.1:8013',viewport:{width:1440,height:1000},recordVideo:{dir:output,size:{width:1440,height:1000}}});
const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto(process.env.LCT_TEST_URL||'http://127.0.0.1:8013');
await page.waitForTimeout(1800);
await page.getByLabel('Загрузить PPTX-шаблон').setInputFiles(path.join(output,'public-test.pptx'));
await page.getByText(/слайдов · .* композиций/).waitFor();
await page.waitForTimeout(1800);
await page.getByLabel('Загрузить материалы').setInputFiles(path.resolve('../examples/content.json'));
await page.waitForTimeout(1800);
const responsePromise=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');
await page.getByRole('button',{name:'Создать презентацию'}).click();
const job=await (await responsePromise).json();
await page.getByRole('tab',{name:'Акценты',exact:true}).waitFor({timeout:240000});
for(const name of ['Последовательно','Сравнение','Акценты']){
 await page.getByRole('tab',{name,exact:true}).click();await page.waitForTimeout(1500);
 await page.getByRole('button',{name:'Следующий слайд'}).click();await page.waitForTimeout(1200);
}
await page.getByText('Текст выступления к слайду',{exact:true}).click();await page.waitForTimeout(2200);
for(const name of ['PPTX','PDF','HTML','Текст выступления']){
 const href=await page.getByRole('link',{name,exact:true}).getAttribute('href');
 const response=await context.request.get(href);if(!response.ok())throw new Error(`Download failed: ${name}`);
}
await page.screenshot({path:path.join(output,'result.png'),fullPage:true});
const result=await (await context.request.get('/api/jobs/'+job.id)).json();
await fs.writeFile(path.join(output,'browser-run.json'),JSON.stringify({job:result,console_errors:errors},null,2));
await page.waitForTimeout(1800);const video=page.video();await context.close();await video.saveAs(path.join(output,'demo.webm'));await browser.close();
console.log(JSON.stringify({job:job.id,status:result.status,timing:result.result?.timing,errors,video:path.join(output,'demo.webm')}));
if(result.status!=='completed'||errors.length)process.exitCode=1;
