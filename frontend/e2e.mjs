import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const BASE=process.env.BASE_URL||'http://127.0.0.1:1415';
const credentials=JSON.parse(fs.readFileSync('../data/e2e-login.json','utf8'));
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'id-ID',timezoneId:'Asia/Jakarta'});
const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
fs.mkdirSync('../docs/screenshots',{recursive:true});
async function nav(name){await page.locator('.sidebar nav').getByRole('button',{name,exact:true}).click();await page.waitForLoadState('networkidle');}
try{
 await page.goto(BASE,{waitUntil:'networkidle'});
 await page.getByLabel('Email',{exact:true}).fill(credentials.email);
 await page.getByLabel('Password',{exact:true}).fill(credentials.password);
 await page.getByRole('button',{name:'Masuk',exact:true}).click();
 await page.getByRole('heading',{name:'Setiap mahasiswa berarti.'}).waitFor();
 await page.waitForLoadState('networkidle');
 assert.equal(await page.locator('[role="alert"]').count(),0);
 await page.screenshot({path:'../docs/screenshots/dashboard-desktop.png',fullPage:true});
 for(const name of ['Mahasiswa','Model Center','Pengguna & audit','Laporan','Unggah CSV','Prediksi individual']){
  await nav(name);assert.equal(await page.locator('[role="alert"]').count(),0,`Alert on ${name}: ${await page.locator('[role="alert"]').allTextContents()}`);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Overflow ${name}`);
 }
 await nav('Model Center');
 await page.getByRole('button',{name:'Academic Update',exact:true}).click();
 await page.waitForLoadState('networkidle');
 assert(await page.locator('tbody tr').count()>=3,'Three comparison models required');
 await page.screenshot({path:'../docs/screenshots/models-desktop.png',fullPage:true});
 await page.locator('tbody .text-button').first().click();
 await page.getByRole('heading',{name:'Confusion matrix',exact:true}).waitFor();
 assert.equal(await page.locator('[role="alert"]').count(),0);
 await nav('Mahasiswa');
 await page.locator('tbody .text-button').first().click();
 await page.getByRole('heading',{name:'Riwayat snapshot'}).waitFor();
 await page.waitForLoadState('networkidle');
 await page.getByLabel('Catatan',{exact:true}).fill('QA E2E: verifikasi tindak lanjut nonpunitif.');
 await page.getByLabel('Tanggal tindak lanjut',{exact:true}).fill('2026-12-01');
 await page.getByRole('button',{name:'Simpan tindak lanjut'}).click();
 await page.getByText('Tindak lanjut tersimpan.',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Seberapa yakin model?'}).click();
 await page.locator('.assistant-answer').waitFor();
 assert((await page.locator('.assistant-answer').innerText()).length>30);
 await nav('Ringkasan');
 await page.setViewportSize({width:390,height:844});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile overflow');
 await page.getByRole('button',{name:'Buka navigasi',exact:true}).click();
 await page.locator('.sidebar nav').getByRole('button',{name:'Mahasiswa',exact:true}).click();
 await page.waitForLoadState('networkidle');
 await page.screenshot({path:'../docs/screenshots/students-mobile.png',fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile students overflow');
 assert.deepEqual(errors,[]);
 console.log('PASS: real admin login, all navigation, three models, evaluation, student timeline, intervention, assistant, desktop/mobile, no JS errors');
}finally{await context.close();await browser.close();}
