const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');

const DEMO_DIR = __dirname;
const REPO_ROOT = path.resolve(DEMO_DIR, '..', '..', '..');
const PUBLIC_DIR = path.join(DEMO_DIR, 'public');
const OUTPUT_DIR = path.join(DEMO_DIR, 'output');
const DEFAULT_URL = 'https://vinfastauto.com/vn_vi/ve-chung-toi';
const PORT = Number(process.env.PORT || 8782);

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml; charset=utf-8',
};

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === 'GET' && req.url === '/api/health') {
      return sendJson(res, 200, {
        ok: true,
        server: 'node',
        mode: 'single_url_artifact_review',
        default_url: DEFAULT_URL,
      });
    }

    if (req.method === 'POST' && req.url === '/api/review') {
      const body = await readJsonBody(req);
      return runReview(body, res);
    }

    if (req.method === 'POST' && req.url === '/api/discover') {
      return sendJson(res, 410, {
        error: 'Discovery was removed. This demo reviews exactly one URL per run.',
      });
    }

    if (req.method === 'GET' || req.method === 'HEAD') {
      return serveStatic(req, res);
    }

    sendJson(res, 405, { error: 'Method not allowed' });
  } catch (error) {
    sendJson(res, 500, { error: error.message });
  }
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`URL artifact review demo running at http://127.0.0.1:${PORT}`);
});

server.on('error', (error) => {
  if (error.code === 'EADDRINUSE') {
    console.error(`Port ${PORT} is already in use. Stop the old server or set PORT=8783.`);
    process.exit(1);
  }
  throw error;
});

function serveStatic(req, res) {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
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
  if (req.method === 'HEAD') {
    return res.end();
  }
  fs.createReadStream(filePath).pipe(res);
}

async function runReview(body, res) {
  const url = String(body.url || '').trim();
  if (!url) {
    return sendJson(res, 400, { error: 'Missing URL.' });
  }
  if (!isHttpUrl(url)) {
    return sendJson(res, 400, { error: 'URL must be an absolute http or https URL.' });
  }

  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const jsonOutputPath = path.join(OUTPUT_DIR, 'artifact_review_payload.json');
  const uvCommand = process.env.UV || 'uv';
  const args = [
    'run',
    'python',
    path.join(DEMO_DIR, 'run_review.py'),
    url,
    '--output-dir',
    OUTPUT_DIR,
    '--json-output',
    jsonOutputPath,
  ];
  if (Boolean(body.no_browser)) {
    args.push('--no-browser');
  }
  if (Boolean(body.include_interactions)) {
    args.push('--include-interactions');
  }

  const result = await spawnReview(uvCommand, args);
  if (fs.existsSync(jsonOutputPath)) {
    const payload = JSON.parse(fs.readFileSync(jsonOutputPath, 'utf8'));
    payload.server = 'node';
    payload.stdout = result.stdout.trim();
    if (result.exitCode !== 0) {
      payload.process_warning = {
        exit_code: result.exitCode,
        stdout: result.stdout.slice(-4000),
        stderr: result.stderr.slice(-4000),
      };
    }
    return sendJson(res, 200, payload);
  }

  if (result.exitCode !== 0) {
    return sendJson(res, 500, {
      error: 'run_review.py failed.',
      exit_code: result.exitCode,
      stdout: result.stdout.slice(-4000),
      stderr: result.stderr.slice(-4000),
    });
  }

  return sendJson(res, 500, {
    error: 'run_review.py completed but did not write JSON output.',
    stdout: result.stdout.slice(-4000),
    stderr: result.stderr.slice(-4000),
  });
}

function spawnReview(command, args) {
  return new Promise((resolve) => {
    const child = spawn(command, args, {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        PYTHONIOENCODING: 'utf-8',
        UV_CACHE_DIR: process.env.UV_CACHE_DIR || path.join(REPO_ROOT, '.uv-cache'),
      },
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

function isHttpUrl(value) {
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
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
