// Render 16:9 episode cover PNGs (1920x1080 via 1280x720 @ 1.5x DPR) using Puppeteer.
// Usage: node render_covers.mjs <manifest.json>
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import puppeteer from "puppeteer-core";

const manifestPath = path.resolve(process.argv[2]);
const manifest = JSON.parse(readFileSync(manifestPath, "utf-8"));

const exe = [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
].find(existsSync);

if (!exe) {
  throw new Error("Could not find Chrome or Edge executable");
}

const browser = await puppeteer.launch({
  executablePath: exe,
  headless: true,
  args: [
    "--allow-file-access-from-files",
    "--force-device-scale-factor=1.5",
    "--hide-scrollbars",
  ],
});

const page = await browser.newPage();
page.on("pageerror", (e) => {
  console.error("PAGE ERROR:", e.message);
  process.exitCode = 1;
});

let curW = 0;
let curH = 0;

for (const job of manifest.jobs) {
  const w = job.width || 1280;
  const h = job.height || 720;
  if (w !== curW || h !== curH) {
    await page.setViewport({ width: w, height: h, deviceScaleFactor: 1.5 });
    curW = w;
    curH = h;
  }
  mkdirSync(path.dirname(job.html), { recursive: true });
  mkdirSync(path.dirname(job.png), { recursive: true });
  await page.goto(pathToFileURL(path.resolve(job.html)).href, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => Promise.all([...document.images].map((i) => i.decode().catch(() => {}))));
  await page.screenshot({ path: job.png, type: "png", clip: { x: 0, y: 0, width: w, height: h } });
  console.log(`rendered ${job.tag} -> ${job.png}`);
}

await browser.close();
