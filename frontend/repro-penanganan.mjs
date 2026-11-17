import { chromium } from '@playwright/test';
const BASE = 'http://127.0.0.1:1426';
const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'id-ID', timezoneId: 'Asia/Jakarta' });
const page = await ctx.newPage();
const errs = [];
page.on('pageerror', e => errs.push(e.message));
const snap = async (label) => {
  const h = await page.evaluate(() => {
    const heads = [...document.querySelectorAll('h2')].map(x => x.textContent.trim());
    const status = document.querySelector('.handling-form select')?.value;
    const tindakan = document.querySelector('.handling-form input')?.value;
    const ev = [...document.querySelectorAll('.timeline li')].map(x => x.innerText.replace(/\s+/g, ' ').trim());
    const hist = [...document.querySelectorAll('.panel table tbody tr')].map(x => x.innerText.replace(/\s+/g, ' ').trim());
    const badge = [...document.querySelectorAll('.panel-title .badge')].map(x => x.textContent.trim());
    return { heads, status, tindakan, ev, hist, badge };
  });
  console.log('\n### ' + label);
  console.log('status select:', h.status, '| tindakan:', h.tindakan, '| badge:', h.badge);
  console.log('events:', h.ev);
  console.log('history rows:', h.hist.length, h.hist.slice(0, 3));
};
try {
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.getByLabel('Email', { exact: true }).fill('yanto@spram.local');
  await page.getByLabel('Password', { exact: true }).fill('JAWkFpZqLYawHa1CmDhNfu3c');
  await page.getByRole('button', { name: 'Masuk', exact: true }).click();
  await page.waitForLoadState('networkidle');
  await page.locator('.sidebar nav').getByRole('button', { name: 'Penanganan', exact: true }).click();
  await page.waitForLoadState('networkidle');
  const items = page.locator('.handling-item');
  console.log('students listed:', await items.count());
  const pick = async (sid) => { await items.filter({ hasText: sid }).first().click(); await page.waitForTimeout(2500); };
  await pick('BATCH-00002'); await snap('BATCH-00002 (first)');
  await pick('BATCH-00004'); await snap('BATCH-00004 after switch');
  await pick('BATCH-00002'); await snap('BATCH-00002 back');
  await pick('BATCH-00003'); await snap('BATCH-00003 (no case)');
  await page.screenshot({ path: '/tmp/penanganan-switch.png', fullPage: true });
  console.log('\nJS errors:', errs);
} finally { await ctx.close(); await browser.close(); }
