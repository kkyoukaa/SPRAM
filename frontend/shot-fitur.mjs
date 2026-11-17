import {chromium} from '@playwright/test';
import fs from 'node:fs';
const BASE='http://127.0.0.1:1426';
const out='../docs/screenshots';
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});

// --- dosen: konsultasi + rekomendasi (crop elemen) ---
{
const page=await (await browser.newContext({viewport:{width:1500,height:1100},locale:'id-ID',timezoneId:'Asia/Jakarta'})).newPage();
await page.goto(BASE,{waitUntil:'networkidle'});
await page.getByLabel('Email',{exact:true}).fill('yanto@spram.local');
await page.getByLabel('Password',{exact:true}).fill('JAWkFpZqLYawHa1CmDhNfu3c');
await page.getByRole('button',{name:'Masuk',exact:true}).click();
await page.waitForLoadState('networkidle');
await page.locator('.sidebar nav').getByRole('button',{name:'Penanganan',exact:true}).click();
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1500);
// panel Penanganan sudah memilih mahasiswa pertama otomatis; tidak perlu klik kartu
const h=page.getByRole('heading',{name:'Verifikasi sinyal, lalu tentukan langkah'});
await h.waitFor({timeout:20000});
const sec=page.locator('section.consult').first();
await sec.scrollIntoViewIfNeeded(); await page.waitForTimeout(600);
const groups=page.getByRole('group',{name:/^Jawaban R/});
const n=await groups.count();
for(let i=0;i<n;i++){const ya=groups.nth(i).getByRole('button',{name:'Ya',exact:true}); if(await ya.count()) await ya.click();}
await page.waitForTimeout(400);
// elemen konsultasi bisa terus bergerak karena auto-scroll; ambil viewport bila tidak stabil
try{ await sec.screenshot({path:`${out}/fitur-konsultasi.png`,animations:'disabled',timeout:8000}); }
catch{ await page.screenshot({path:`${out}/fitur-konsultasi.png`}); }
await page.getByRole('button',{name:'Susun rekomendasi'}).click();
await page.getByRole('heading',{name:'Rekomendasi tindakan'}).waitFor({timeout:25000});
await page.waitForTimeout(1200);
const rec=page.locator('.recommendations').first();
try{ await rec.screenshot({path:`${out}/fitur-rekomendasi.png`,animations:'disabled',timeout:8000}); }
catch{ await page.screenshot({path:`${out}/fitur-rekomendasi.png`}); }
await page.context().close();
}

// --- admin: ringkasan, detail mahasiswa, model center ---
{
const c=JSON.parse(fs.readFileSync('../data/e2e-login.json','utf8'));
const page=await (await browser.newContext({viewport:{width:1440,height:1000},locale:'id-ID',timezoneId:'Asia/Jakarta'})).newPage();
await page.goto(BASE,{waitUntil:'networkidle'});
await page.getByLabel('Email',{exact:true}).fill(c.email);
await page.getByLabel('Password',{exact:true}).fill(c.password);
await page.getByRole('button',{name:'Masuk',exact:true}).click();
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1500);
await page.screenshot({path:`${out}/fitur-ringkasan.png`});
await page.locator('.sidebar nav').getByRole('button',{name:'Mahasiswa',exact:true}).click();
await page.waitForLoadState('networkidle');
await page.locator('tbody tr .text-button, tbody tr button').first().click();
await page.waitForLoadState('networkidle');
await page.waitForTimeout(2000);
await page.screenshot({path:`${out}/fitur-detail-mahasiswa.png`});
await page.locator('.sidebar nav').getByRole('button',{name:'Model Center',exact:true}).click();
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1800);
await page.screenshot({path:`${out}/fitur-model-center.png`});
await page.context().close();
}
await browser.close();
console.log('done');
