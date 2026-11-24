import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE = path.resolve(__dirname, "..");
const SELECTED_PATH = path.join(BASE, "cache", "selected_models.json");
const MANIFEST_PATH = path.join(BASE, "cache", "render_manifest.json");
const FORCE_RENDER = process.argv.includes("--force");
const BROWSER_LAUNCH_TIMEOUT_MS = 45_000;
const BROWSER_LAUNCH_RETRIES = 3;
const CDP_COMMAND_TIMEOUT_MS = 30_000;

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function sha256File(p) {
  return crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex");
}

function isPngFile(buf) {
  return buf.length > 8 && buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4e && buf[3] === 0x47;
}

function readPngDimensions(buf) {
  if (!isPngFile(buf) || buf.length < 24) return { width: 0, height: 0 };
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

function findBrowserExecutable() {
  if (process.env.CHROME_PATH && fs.existsSync(process.env.CHROME_PATH)) {
    return process.env.CHROME_PATH;
  }
  const candidates =
    process.platform === "win32"
      ? [
          "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
          "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
          "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
          "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        ]
      : process.platform === "darwin"
        ? [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
          ]
        : [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/microsoft-edge",
          ];

  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  for (const cmd of ["google-chrome", "chromium", "chromium-browser", "msedge"]) {
    const res = spawnSync(process.platform === "win32" ? "where" : "which", [cmd], { encoding: "utf-8" });
    if (res.status === 0 && res.stdout.trim()) {
      return res.stdout.trim().split(/\r?\n/)[0];
    }
  }
  throw new Error("No Chromium/Chrome/Edge executable found. Set CHROME_PATH env var.");
}

function parseSvgAspect(svgText) {
  const mTag = svgText.match(/<svg\b[^>]*>/i);
  if (!mTag) return { aspect: 4 / 3, hasViewBox: false };
  const tag = mTag[0];
  const vb = tag.match(/viewBox\s*=\s*["']\s*([-\d.]+)[,\s]+([-\d.]+)[,\s]+([-\d.]+)[,\s]+([-\d.]+)\s*["']/i);
  if (vb) {
    const w = parseFloat(vb[3]);
    const h = parseFloat(vb[4]);
    if (w > 0 && h > 0) return { aspect: w / h, hasViewBox: true, vbW: w, vbH: h };
  }
  const mw = tag.match(/\bwidth\s*=\s*["']\s*([\d.]+)(?:px)?\s*["']/i);
  const mh = tag.match(/\bheight\s*=\s*["']\s*([\d.]+)(?:px)?\s*["']/i);
  if (mw && mh) {
    const w = parseFloat(mw[1]);
    const h = parseFloat(mh[1]);
    if (w > 0 && h > 0) return { aspect: w / h, hasViewBox: false, vbW: w, vbH: h };
  }
  return { aspect: 4 / 3, hasViewBox: false };
}

function fixSvgForImg(svgText) {
  let s = svgText;
  const info = parseSvgAspect(s);
  if (!info.hasViewBox && info.vbW && info.vbH) {
    s = s.replace(/<svg\b/i, `<svg viewBox="0 0 ${info.vbW} ${info.vbH}"`);
  }
  s = s.replace(/&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)/g, "&amp;");
  return s;
}

class CDPClient {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.nextId = 1;
    this.pending = new Map();
  }
  async connect() {
    this.ws = new WebSocket(this.wsUrl);
    await new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = reject;
    });
    const rejectAll = (reason) => {
      for (const { reject, timer } of this.pending.values()) {
        clearTimeout(timer);
        reject(reason);
      }
      this.pending.clear();
    };
    this.ws.onclose = () => rejectAll(new Error("CDP WebSocket closed unexpectedly"));
    this.ws.onerror = (ev) => rejectAll(new Error(`CDP WebSocket error: ${ev?.message || "unknown"}`));
    this.ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data.toString());
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject, timer } = this.pending.get(msg.id);
        clearTimeout(timer);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(msg.error.message || JSON.stringify(msg.error)));
        else resolve(msg.result);
      }
    };
  }
  send(method, params = {}, timeoutMs = CDP_COMMAND_TIMEOUT_MS) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (this.pending.delete(id)) {
          reject(new Error(`CDP command timed out after ${timeoutMs}ms: ${method}`));
        }
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      try {
        this.ws.send(JSON.stringify({ id, method, params }));
      } catch (err) {
        clearTimeout(timer);
        this.pending.delete(id);
        reject(err);
      }
    });
  }
  close() {
    if (!this.ws) return;
    this.ws.onclose = null;
    this.ws.onerror = null;
    try { this.ws.close(); } catch {}
  }
}

function killProcessTree(proc, signal) {
  if (!proc?.pid) return;
  try {
    if (process.platform !== "win32") {
      process.kill(-proc.pid, signal);
    } else {
      proc.kill(signal);
    }
  } catch {
    try { proc.kill(signal); } catch {}
  }
}

async function closeBrowser(proc, cdp, userDataDir) {
  if (cdp) {
    try {
      await cdp.send("Browser.close", {}, 1500);
    } catch {}
    cdp.close();
  }
  if (proc && proc.exitCode === null && !proc.killed) {
    killProcessTree(proc, "SIGTERM");
    const exitDeadline = Date.now() + 1500;
    while (proc.exitCode === null && Date.now() < exitDeadline) {
      await sleep(50);
    }
    if (proc.exitCode === null) {
      killProcessTree(proc, "SIGKILL");
      await sleep(100);
    }
  } else if (proc?.pid && process.platform !== "win32") {
    // Ensure wrapper-spawned helper processes (cat, crashpad) are gone too.
    killProcessTree(proc, "SIGKILL");
  }
  if (userDataDir) {
    try { fs.rmSync(userDataDir, { recursive: true, force: true }); } catch {}
  }
}

async function findOrCreatePageTarget(port, allowCreate) {
  try {
    const r = await fetch(`http://127.0.0.1:${port}/json/list`, {
      signal: AbortSignal.timeout(2000),
    });
    if (r.ok) {
      const list = await r.json();
      const page = list.find((t) => t.type === "page" && t.webSocketDebuggerUrl);
      if (page) return page;
      if (allowCreate) {
        for (const method of ["PUT", "GET"]) {
          try {
            const nr = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {
              method,
              signal: AbortSignal.timeout(2000),
            });
            if (nr.ok) {
              const created = await nr.json();
              if (created?.webSocketDebuggerUrl) return created;
            }
          } catch {}
        }
      }
    }
  } catch {}
  return null;
}

async function launchBrowserOnce(browserPath) {
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "pelican-browser-"));
  const env = { ...process.env };
  if (process.platform === "linux") {
    // Avoid 25s DBus/Secret-Service activation stalls on headless Linux CI VMs.
    env.DBUS_SESSION_BUS_ADDRESS = "/dev/null";
    env.XDG_CONFIG_HOME = path.join(userDataDir, "xdg-config");
    env.XDG_CACHE_HOME = path.join(userDataDir, "xdg-cache");
  }

  const proc = spawn(
    browserPath,
    [
      "--headless=new",
      "--disable-gpu",
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-extensions",
      "--disable-background-networking",
      "--disable-default-apps",
      "--disable-sync",
      "--disable-translate",
      "--disable-component-update",
      "--disable-crash-reporter",
      "--disable-breakpad",
      "--no-first-run",
      "--no-default-browser-check",
      "--password-store=basic",
      "--use-mock-keychain",
      "--metrics-recording-only",
      "--mute-audio",
      "--hide-scrollbars",
      "--disable-background-timer-throttling",
      "--disable-renderer-backgrounding",
      "--disable-backgrounding-occluded-windows",
      "--disable-features=Translate,BackForwardCache,AcceptCHFrame,MediaRouter,OptimizationHints,DialMediaRouteProvider",
      "--remote-debugging-address=127.0.0.1",
      "--remote-debugging-port=0",
      `--user-data-dir=${userDataDir}`,
      "about:blank",
    ],
    {
      stdio: ["ignore", "ignore", "pipe"],
      detached: process.platform !== "win32",
      env,
    }
  );

  let stderrBuf = "";
  let debugPort = null;
  let portFoundAt = null;
  let exited = false;
  let exitInfo = "";

  proc.stderr?.on("data", (chunk) => {
    const text = chunk.toString("utf-8");
    stderrBuf = (stderrBuf + text).slice(-4000);
    if (!debugPort) {
      const m = text.match(/DevTools listening on ws:\/\/[^:]+:(\d+)\//);
      if (m) {
        debugPort = Number(m[1]);
        portFoundAt = Date.now();
      }
    }
  });
  proc.on("exit", (code, signal) => {
    exited = true;
    exitInfo = `code=${code}, signal=${signal}`;
  });
  proc.on("error", (err) => {
    exited = true;
    exitInfo = `spawn error: ${err.message}`;
  });

  const activePortFile = path.join(userDataDir, "DevToolsActivePort");
  const deadline = Date.now() + BROWSER_LAUNCH_TIMEOUT_MS;
  let target = null;

  while (Date.now() < deadline && !exited) {
    if (!debugPort && fs.existsSync(activePortFile)) {
      try {
        const firstLine = fs.readFileSync(activePortFile, "utf-8").split(/\r?\n/)[0]?.trim();
        const parsed = Number(firstLine);
        if (Number.isInteger(parsed) && parsed > 0) {
          debugPort = parsed;
          portFoundAt = Date.now();
        }
      } catch {}
    }
    if (debugPort) {
      const allowCreate = portFoundAt !== null && Date.now() - portFoundAt > 2000;
      target = await findOrCreatePageTarget(debugPort, allowCreate);
      if (target) break;
    }
    await sleep(150);
  }

  if (!target) {
    await closeBrowser(proc, null, userDataDir);
    const details = [
      exited ? `exited early (${exitInfo})` : `timed out after ${BROWSER_LAUNCH_TIMEOUT_MS}ms`,
      debugPort ? `port=${debugPort}` : "DevTools port never opened",
      stderrBuf.trim() ? `stderr:\n${stderrBuf.trim()}` : "no stderr output",
    ].join("; ");
    throw new Error(`Could not connect to headless browser CDP (${browserPath}): ${details}`);
  }
  return { proc, wsUrl: target.webSocketDebuggerUrl, userDataDir };
}

async function launchBrowser(browserPath) {
  let lastErr;
  for (let attempt = 1; attempt <= BROWSER_LAUNCH_RETRIES; attempt++) {
    try {
      return await launchBrowserOnce(browserPath);
    } catch (err) {
      lastErr = err;
      if (attempt < BROWSER_LAUNCH_RETRIES) {
        console.warn(`Browser launch attempt ${attempt}/${BROWSER_LAUNCH_RETRIES} failed, retrying... (${err.message})`);
        await sleep(1000);
      }
    }
  }
  throw lastErr;
}

async function renderSvgToPng(cdp, svgPath, outPngPath) {
  const rawText = fs.readFileSync(svgPath, "utf-8");
  const { aspect } = parseSvgAspect(rawText);
  const clampedAspect = Math.max(0.5, Math.min(2.5, aspect || 4 / 3));
  const width = 1024;
  const height = Math.max(400, Math.min(1400, Math.round(width / clampedAspect)));

  const fixedSvg = fixSvgForImg(rawText);
  const b64 = Buffer.from(fixedSvg, "utf-8").toString("base64");

  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: false,
  });

  const evalRes = await cdp.send("Runtime.evaluate", {
    awaitPromise: true,
    returnByValue: true,
    expression: `(async () => {
      document.documentElement.style.cssText = 'margin:0;padding:0;background:#ffffff;width:100%;height:100%;overflow:hidden;';
      document.body.style.cssText = 'margin:0;padding:16px;box-sizing:border-box;background:#ffffff;width:100%;height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden;';
      document.body.innerHTML = '';
      const img = document.createElement('img');
      img.style.cssText = 'max-width:100%;max-height:100%;width:100%;height:100%;object-fit:contain;display:block;';
      const ok = await new Promise((resolve) => {
        img.onload = () => resolve(true);
        img.onerror = () => resolve(false);
        img.src = 'data:image/svg+xml;base64,${b64}';
      });
      if (ok && img.naturalWidth > 0) {
        document.body.appendChild(img);
        await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
        return { ok: true, nw: img.naturalWidth, nh: img.naturalHeight, mode: 'img' };
      }
      return { ok: false, mode: 'img' };
    })()`,
  });

  const val = evalRes?.result?.value;
  if (!val?.ok) {
    const iframeHtml = `<!doctype html><html><body style="margin:0;padding:16px;box-sizing:border-box;background:#fff;width:100vw;height:100vh;display:flex;align-items:center;justify-content:center;overflow:hidden;"><style>svg{max-width:100%;max-height:100%;width:100%;height:100%;display:block;}</style>${fixedSvg}</body></html>`;
    const iframeB64 = Buffer.from(iframeHtml, "utf-8").toString("base64");
    await cdp.send("Runtime.evaluate", {
      awaitPromise: true,
      returnByValue: true,
      expression: `(async () => {
        document.body.style.cssText = 'margin:0;padding:0;background:#fff;width:100%;height:100%;overflow:hidden;';
        document.body.innerHTML = '';
        const fr = document.createElement('iframe');
        fr.setAttribute('sandbox', '');
        fr.style.cssText = 'border:0;width:100%;height:100%;display:block;';
        await new Promise((resolve) => {
          fr.onload = resolve;
          fr.src = 'data:text/html;base64,${iframeB64}';
          document.body.appendChild(fr);
        });
        await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
        return { ok: true, mode: 'iframe' };
      })()`,
    });
  }

  const shot = await cdp.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
  });
  const pngBuf = Buffer.from(shot.data, "base64");
  fs.mkdirSync(path.dirname(outPngPath), { recursive: true });
  fs.writeFileSync(outPngPath, pngBuf);
  const dims = readPngDimensions(pngBuf);
  return { ok: true, width: dims.width, height: dims.height, bytes: pngBuf.length, mode: val?.ok ? "svg_img" : "svg_iframe" };
}

async function convertRasterToPng(cdp, srcPath, outPngPath) {
  const buf = fs.readFileSync(srcPath);
  fs.mkdirSync(path.dirname(outPngPath), { recursive: true });
  if (isPngFile(buf)) {
    fs.writeFileSync(outPngPath, buf);
    const dims = readPngDimensions(buf);
    return { ok: true, width: dims.width, height: dims.height, bytes: buf.length, mode: "raster_copy_png" };
  }

  const ext = path.extname(srcPath).toLowerCase();
  const mime = ext === ".webp" ? "image/webp" : (ext === ".jpg" || ext === ".jpeg" ? "image/jpeg" : "image/png");
  const b64 = buf.toString("base64");

  const evalRes = await cdp.send("Runtime.evaluate", {
    awaitPromise: true,
    returnByValue: true,
    expression: `(async () => {
      const img = new Image();
      const ok = await new Promise((resolve) => {
        img.onload = () => resolve(true);
        img.onerror = () => resolve(false);
        img.src = 'data:${mime};base64,${b64}';
      });
      if (!ok || !img.naturalWidth) return { ok: false };
      const c = document.createElement('canvas');
      c.width = img.naturalWidth;
      c.height = img.naturalHeight;
      const ctx = c.getContext('2d');
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, c.width, c.height);
      ctx.drawImage(img, 0, 0);
      const dataUrl = c.toDataURL('image/png');
      return { ok: true, width: c.width, height: c.height, b64: dataUrl.split(',')[1] };
    })()`,
  });

  const val = evalRes?.result?.value;
  if (!val?.ok || !val?.b64) {
    throw new Error(`Failed to decode raster image: ${srcPath}`);
  }
  const pngBuf = Buffer.from(val.b64, "base64");
  fs.writeFileSync(outPngPath, pngBuf);
  return { ok: true, width: val.width, height: val.height, bytes: pngBuf.length, mode: "raster_canvas_png" };
}

async function main() {
  const models = JSON.parse(fs.readFileSync(SELECTED_PATH, "utf-8"));
  let prevManifest = {};
  if (fs.existsSync(MANIFEST_PATH)) {
    try {
      prevManifest = JSON.parse(fs.readFileSync(MANIFEST_PATH, "utf-8")).manifest || {};
    } catch {}
  }

  const manifest = {};
  const directPngCopies = [];
  const browserToRender = [];
  let reusedCount = 0;

  for (const m of models) {
    const outPngPath = path.join(BASE, m.png_path);
    const srcPath = m.has_svg && m.svg_path ? path.join(BASE, m.svg_path) : m.raster_source_cache;
    const srcHash = srcPath && fs.existsSync(srcPath) ? sha256File(srcPath) : "";
    const prev = prevManifest[m.model_id];

    if (!FORCE_RENDER && prev?.ok && prev.source_sha256 === srcHash && fs.existsSync(outPngPath)) {
      manifest[m.model_id] = prev;
      reusedCount++;
    } else if (!m.has_svg && srcPath && fs.existsSync(srcPath) && isPngFile(fs.readFileSync(srcPath))) {
      directPngCopies.push({ model: m, srcPath, srcHash, outPngPath });
    } else {
      browserToRender.push({ model: m, srcPath, srcHash, outPngPath });
    }
  }

  const totalToRender = directPngCopies.length + browserToRender.length;
  console.log(
    `PNG render plan: ${models.length} total | ${reusedCount} unchanged (cached) | ${totalToRender} to render` +
      (directPngCopies.length > 0 ? ` (${directPngCopies.length} direct PNG copy, ${browserToRender.length} via browser)` : "")
  );

  let okCount = reusedCount;
  let errCount = 0;
  const errors = [];

  for (const { model: m, srcPath, srcHash, outPngPath } of directPngCopies) {
    try {
      const info = await convertRasterToPng(null, srcPath, outPngPath);
      info.source_sha256 = srcHash;
      manifest[m.model_id] = info;
      okCount++;
    } catch (e) {
      errCount++;
      errors.push({ model_id: m.model_id, error: String(e) });
      manifest[m.model_id] = { ok: false, error: String(e) };
    }
  }

  if (browserToRender.length > 0) {
    const browserPath = findBrowserExecutable();
    console.log(`Using headless browser: ${browserPath}`);
    const { proc, wsUrl, userDataDir } = await launchBrowser(browserPath);
    const cdp = new CDPClient(wsUrl);

    try {
      await cdp.connect();
      await cdp.send("Page.enable");

      for (let i = 0; i < browserToRender.length; i++) {
        const { model: m, srcPath, srcHash, outPngPath } = browserToRender[i];
        try {
          let info;
          if (m.has_svg && m.svg_path) {
            info = await renderSvgToPng(cdp, srcPath, outPngPath);
          } else if (srcPath && fs.existsSync(srcPath)) {
            info = await convertRasterToPng(cdp, srcPath, outPngPath);
          } else {
            throw new Error("No svg_path or raster_source_cache");
          }
          info.source_sha256 = srcHash;
          manifest[m.model_id] = info;
          okCount++;
        } catch (e) {
          errCount++;
          errors.push({ model_id: m.model_id, error: String(e) });
          manifest[m.model_id] = { ok: false, error: String(e) };
        }
        if ((i + 1) % 50 === 0 || i + 1 === browserToRender.length) {
          console.log(`  Rendered ${i + 1}/${browserToRender.length} (ok=${okCount}, err=${errCount})`);
        }
      }
    } finally {
      await closeBrowser(proc, cdp, userDataDir);
    }
  }

  fs.writeFileSync(MANIFEST_PATH, JSON.stringify({ okCount, errCount, reusedCount, errors, manifest }, null, 2), "utf-8");
  console.log(`DONE rendering! ok=${okCount}, reused=${reusedCount}, err=${errCount}.`);
  if (errors.length) {
    console.log("Errors:", errors.slice(0, 10));
    process.exitCode = 1;
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
