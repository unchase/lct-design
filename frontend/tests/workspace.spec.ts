import {test,expect} from '@playwright/test';
test('upload, generate, inspect three variants and downloads',async({page,request})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await expect(page.getByRole('heading',{name:/Содержание — ваше/})).toBeVisible();
 await page.screenshot({path:'../output/browser/empty.png',fullPage:true});
 const template=process.env.LCT_TEST_TEMPLATE;
 test.skip(!template,'Set LCT_TEST_TEMPLATE to a user-owned PPTX fixture');
 await page.getByLabel('Загрузить PPTX-шаблон').setInputFiles(template!);
 await expect(page.getByText(/слайдов · .* композиций/)).toBeVisible();
 await page.getByRole('button',{name:/Попробовать на демонстрационном/}).click();
 await expect(page.getByText(/12 разделов/)).toBeVisible();
 await page.getByRole('button',{name:'Создать презентацию'}).click();
 await expect(page.getByRole('tab',{name:'Акценты',exact:true})).toBeVisible({timeout:150000});
 await page.getByRole('tab',{name:'Акценты',exact:true}).click();
 await expect(page.getByLabel('Предпросмотр слайда').locator('img')).toBeVisible();
 await page.getByRole('button',{name:'Следующий слайд'}).click();
 await expect(page.getByText('2 / 12',{exact:true})).toBeVisible();
 await page.getByText('Текст выступления к слайду', {exact:true}).click();
 await expect(page.locator('.speaker-notes p')).not.toBeEmpty();
 await expect(page.getByRole('link',{name:'Текст выступления',exact:true})).toBeVisible();
 for(const name of ['PPTX','PDF','HTML']){
   const url=await page.getByRole('link',{name,exact:true}).getAttribute('href');
   expect((await request.get(url!)).status()).toBe(200);
 }
 await page.screenshot({path:'../output/browser/result.png',fullPage:true});
 expect(errors).toEqual([]);
});

test('reject wrong file type without losing the input screen',async({page})=>{
 await page.goto('/');await page.getByLabel('Загрузить PPTX-шаблон').setInputFiles({name:'bad.pptx',mimeType:'application/octet-stream',buffer:Buffer.from('not a zip')});
 await expect(page.getByRole('alert')).toBeVisible();
 await expect(page.getByRole('button',{name:'Создать презентацию'})).toBeDisabled();
});
