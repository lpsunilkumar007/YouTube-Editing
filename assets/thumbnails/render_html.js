// Render an HTML thumbnail to PNG with headless Chrome (puppeteer-core from the HyperFrames install) and report the
// on-page boxes of every element marked data-qa="...", so QA can check overlaps/margins exactly.
// usage: node render_html.js <in.html> <out.png> <boxes.json>
const path = require("path");
const { createRequire } = require("module");
const puppeteer = createRequire(path.join(process.env.HF_DIR, "package.json"))("puppeteer-core");
(async () => {
  const [inp, out, boxes] = process.argv.slice(2);
  const browser = await puppeteer.launch({ executablePath: process.env.CHROME, headless: "shell", args: ["--no-sandbox", "--font-render-hinting=none"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 720, deviceScaleFactor: 1 });
  await page.goto("file:///" + inp.split(path.sep).join("/"), { waitUntil: "networkidle0", timeout: 60000 });
  await page.evaluate(async () => { await document.fonts.ready; });
  const fonts = await page.evaluate(() => [...document.fonts].filter(f => f.status === "loaded").map(f => f.family + " " + f.weight));
  const b = await page.evaluate(() => [...document.querySelectorAll("[data-qa]")].map(e => {
    const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
    return { qa: e.dataset.qa, text: e.innerText || "", x: r.x, y: r.y, w: r.width, h: r.height, font_px: parseFloat(cs.fontSize), color: cs.color };
  }));
  await page.screenshot({ path: out, clip: { x: 0, y: 0, width: 1280, height: 720 } });
  require("fs").writeFileSync(boxes, JSON.stringify({ fonts, boxes: b }, null, 1));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
