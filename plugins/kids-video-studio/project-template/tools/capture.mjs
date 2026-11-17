// Frame-accurate capture of an H5 scene page into mp4 segments.
// The page must expose window.SEGMENTS {id:{dur,cues}} and window.renderAt(id, seconds).
// Usage: node capture.mjs <index.html> <outDir> [segId ...] [--still segId:seconds ...]
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import puppeteer from "puppeteer-core";

const FPS = 24;
const args = process.argv.slice(2);
const stills = [];
for (let i = args.length - 2; i >= 0; i--) if (args[i] === "--still") stills.push(...args.splice(i, 2).slice(1));
// --scale <factor>: device pixel ratio (1.5 renders the 1280x720 stage as 1920x1080)
let scale = 1;
for (let i = args.length - 2; i >= 0; i--) if (args[i] === "--scale") scale = parseFloat(args.splice(i, 2)[1]);
// --dur <path relative to the page>: alternative durations file (another voice variant)
let durQuery = "";
for (let i = args.length - 2; i >= 0; i--) if (args[i] === "--dur") durQuery = "&dur=" + encodeURIComponent(args.splice(i, 2)[1]);
const [html, outDir, ...only] = args;
mkdirSync(outDir, { recursive: true });

const exe = ["C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"].find(existsSync);
const browser = await puppeteer.launch({ executablePath: exe, headless: true,
  args: ["--allow-file-access-from-files", `--force-device-scale-factor=${scale}`, "--hide-scrollbars"] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 720, deviceScaleFactor: scale });
page.on("pageerror", e => { console.error("PAGE ERROR", e.message); process.exitCode = 1; });
await page.goto(pathToFileURL(path.resolve(html)).href + "?capture=1" + durQuery, { waitUntil: "load" });
await page.evaluate(() => document.fonts.ready);
const segments = await page.evaluate(() => window.SEGMENTS);
writeFileSync(path.join(outDir, "timeline.json"), JSON.stringify(segments, null, 1));
const clip = { x: 0, y: 0, width: 1280, height: 720 };

if (stills.length) {
  for (const s of stills) {
    const [id, t] = s.split(":");
    await page.evaluate((id, t) => window.renderAt(id, t), id, parseFloat(t));
    await page.screenshot({ path: path.join(outDir, `still_${id}_${t}.jpg`), type: "jpeg", quality: 80, clip });
  }
} else {
  for (const [id, seg] of Object.entries(segments)) {
    if (only.length && !only.includes(id)) continue;
    const n = Math.round(seg.dur * FPS), out = path.join(outDir, `${id}.mp4`);
    const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg",
      "-i", "-", "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", String(FPS), out],
      { stdio: ["pipe", "inherit", "inherit"] });
    const done = new Promise((res, rej) => ff.on("close", c => (c === 0 ? res() : rej(new Error("ffmpeg " + c)))));
    for (let f = 0; f < n; f++) {
      await page.evaluate((id, t) => window.renderAt(id, t), id, f / FPS);
      const buf = await page.screenshot({ type: "jpeg", quality: 96, clip });
      if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once("drain", r));
    }
    ff.stdin.end(); await done;
    console.log(`${id}: ${n} frames (${seg.dur.toFixed(2)}s) -> ${out}`);
  }
}
await browser.close();
