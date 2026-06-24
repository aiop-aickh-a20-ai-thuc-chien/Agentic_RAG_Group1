const { useEffect, useMemo, useState } = React;
const h = React.createElement;

function App() {
  const [health, setHealth] = useState(null);
  const [catalog, setCatalog] = useState(null);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(new Set());
  const [customUrls, setCustomUrls] = useState('');
  const [noBrowser, setNoBrowser] = useState(true);
  const [running, setRunning] = useState(false);
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    loadInitialData();
  }, []);

  async function loadInitialData() {
    try {
      const [healthData, catalogData] = await Promise.all([
        fetchJson('/api/health'),
        fetchJson('/api/golden'),
      ]);
      setHealth(healthData);
      setCatalog(catalogData);
      setCustomUrls(healthData.smoke_url || catalogData.smoke_url || '');
    } catch (loadError) {
      setError(loadError.message);
    }
  }

  const filteredItems = useMemo(() => {
    if (!catalog) return [];
    const needle = query.trim().toLowerCase();
    const items = catalog.items || [];
    if (!needle) return items.slice(0, 80);
    return items
      .filter((item) => {
        return [item.url, item.sample_id, item.description]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(needle));
      })
      .slice(0, 120);
  }, [catalog, query]);

  const selectedUrls = [...selected];
  const smokeUrl = health?.smoke_url || catalog?.smoke_url;

  async function runUrls(urls) {
    const normalizedUrls = uniqueUrls(urls);
    if (!normalizedUrls.length) {
      setError('Select or enter at least one URL.');
      return;
    }
    setRunning(true);
    setError('');
    setPayload(null);
    try {
      const data = await fetchJson('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls: normalizedUrls, no_browser: noBrowser }),
      });
      setPayload(data);
    } catch (runError) {
      setError(runError.message);
    } finally {
      setRunning(false);
    }
  }

  function runCustom() {
    runUrls(customUrls.split(/\r?\n/).map((url) => url.trim()));
  }

  function runSelected() {
    runUrls(selectedUrls);
  }

  function toggleSelected(url) {
    const next = new Set(selected);
    if (next.has(url)) {
      next.delete(url);
    } else {
      next.add(url);
    }
    setSelected(next);
  }

  function selectVisible(limit) {
    setSelected(new Set(filteredItems.slice(0, limit).map((item) => item.url)));
  }

  return h(
    'div',
    { className: 'app-shell' },
    h(
      'header',
      { className: 'topbar' },
      h('div', null, h('h1', null, 'URL Golden Review'), h('p', null, 'Current URL ingestion + golden-data scorer')),
      h('div', { className: 'health' }, renderHealth(health, catalog)),
    ),
    error ? h('pre', { className: 'error-box' }, error) : null,
    h(
      'section',
      { className: 'control-band' },
      h(
        'div',
        { className: 'control-panel' },
        h('label', null, 'Custom URLs'),
        h('textarea', {
          value: customUrls,
          onChange: (event) => setCustomUrls(event.target.value),
          rows: 4,
        }),
        h(
          'div',
          { className: 'button-row' },
          h('button', { onClick: runCustom, disabled: running }, running ? 'Running...' : 'Run custom'),
          h('button', { onClick: () => runUrls([smokeUrl]), disabled: running || !smokeUrl }, 'Run ve-chung-toi'),
        ),
        h(
          'label',
          { className: 'check-row' },
          h('input', {
            type: 'checkbox',
            checked: noBrowser,
            onChange: (event) => setNoBrowser(event.target.checked),
          }),
          h('span', null, 'Static/no-browser mode for faster smoke checks'),
        ),
      ),
      h(
        'div',
        { className: 'control-panel' },
        h('label', null, 'Golden URL search'),
        h('input', {
          type: 'search',
          value: query,
          onChange: (event) => setQuery(event.target.value),
          placeholder: 'Search URL, sample id, description',
        }),
        h(
          'div',
          { className: 'button-row' },
          h('button', { onClick: () => selectVisible(10), disabled: !filteredItems.length }, 'Select first 10'),
          h('button', { onClick: () => setSelected(new Set()), disabled: !selected.size }, 'Clear'),
          h('button', { onClick: runSelected, disabled: running || !selected.size }, `Run selected (${selected.size})`),
        ),
      ),
    ),
    h(CatalogTable, {
      items: filteredItems,
      selected,
      toggleSelected,
      totalCount: catalog?.url_count || 0,
    }),
    payload ? h(ReviewResults, { payload }) : h('section', { className: 'empty-state' }, 'Run a URL to inspect chunks, checks, and current metadata.'),
  );
}

function CatalogTable({ items, selected, toggleSelected, totalCount }) {
  return h(
    'section',
    { className: 'table-section' },
    h('div', { className: 'section-title' }, h('h2', null, 'Golden URLs'), h('span', null, `${items.length} shown / ${totalCount} total`)),
    h(
      'div',
      { className: 'table-wrap' },
      h(
        'table',
        null,
        h(
          'thead',
          null,
          h('tr', null, h('th', null, ''), h('th', null, '#'), h('th', null, 'URL'), h('th', null, 'Sample'), h('th', null, 'Contract')),
        ),
        h(
          'tbody',
          null,
          items.map((item) =>
            h(
              'tr',
              { key: item.url },
              h('td', null, h('input', { type: 'checkbox', checked: selected.has(item.url), onChange: () => toggleSelected(item.url) })),
              h('td', null, item.index),
              h('td', { className: 'url-cell' }, item.url),
              h('td', null, item.sample_id || h('span', { className: 'muted' }, 'missing')),
              h('td', null, contractSummary(item)),
            ),
          ),
        ),
      ),
    ),
  );
}

function ReviewResults({ payload }) {
  const summary = payload.summary || {};
  return h(
    'section',
    { className: 'results' },
    h(
      'div',
      { className: 'section-title' },
      h('h2', null, 'Run Results'),
      h('span', null, `Browser extractor: ${payload.use_browser_extractor ? 'on' : 'off'}`),
    ),
    h(
      'div',
      { className: 'summary-grid' },
      metric('Requested', summary.requested),
      metric('Passed', summary.passed, 'good'),
      metric('Failed', summary.failed, 'bad'),
      metric('Errors', summary.errors, 'bad'),
      metric('Unscored', summary.unscored),
    ),
    ...(payload.results || []).map((result) => h(ResultCard, { key: result.url, result })),
  );
}

function ResultCard({ result }) {
  const document = result.document || {};
  const evaluation = result.evaluation || {};
  const errorChecks = evaluation.error_checks || [];
  const recovery = document.ve_chung_toi_recovery;
  return h(
    'article',
    { className: `result-card ${statusClass(result.status)}` },
    h(
      'header',
      null,
      h('div', null, h('h3', null, result.url), h('p', null, result.sample?.sample_id || result.error || 'No golden sample')),
      h('span', { className: `status-pill ${statusClass(result.status)}` }, result.status),
    ),
    h(
      'div',
      { className: 'summary-grid compact' },
      metric('Score', evaluation.score ?? 'n/a', statusClass(result.status)),
      metric('Chunks', document.chunk_count ?? 0),
      metric('Usable', document.usable_chunk_count ?? 0),
      metric('Markdown chars', document.markdown_length ?? 0),
      metric('Seconds', result.elapsed_seconds),
    ),
    recovery ? h('div', { className: `callout ${recovery.passed ? 'good' : 'bad'}` }, `${recovery.current_check}. Sections: ${recovery.recovery_sections.join(', ') || 'none'}`) : null,
    errorChecks.length
      ? h(CheckList, { checks: errorChecks })
      : evaluation.checks
        ? h('div', { className: 'callout good' }, 'No hard golden-check failures.')
        : h('div', { className: 'callout neutral' }, 'No golden sample matched this URL, so this run is diagnostics-only.'),
    h(DetailsBlock, { title: 'Quality Gate', value: document.quality_gate }),
    h(DetailsBlock, { title: 'URL Quality', value: document.url_quality }),
    h(DetailsBlock, { title: 'Metadata Summary', value: document.metadata_summary }),
    h(ProductSpecs, { specs: document.product_specs || [] }),
    h(ChunkList, { chunks: document.chunks || [] }),
    h(PreviewBlock, { title: 'Markdown Preview', text: document.markdown_preview || '' }),
    h(DetailsBlock, { title: 'Manifest', value: document.manifest }),
  );
}

function CheckList({ checks }) {
  return h(
    'div',
    { className: 'checks' },
    h('h4', null, 'Failing Checks'),
    checks.map((check, index) =>
      h(
        'div',
        { className: 'check-row-card', key: `${check.name}-${index}` },
        h('strong', null, check.name),
        h('span', null, check.message),
        check.details?.snippet ? h('code', null, check.details.snippet) : null,
      ),
    ),
  );
}

function ProductSpecs({ specs }) {
  if (!specs.length) return h('div', { className: 'muted block-gap' }, 'No product specs detected.');
  return h(
    'details',
    { className: 'details-block', open: true },
    h('summary', null, 'Product Specs'),
    h('pre', null, JSON.stringify(specs, null, 2)),
  );
}

function ChunkList({ chunks }) {
  if (!chunks.length) return h('div', { className: 'muted block-gap' }, 'No chunks returned.');
  return h(
    'div',
    { className: 'chunk-list' },
    chunks.map((chunk) =>
      h(
        'article',
        { className: `chunk-card ${chunk.is_usable ? 'good' : 'bad'}`, key: chunk.chunk_id },
        h(
          'header',
          null,
          h('strong', null, chunk.section || 'main'),
          h('code', null, chunk.chunk_id),
          h('span', null, chunk.is_usable ? 'usable' : 'low signal'),
        ),
        h(ChunkImages, { chunk }),
        h('p', null, chunk.text),
        h('small', null, `weight=${chunk.retrieval_weight ?? 'n/a'} noise=${chunk.is_noise}`),
      ),
    ),
  );
}

function ChunkImages({ chunk }) {
  const images = chunkImages(chunk);
  if (!images.length) return null;
  return h(
    'div',
    { className: 'chunk-images' },
    images.map((image) =>
      h(
        'figure',
        { className: 'chunk-image-card', key: image.url },
        h('img', {
          src: image.url,
          alt: image.label,
          loading: 'lazy',
          onError: (event) => event.currentTarget.closest('figure').classList.add('image-error'),
        }),
        h(
          'figcaption',
          null,
          h('strong', null, image.label),
          h('code', null, image.url),
        ),
      ),
    ),
  );
}

function chunkImages(chunk) {
  const candidates = [];
  for (const url of Array.isArray(chunk.image_urls) ? chunk.image_urls : []) {
    addImageCandidate(candidates, url, chunk.image_snapshot_ref || 'chunk image');
  }
  addImageCandidate(candidates, chunk.image_url, chunk.image_snapshot_ref || 'chunk image');
  addImageCandidate(
    candidates,
    chunk.interaction_state?.image_url,
    chunk.interaction_state?.option_label || chunk.image_snapshot_ref || 'interaction state',
  );
  const interactionStates = Array.isArray(chunk.interaction_states)
    ? chunk.interaction_states
    : [];
  for (const state of interactionStates) {
    addImageCandidate(
      candidates,
      state?.image_url,
      state?.option_label || state?.state_id || 'interaction state',
    );
  }
  for (const image of markdownImageUrls(chunk.text || '')) {
    addImageCandidate(candidates, image.url, image.alt || 'markdown image');
  }
  const seen = new Set();
  return candidates.filter((candidate) => {
    if (!candidate.url || seen.has(candidate.url)) return false;
    seen.add(candidate.url);
    return true;
  }).slice(0, 4);
}

function addImageCandidate(candidates, rawUrl, rawLabel) {
  const url = safeImageUrl(rawUrl);
  if (!url) return;
  candidates.push({
    url,
    label: String(rawLabel || 'chunk image'),
  });
}

function markdownImageUrls(text) {
  const images = [];
  const imagePattern = /!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;
  let match = imagePattern.exec(text);
  while (match) {
    images.push({ alt: match[1], url: match[2] });
    match = imagePattern.exec(text);
  }
  return images;
}

function safeImageUrl(value) {
  const url = String(value || '').trim();
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  if (url.startsWith('/')) return url;
  return '';
}

function DetailsBlock({ title, value }) {
  if (!value || !Object.keys(value).length) return null;
  return h('details', { className: 'details-block' }, h('summary', null, title), h('pre', null, JSON.stringify(value, null, 2)));
}

function PreviewBlock({ title, text }) {
  if (!text) return null;
  return h('details', { className: 'details-block' }, h('summary', null, title), h('pre', null, text));
}

function metric(label, value, tone = '') {
  return h('div', { className: `metric ${tone}` }, h('span', null, label), h('strong', null, value ?? 0));
}

function renderHealth(health, catalog) {
  if (!health || !catalog) return 'Loading...';
  return `${health.server} OK | ${catalog.url_count} URLs | ${catalog.golden_sample_count} samples`;
}

function contractSummary(item) {
  if (!item.has_golden_sample) return h('span', { className: 'badge bad' }, 'missing golden');
  return h(
    'span',
    { className: 'badge' },
    `chunks ${item.min_chunk_count ?? '?'}-${item.max_chunk_count ?? '*'} | required ${item.required_text_snippets.length}`,
  );
}

function statusClass(status) {
  if (status === 'passed' || status === 'good') return 'good';
  if (status === 'failed' || status === 'error' || status === 'bad') return 'bad';
  return 'neutral';
}

function uniqueUrls(urls) {
  return [...new Set(urls.map((url) => String(url || '').trim()).filter(Boolean))];
}

async function fetchJson(url, options) {
  const response = await fetch(url, { cache: 'no-store', ...(options || {}) });
  const data = await response.json();
  if (!response.ok || data.error) {
    throw new Error(formatApiError(data, response.statusText));
  }
  return data;
}

function formatApiError(data, fallback) {
  const parts = [data.error || fallback];
  if (data.exit_code !== undefined) parts.push(`exit code: ${data.exit_code}`);
  if (data.stderr) parts.push(`stderr:\n${data.stderr}`);
  if (data.stdout) parts.push(`stdout:\n${data.stdout}`);
  return parts.filter(Boolean).join('\n\n');
}

ReactDOM.createRoot(document.getElementById('root')).render(h(App));
