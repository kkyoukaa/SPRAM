import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const base=process.env.BASE_URL||'http://127.0.0.1:18415';
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
for(const viewport of [{width:1280,height:800},{width:768,height:1024},{width:390,height:844}]){
 const context=await browser.newContext({viewport});const page=await context.newPage();await page.goto(base,{waitUntil:'networkidle'});
 assert.equal(await page.locator('html').getAttribute('lang'),'id');
 assert.equal(await page.locator('input:not([type=hidden])').count(),await page.locator('label input, input[aria-label]').count());
 assert(await page.locator(':focus-visible').count()===0);
 await page.keyboard.press('Tab');assert(await page.locator(':focus-visible').count()>0,'focus visible missing');
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow ${viewport.width}`);
 await context.close();
}
await browser.close();console.log('PASS: lang, labels, focus visible, no horizontal overflow at 1280/768/390');
