const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');

const DEMO_DIR = __dirname;
const REPO_ROOT = path.resolve(DEMO_DIR, '..', '..', '..');
const PUBLIC_DIR = path.join(DEMO_DIR, 'public');
const OUTPUT_DIR = path.join(DEMO_DIR, 'output');
const URL_LIST_PATH = path.join(
  REPO_ROOT,
  'src',
  'agentic_rag',
  'ingestion',
  'url',
  'golden_data',
  'Link_data.txt',
);
const GOLDEN_PATH = path.join(
  REPO_ROOT,
  'src',
  'agentic_rag',
  'ingestion',
  'url',
  'golden_data',
  'vinfast_url_golden_samples.json',
);
const SMOKE_URL = 'https://vinfastauto.com/vn_vi/ve-chung-toi';
const PORT = Number(process.env.PORT || 8784);

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml; charset=utf-8',
};

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
    if (req.method === 'GET' && url.pathname === '/api/health') {
      return sendJson(res, 200, healthPayload());
    }
    if (req.method === 'GET' && url.pathname === '/api/golden') {
      return sendJson(res, 200, loadGoldenCatalog());
    }
    if (req.method === 'POST' && url.pathname === '/api/run') {
      const body = await readJsonBody(req);
      return runGoldenReview(body, res);
    }
    if (req.method === 'GET' || req.method === 'HEAD') {
      return serveStatic(req, res, url);
    }
    return sendJson(res, 405, { error: 'Method not allowed.' });
  } catch (error) {
    return sendJson(res, 500, { error: error.message });
  }
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`URL Golden Review React demo running at http://127.0.0.1:${PORT}`);
});

server.on('error', (error) => {
  if (error.code === 'EADDRINUSE') {
    console.error(`Port ${PORT} is already in use. Set PORT=8785 and try again.`);
    process.exit(1);
  }
  throw error;
});

function healthPayload() {
  const catalog = loadGoldenCatalog();
  return {
    ok: true,
    server: 'node',
    demo: 'url-golden-review-react',
    smoke_url: SMOKE_URL,
    url_count: catalog.url_count,
    golden_sample_count: catalog.golden_sample_count,
  };
}

function loadGoldenCatalog() {
  const urls = readUrlList(URL_LIST_PATH);
  const golden = JSON.parse(fs.readFileSync(GOLDEN_PATH, 'utf8'));
  const samples = Array.isArray(golden.samples) ? golden.samples : [];
  const samplesByUrl = new Map();
  for (const sample of samples) {
    const sourceUrl = sample.input?.source_url || sample.input?.source;
    if (sourceUrl) samplesByUrl.set(normalizeUrl(sourceUrl), sample);
  }
  const items = urls.map((url, index) => {
    const sample = samplesByUrl.get(normalizeUrl(url));
    const expectations = sample?.expectations || {};
    return {
      index: index + 1,
      url,
      has_golden_sample: Boolean(sample),
      sample_id: sample?.sample_id || null,
      description: sample?.description || null,
      min_chunk_count: expectations.min_chunk_count ?? null,
      max_chunk_count: expectations.max_chunk_count ?? null,
      required_text_snippets: expectations.required_text_snippets || [],
      forbidden_text_snippets: expectations.forbidden_text_snippets || [],
      product_spec_check_count: Array.isArray(expectations.product_spec_checks)
        ? expectations.product_spec_checks.length
        : 0,
    };
  });
  return {
    payload_schema_version: 1,
    golden_version: golden.version || null,
    description: golden.description || null,
    url_list_path: relativePath(URL_LIST_PATH),
    golden_path: relativePath(GOLDEN_PATH),
    smoke_url: SMOKE_URL,
    url_count: urls.length,
    golden_sample_count: samples.length,
    items,
  };
}

async function runGoldenReview(body, res) {
  const urls = selectedUrls(body);
  if (!urls.length) {
    return sendJson(res, 400, { error: 'Select or enter at least one URL.' });
  }
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const outputPath = path.join(OUTPUT_DIR, 'latest_payload.json');
  const uvCommand = process.env.UV || 'uv';
  const args = [
    'run',
    'python',
    path.join(DEMO_DIR, 'run_ingestion_review.py'),
    '--output',
    outputPath,
    '--output-dir',
    OUTPUT_DIR,
    '--golden',
    GOLDEN_PATH,
    '--url-list',
    URL_LIST_PATH,
  ];
  if (body && body.no_browser) {
    args.push('--no-browser');
  }
  for (const url of urls) {
    args.push('--url', url);
  }
  const result = await spawnPython(uvCommand, args);
  if (result.exitCode !== 0) {
    return sendJson(res, 500, {
      error: 'run_ingestion_review.py failed.',
      exit_code: result.exitCode,
      stdout: result.stdout.slice(-4000),
      stderr: result.stderr.slice(-4000),
    });
  }
  if (!fs.existsSync(outputPath)) {
    return sendJson(res, 500, {
      error: 'run_ingestion_review.py completed but did not write output JSON.',
      stdout: result.stdout.slice(-4000),
      stderr: result.stderr.slice(-4000),
    });
  }
  const payload = JSON.parse(fs.readFileSync(outputPath, 'utf8'));
  payload.server = 'node';
  payload.stdout = result.stdout.trim();
  return sendJson(res, 200, payload);
}

function selectedUrls(body) {
  const rawUrls = Array.isArray(body?.urls) ? body.urls : [];
  const urls = rawUrls.map((item) => String(item || '').trim()).filter(Boolean);
  const unique = [];
  const seen = new Set();
  for (const url of urls) {
    if (seen.has(url)) continue;
    seen.add(url);
    unique.push(url);
  }
  return unique.slice(0, 25);
}

function serveStatic(req, res, url) {
  const requestedPath = url.pathname === '/' ? '/index.html' : url.pathname;
  const filePath = path.resolve(PUBLIC_DIR, `.${decodeURIComponent(requestedPath)}`);
  if (!filePath.startsWith(PUBLIC_DIR + path.sep)) {
    return sendText(res, 403, 'Forbidden');
  }
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    return sendText(res, 404, 'File not found');
  }
  const ext = path.extname(filePath).toLowerCase();
  res.writeHead(200, {
    'Content-Type': MIME_TYPES[ext] || 'application/octet-stream',
    'Cache-Control': 'no-store, max-age=0',
  });
  if (req.method === 'HEAD') return res.end();
  return fs.createReadStream(filePath).pipe(res);
}

function spawnPython(command, args) {
  return new Promise((resolve) => {
    const child = spawn(command, args, {
      cwd: REPO_ROOT,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
      windowsHide: true,
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });
    child.on('error', (error) => {
      resolve({ exitCode: 1, stdout, stderr: `${stderr}\n${error.message}`.trim() });
    });
    child.on('close', (exitCode) => {
      resolve({ exitCode, stdout, stderr });
    });
  });
}

function readUrlList(filePath) {
  return fs
    .readFileSync(filePath, 'utf8')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith('#'));
}

function normalizeUrl(value) {
  try {
    const url = new URL(value);
    url.hash = '';
    url.pathname = url.pathname.replace(/\/$/, '');
    return url.toString();
  } catch {
    return String(value || '').trim().replace(/\/$/, '');
  }
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let raw = '';
    req.on('data', (chunk) => {
      raw += chunk;
      if (raw.length > 1024 * 1024) {
        reject(new Error('Request body too large.'));
        req.destroy();
      }
    });
    req.on('end', () => {
      if (!raw.trim()) return resolve({});
      try {
        resolve(JSON.parse(raw));
      } catch (error) {
        reject(new Error(`Invalid JSON: ${error.message}`));
      }
    });
    req.on('error', reject);
  });
}

function relativePath(filePath) {
  return path.relative(REPO_ROOT, filePath).replace(/\\/g, '/');
}

function sendJson(res, status, payload) {
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store, max-age=0',
  });
  res.end(JSON.stringify(payload));
}

function sendText(res, status, text) {
  res.writeHead(status, {
    'Content-Type': 'text/plain; charset=utf-8',
    'Cache-Control': 'no-store, max-age=0',
  });
  res.end(text);
}
