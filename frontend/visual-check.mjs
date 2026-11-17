import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import fs from "node:fs";
const base = process.env.BASE_URL || "http://127.0.0.1:1415";
fs.mkdirSync("../docs/screenshots", { recursive: true });
const browser = await chromium.launch({
  headless: true,
  args: ["--no-sandbox"],
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  locale: "id-ID",
  timezoneId: "Asia/Jakarta",
});
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
try {
  await page.goto(base, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Selamat datang." }).waitFor();
  assert.equal(
    await page.getByLabel("Email", { exact: true }).inputValue(),
    "",
  );
  assert.equal(
    await page.getByLabel("Password", { exact: true }).inputValue(),
    "",
  );
  await page.screenshot({
    path: "../docs/screenshots/login-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  );
  await page.screenshot({
    path: "../docs/screenshots/login-mobile.png",
    fullPage: true,
  });
  assert.deepEqual(errors, []);
  console.log(
    "PASS login desktop/mobile, empty credentials, no overflow, no JS errors",
  );
} finally {
  await context.close();
  await browser.close();
}
