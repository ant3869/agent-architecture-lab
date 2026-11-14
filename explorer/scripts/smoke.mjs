// Browser smoke test for the built explorer.
//   npm run build && npm run smoke [-- --shots <dir>]      (requires Playwright, see below)
// Serves dist/ with `vite preview`, visits every route (including every solution of every
// pattern), and fails on: console errors, failed requests, a diagram that did not render,
// or a view that rendered its error state.
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// Playwright is resolved at run time (local devDependency or a global install on NODE_PATH)
// so that the explorer itself carries no browser-automation dependency.
let chromium;
try {
  ({ chromium } = createRequire(import.meta.url)("playwright"));
} catch {
  console.error("The smoke test needs Playwright: npm install --no-save playwright && npx playwright install chromium");
  process.exit(2);
}

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const shotsArg = process.argv.indexOf("--shots");
const shots = shotsArg > -1 ? process.argv[shotsArg + 1] : null;
const port = 4173;
const origin = `http://127.0.0.1:${port}`;
const catalog = JSON.parse(readFileSync(join(root, "public", "data", "catalog.json"), "utf8"));

const routes = ["#/", "#/guide", "#/sources", "#/compare", "#/results"];
for (const p of catalog.patterns) {
  routes.push(`#/compare/${p.id}`);
  for (const s of p.solutions) routes.push(`#/patterns/${p.id}?s=${s.id}`);
}
for (const id of catalog.manifest.experiments) routes.push(`#/results/${id}`);
for (const t of catalog.traces) routes.push(`#/traces/${t.id}`);

async function waitForServer() {
  for (let i = 0; i < 60; i++) {
    try {
      if ((await fetch(origin)).ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error("vite preview did not start");
}

// Run the installed Vite CLI with Node directly; spawning npx fails on Windows without a shell.
const viteCli = join(root, "node_modules", "vite", "bin", "vite.js");
const server = spawn(process.execPath, [viteCli, "preview", "--port", String(port), "--strictPort", "--host", "127.0.0.1"], { cwd: root, stdio: "ignore" });
const problems = [];
let browser;
try {
  await waitForServer();
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: shots ? 2 : 1 });
  page.on("console", (m) => m.type() === "error" && problems.push(`console error on ${page.url()}: ${m.text()}`));
  page.on("pageerror", (e) => problems.push(`page error on ${page.url()}: ${e.message}`));
  page.on("requestfailed", (r) => problems.push(`request failed: ${r.url()}`));
  page.on("response", (r) => r.status() >= 400 && problems.push(`HTTP ${r.status()}: ${r.url()}`));
  if (shots) mkdirSync(shots, { recursive: true });
  await page.goto(`${origin}/`);
  for (const route of routes) {
    await page.evaluate((h) => {
      window.location.hash = h;
    }, route);
    await page.waitForFunction(() => !document.querySelector('[role="status"]') && !document.querySelector('[data-diagram="loading"]'), null, { timeout: 15000 });
    await page.waitForTimeout(60);
    if (await page.locator('[role="alert"]').count()) problems.push(`error state rendered at ${route}`);
    if (await page.locator('[data-diagram="error"]').count()) problems.push(`diagram failed to render at ${route}`);
    const h1 = await page.locator("h1").first().textContent();
    if (!h1) problems.push(`no heading at ${route}`);
    if ((await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)) > 2) problems.push(`horizontal overflow at ${route}`);
    if (shots) await page.screenshot({ path: join(shots, `${route.replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "") || "home"}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 390, height: 800 });
  for (const route of ["#/", "#/guide", "#/sources", "#/compare", "#/results", `#/traces/${catalog.traces[0].id}`, ...catalog.patterns.map((p) => `#/patterns/${p.id}`)]) {
    await page.evaluate((h) => {
      window.location.hash = h;
    }, route);
    await page.waitForFunction(() => !document.querySelector('[role="status"]') && !document.querySelector('[data-diagram="loading"]'), null, { timeout: 15000 });
    await page.waitForTimeout(60);
    if ((await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)) > 2) problems.push(`horizontal overflow on a phone-width viewport at ${route}`);
  }
} catch (err) {
  problems.push(`smoke run aborted: ${err instanceof Error ? err.message : String(err)}`);
} finally {
  await browser?.close();
  server.kill();
}
if (problems.length) {
  console.error(`FAILED (${problems.length})\n` + [...new Set(problems)].join("\n"));
  process.exit(1);
}
console.log(`ok: ${routes.length} routes, no console errors, all diagrams rendered`);
