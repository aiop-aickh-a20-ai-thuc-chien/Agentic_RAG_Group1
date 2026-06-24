const runBtn = document.getElementById('run-btn');
const urlInput = document.getElementById('url-input');
const noBrowser = document.getElementById('no-browser');
const includeInteractions = document.getElementById('include-interactions');
const statusBox = document.getElementById('status');
const reportLink = document.getElementById('report-link');
const summaryStatus = document.getElementById('summary-status');
const summaryGrid = document.getElementById('summary-grid');
const artifactCount = document.getElementById('artifact-count');
const artifactGrid = document.getElementById('artifact-grid');
const qualityStatus = document.getElementById('quality-status');
const qualityJson = document.getElementById('quality-json');
const manifestStatus = document.getElementById('manifest-status');
const manifestJson = document.getElementById('manifest-json');
const dedupStatus = document.getElementById('dedup-status');
const dedupSummaryGrid = document.getElementById('dedup-summary-grid');
const dedupList = document.getElementById('dedup-list');
const chunkCount = document.getElementById('chunk-count');
const chunkGrid = document.getElementById('chunk-grid');
const interactionStatus = document.getElementById('interaction-status');
const interactionSummaryGrid = document.getElementById('interaction-summary-grid');
const interactionArtifactGrid = document.getElementById('interaction-artifact-grid');
const interactionLeftPanel = document.getElementById('interaction-left-panel');
const interactionCenterPanel = document.getElementById('interaction-center-panel');
const interactionRightPanel = document.getElementById('interaction-right-panel');
const interactionDiffGrid = document.getElementById('interaction-diff-grid');
const interactionPromotedChunkGrid = document.getElementById('interaction-promoted-chunk-grid');
const interactionChunkGrid = document.getElementById('interaction-chunk-grid');
const artifactTemplate = document.getElementById('artifact-template');

runBtn.addEventListener('click', runReview);
checkHealth();

async function checkHealth() {
  try {
    const response = await fetch('/api/health', { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || response.statusText);
    if (data.default_url && !urlInput.value.trim()) {
      urlInput.value = data.default_url;
    }
    setStatus(`Ready. ${data.server || 'server'} OK. Mode: ${data.mode || 'single URL'}.`, false);
  } catch (error) {
    setStatus(`Server health check failed: ${error.message}`, true);
  }
}

async function runReview() {
  const url = urlInput.value.trim();
  if (!url) {
    setStatus('Enter one URL first.', true);
    return;
  }

  setRunning(true);
  setStatus('Running URL ingestion and collecting artifacts. Dynamic pages can take a while.', false);
  clearResults();

  try {
    const response = await fetch('/api/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url,
        no_browser: noBrowser.checked,
        include_interactions: includeInteractions.checked,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(formatApiError(data, response.statusText));
    renderPayload(data);
    const reviewError = data.error ? ` Ingestion note: ${data.error}` : '';
    setStatus(
      `Review complete for one URL. ${data.summary?.artifact_count || 0} artifacts found.${reviewError}`,
      Boolean(data.error),
    );
  } catch (error) {
    setStatus(`Error: ${error.message}`, true);
  } finally {
    setRunning(false);
  }
}

function renderPayload(data) {
  const summary = data.summary || {};
  summaryStatus.textContent = summary.status || data.status || 'unknown';
  summaryStatus.className = `status-pill ${statusClass(summary.status || data.status)}`;
  summaryGrid.innerHTML = [
    metric('Chunks', summary.chunk_count ?? 0),
    metric('Usable', summary.usable_chunk_count ?? 0),
    metric('Valuable', summary.valuable_chunk_count ?? 0),
    metric('Product Facts', summary.product_fact_chunk_count ?? 0),
    metric('Entities', summary.entity_chunk_count ?? 0),
    metric('Noise', summary.noise_chunk_count ?? 0),
    metric('Duplicates', summary.dedup_duplicate_candidate_count ?? 0),
    metric('Exact Dup', summary.dedup_exact_match_count ?? 0),
    metric('SimHash Dup', summary.dedup_simhash_match_count ?? 0),
    metric('Markdown', summary.markdown_length ?? 0),
    metric('Parser', summary.parser || '(none)'),
    metric('Source HTML', summary.source_html_stage || '(none)'),
    metric('Page Type', summary.page_type || '(unknown)'),
    metric('Gate', summary.quality_status || '(none)'),
    metric('Verdict', summary.quality_verdict || '(none)'),
    metric('Render Required', summary.render_required ?? '(unknown)'),
    metric('Elapsed', `${data.elapsed_seconds ?? 0}s`),
  ].join('');

  reportLink.textContent = data.report_path ? `Report: ${data.report_path}` : '';
  renderArtifacts(data.artifacts || []);
  renderJsonPanel(qualityJson, qualityStatus, data.quality || {});
  renderJsonPanel(manifestJson, manifestStatus, data.manifest || {});
  renderDedup(data.deduplication || {});
  renderChunks(data.chunks || []);
  renderInteraction(data.interaction || {});
}

function renderDedup(dedup) {
  const summary = dedup.summary || {};
  const duplicateChunks = Array.isArray(dedup.duplicate_chunks) ? dedup.duplicate_chunks : [];
  dedupStatus.textContent = duplicateChunks.length
    ? `${duplicateChunks.length} candidates`
    : 'no candidates';
  dedupStatus.className = `status-pill ${duplicateChunks.length ? 'partial' : 'success'}`;
  dedupSummaryGrid.innerHTML = [
    metric('Documents', summary.document_count ?? 0),
    metric('Exact Matches', summary.exact_match_count ?? 0),
    metric('SimHash Matches', summary.simhash_match_count ?? 0),
    metric('Embedding Matches', summary.embedding_match_count ?? 0),
    metric('Candidates', summary.duplicate_candidate_count ?? 0),
    metric('Layers', Array.isArray(summary.layers_enabled) ? summary.layers_enabled.join(', ') : ''),
  ].join('');

  dedupList.innerHTML = duplicateChunks.length
    ? duplicateChunks.slice(0, 12).map((item) => {
      const metadata = item.deduplication || {};
      return `
        <article class="dedup-card">
          <header>
            <strong>${escapeHtml(item.chunk_id || '')}</strong>
            <span>${escapeHtml(metadata.primary_layer || '')}</span>
          </header>
          <div class="chunk-meta">
            <span>canonical: ${escapeHtml(metadata.canonical_chunk_id || '')}</span>
            <span>matches: ${escapeHtml(metadata.match_count ?? '')}</span>
            <span>layers: ${escapeHtml((metadata.detected_layers || []).join(', '))}</span>
          </div>
          <pre>${escapeHtml(item.text_preview || '')}</pre>
        </article>
      `;
    }).join('')
    : '<div class="empty-state">No exact or SimHash duplicate candidates in this run.</div>';
}

function renderArtifacts(artifacts) {
  const existingCount = artifacts.filter((item) => item.exists).length;
  artifactCount.textContent = `${existingCount}/${artifacts.length} files`;
  artifactGrid.innerHTML = '';
  for (const artifact of artifacts) {
    const node = artifactTemplate.content.cloneNode(true);
    node.querySelector('.artifact-label').textContent = artifact.label || artifact.key;
    node.querySelector('.artifact-description').textContent = artifact.description || '';
    const status = node.querySelector('.artifact-status');
    status.textContent = artifact.exists ? 'found' : 'missing';
    status.className = `artifact-status ${artifact.exists ? 'success' : 'bad'}`;
    node.querySelector('.artifact-meta').innerHTML = `
      <code>${escapeHtml(artifact.path || '')}</code>
      <span>${formatBytes(artifact.size_bytes || 0)}</span>
      <span>${Number(artifact.line_count || 0)} lines</span>
      ${artifact.truncated ? '<span>preview truncated</span>' : ''}
    `;
    node.querySelector('.artifact-preview').textContent =
      artifact.preview || '(artifact was not written for this run)';
    artifactGrid.appendChild(node);
  }
}

function renderJsonPanel(element, statusElement, value) {
  const keys = value && typeof value === 'object' ? Object.keys(value) : [];
  statusElement.textContent = keys.length ? `${keys.length} keys` : 'empty';
  element.textContent = JSON.stringify(value || {}, null, 2);
}

function renderChunks(chunks) {
  chunkCount.textContent = `${chunks.length} chunks`;
  if (!chunks.length) {
    chunkGrid.innerHTML = '<div class="empty-state">No chunks were generated.</div>';
    return;
  }
  chunkGrid.innerHTML = chunkCards(chunks);
}

function renderInteraction(interaction) {
  const enabled = Boolean(interaction.enabled);
  const attempted = Boolean(interaction.attempted);
  const error = interaction.error || '';
  const skipped = interaction.skipped_reason || '';
  const chunks = Array.isArray(interaction.chunks) ? interaction.chunks : [];
  const debugChunks = Array.isArray(interaction.debug_chunks) ? interaction.debug_chunks : [];
  const promotedChunks = Array.isArray(interaction.promoted_chunks) ? interaction.promoted_chunks : [];
  const panelSnapshots = Array.isArray(interaction.panel_snapshots) ? interaction.panel_snapshots : [];
  const panelDiffs = Array.isArray(interaction.panel_diffs) ? interaction.panel_diffs : [];
  const controls = Array.isArray(interaction.controls) ? interaction.controls : [];
  const artifacts = Array.isArray(interaction.artifacts) ? interaction.artifacts : [];

  interactionStatus.textContent = error
    ? 'error'
    : attempted
      ? `${promotedChunks.length} promoted / ${debugChunks.length || chunks.length} debug`
      : skipped || (enabled ? 'not attempted' : 'disabled');
  interactionStatus.className = `status-pill ${error ? 'bad' : attempted ? 'partial' : 'bad'}`;
  interactionSummaryGrid.innerHTML = [
    metric('Enabled', enabled),
    metric('Attempted', attempted),
    metric('Required', interaction.profile?.interaction_required ?? false),
    metric('States', interaction.state_count ?? 0),
    metric('Controls', interaction.control_count ?? 0),
    metric('Skipped Controls', interaction.skipped_control_count ?? 0),
    metric('Panel Snapshots', interaction.panel_snapshot_count ?? panelSnapshots.length),
    metric('Panel Diffs', interaction.panel_diff_count ?? panelDiffs.length),
    metric('Debug Chunks', interaction.debug_chunk_count ?? debugChunks.length),
    metric('Promoted Chunks', interaction.promoted_chunk_count ?? promotedChunks.length),
    metric('Chunks Total', interaction.chunk_count ?? chunks.length),
    metric('Skipped Reason', skipped || '(none)'),
    metric('Error', error || '(none)'),
  ].join('');

  renderPanelSnapshots(panelSnapshots, controls);
  renderPanelDiffs(panelDiffs);

  interactionArtifactGrid.innerHTML = artifacts.length
    ? artifacts.map((artifact) => `
      <article class="artifact-card">
        <header>
          <div>
            <h3 class="artifact-label">${escapeHtml(artifact.label || artifact.key || '')}</h3>
            <p class="artifact-description">${escapeHtml(artifact.description || '')}</p>
          </div>
          <span class="artifact-status ${artifact.exists ? 'success' : 'bad'}">
            ${artifact.exists ? 'found' : 'missing'}
          </span>
        </header>
        <div class="artifact-meta">
          <code>${escapeHtml(artifact.path || '')}</code>
          <span>${formatBytes(artifact.size_bytes || 0)}</span>
          <span>${Number(artifact.line_count || 0)} lines</span>
        </div>
        <details>
          <summary>Preview</summary>
          <pre class="artifact-preview">${escapeHtml(artifact.preview || '(artifact was not written for this run)')}</pre>
        </details>
      </article>
    `).join('')
    : '<div class="empty-state">No interaction artifacts for this run.</div>';

  interactionPromotedChunkGrid.innerHTML = promotedChunks.length
    ? chunkCards(promotedChunks)
    : '<div class="empty-state">No promoted semantic chunks. Dynamic evidence stayed debug-only for this run.</div>';

  const visibleDebugChunks = debugChunks.length ? debugChunks : chunks.filter((chunk) => {
    const metadata = chunk.metadata || {};
    return metadata.chunk_type !== 'dynamic_state';
  });
  interactionChunkGrid.innerHTML = visibleDebugChunks.length
    ? chunkCards(visibleDebugChunks)
    : '<div class="empty-state">No interaction debug chunks. Try a booking/configurator URL with dynamic interaction capture enabled.</div>';
}

function renderPanelSnapshots(snapshots, controls) {
  const roles = {
    left_panel: interactionLeftPanel,
    center_visual: interactionCenterPanel,
    right_panel: interactionRightPanel,
  };
  for (const [role, element] of Object.entries(roles)) {
    const roleSnapshots = snapshots.filter((snapshot) => snapshot.panel_role === role).slice(-4);
    const roleControls = controls.filter((control) => control.panel_role === role).slice(0, 12);
    element.innerHTML = panelSnapshotCards(roleSnapshots, roleControls, role);
  }
}

function panelSnapshotCards(snapshots, controls, role) {
  const controlList = controls.length
    ? `<ul class="control-list">${controls.map((control) => `
      <li>
        <strong>${escapeHtml(control.label || '')}</strong>
        <span>${escapeHtml(control.group || 'option')}</span>
      </li>
    `).join('')}</ul>`
    : '<p class="muted-small">No safe controls mapped to this panel.</p>';
  const snapshotList = snapshots.length
    ? snapshots.map((snapshot) => panelSnapshotCard(snapshot)).join('')
    : '<p class="muted-small">No panel snapshot captured.</p>';
  return `
    <div class="panel-subhead">Safe controls</div>
    ${controlList}
    <div class="panel-subhead">Recent snapshots</div>
    ${snapshotList}
  `;
}

function panelSnapshotCard(snapshot) {
  const images = Array.isArray(snapshot.image_urls) ? snapshot.image_urls.slice(0, 3) : [];
  const prices = Array.isArray(snapshot.price_values) ? snapshot.price_values.slice(0, 6) : [];
  return `
    <article class="panel-snapshot-card">
      <header>
        <strong>${escapeHtml(snapshot.interaction_step || '')}</strong>
        <code>${escapeHtml(snapshot.snapshot_id || '')}</code>
      </header>
      <div class="chunk-meta">
        <span>prices: ${escapeHtml(prices.join(', ') || '(none)')}</span>
        <span>images: ${images.length}</span>
      </div>
      ${images.length ? `
        <div class="mini-images">
          ${images.map((url) => `<img src="${escapeHtml(url)}" alt="panel image" loading="lazy">`).join('')}
        </div>
      ` : ''}
      <pre>${escapeHtml((snapshot.text || '').slice(0, 700))}</pre>
    </article>
  `;
}

function renderPanelDiffs(diffs) {
  if (!diffs.length) {
    interactionDiffGrid.innerHTML = '<div class="empty-state">No changed panel diffs captured yet.</div>';
    return;
  }
  interactionDiffGrid.innerHTML = diffs.slice(0, 12).map((diff) => `
    <article class="diff-card">
      <header>
        <strong>${escapeHtml(diff.control_label || '')}</strong>
        <span>${escapeHtml(diff.control_group || 'option')}</span>
      </header>
      <div class="chunk-meta">
        <span>changed panels: ${escapeHtml((diff.changed_panels || []).join(', ') || '(none)')}</span>
        <span>changed fields: ${escapeHtml((diff.changed_fields || []).join(', ') || '(none)')}</span>
      </div>
      <details>
        <summary>Diff JSON</summary>
        <pre>${escapeHtml(JSON.stringify(diff, null, 2))}</pre>
      </details>
    </article>
  `).join('');
}

function chunkCards(chunks) {
  return chunks.map((chunk, index) => {
    const metadata = chunk.metadata || {};
    const debugOnly = metadata.retrieval_visibility === 'debug_only'
      || metadata.metadata_prefilter_exclude === true
      || metadata.trusted_for_retrieval === false;
    const dedup = chunk.deduplication || metadata.deduplication || null;
    const duplicateCandidate = dedup && dedup.status === 'duplicate_candidate';
    return `
    <article class="chunk-card ${debugOnly ? 'debug-only' : ''} ${duplicateCandidate ? 'duplicate-candidate' : ''}">
      <header>
        <div>
          <strong>Chunk ${index + 1}</strong>
          <code>${escapeHtml(chunk.chunk_id || '')}</code>
        </div>
        <span class="chunk-usable ${chunk.is_usable_for_retrieval ? 'success' : 'bad'}">
          ${chunk.is_usable_for_retrieval ? 'usable' : 'low signal'}
        </span>
      </header>
      <div class="chunk-meta">
        <span>Section: ${escapeHtml(chunk.section || 'main')}</span>
        <span>Type: ${escapeHtml(chunk.chunk_type || metadata.chunk_type || '')}</span>
        <span>Visibility: ${escapeHtml(chunk.retrieval_visibility || metadata.retrieval_visibility || 'normal')}</span>
        <span>Pre-filtered: ${escapeHtml(chunk.metadata_prefilter_exclude ?? metadata.metadata_prefilter_exclude ?? '')}</span>
        <span>Tokens: ${escapeHtml(chunk.chunk_token_count ?? '')}</span>
        <span>Weight: ${escapeHtml(chunk.retrieval_weight ?? '')}</span>
        <span>Noise: ${escapeHtml(chunk.is_noise ?? '')}</span>
        ${duplicateCandidate
          ? `<span>Duplicate: ${escapeHtml(dedup.primary_layer || '')} -> ${escapeHtml(dedup.canonical_chunk_id || '')}</span>`
          : ''}
      </div>
      ${renderChunkImages(chunk)}
      <pre>${escapeHtml(chunk.text || '')}</pre>
      <details>
        <summary>Metadata</summary>
        <pre>${escapeHtml(JSON.stringify(chunk.metadata || {}, null, 2))}</pre>
      </details>
    </article>
  `;
  }).join('');
}

function renderChunkImages(chunk) {
  const images = chunkImages(chunk);
  if (!images.length) return '';
  return `
    <div class="chunk-images">
      ${images.map((image) => `
        <figure class="chunk-image-card">
          <img
            src="${escapeHtml(image.url)}"
            alt="${escapeHtml(image.label)}"
            loading="lazy"
            onerror="this.closest('figure').classList.add('image-error')"
          >
          <figcaption>
            <strong>${escapeHtml(image.label)}</strong>
            <code>${escapeHtml(image.url)}</code>
          </figcaption>
        </figure>
      `).join('')}
    </div>
  `;
}

function chunkImages(chunk) {
  const metadata = chunk.metadata || {};
  const candidates = [];
  for (const url of Array.isArray(chunk.image_urls) ? chunk.image_urls : []) {
    addImageCandidate(candidates, url, chunk.image_snapshot_ref || 'chunk image');
  }
  addImageCandidate(candidates, metadata.image_url, metadata.image_snapshot_ref || 'metadata image');
  addImageCandidate(candidates, chunk.image_url, chunk.image_snapshot_ref || 'chunk image');

  const interactionState = metadata.interaction_state || {};
  addImageCandidate(
    candidates,
    interactionState.image_url,
    interactionState.option_label || metadata.image_snapshot_ref || 'interaction state',
  );

  const interactionStates = Array.isArray(metadata.interaction_states)
    ? metadata.interaction_states
    : [];
  for (const state of interactionStates) {
    addImageCandidate(
      candidates,
      state?.image_url,
      state?.option_label || state?.state_id || 'interaction state',
    );
  }

  const markdownImages = markdownImageUrls(chunk.text || '');
  for (const image of markdownImages) {
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

function metric(label, value) {
  return `
    <div class="metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function clearResults() {
  summaryStatus.textContent = 'running';
  summaryStatus.className = 'status-pill partial';
  summaryGrid.innerHTML = '';
  artifactCount.textContent = '0 files';
  artifactGrid.innerHTML = '';
  qualityStatus.textContent = 'empty';
  qualityJson.textContent = '{}';
  manifestStatus.textContent = 'empty';
  manifestJson.textContent = '{}';
  dedupStatus.textContent = 'not run';
  dedupSummaryGrid.innerHTML = '';
  dedupList.innerHTML = '';
  chunkCount.textContent = '0 chunks';
  chunkGrid.innerHTML = '';
  interactionStatus.textContent = 'not run';
  interactionSummaryGrid.innerHTML = '';
  interactionArtifactGrid.innerHTML = '';
  interactionLeftPanel.innerHTML = '';
  interactionCenterPanel.innerHTML = '';
  interactionRightPanel.innerHTML = '';
  interactionDiffGrid.innerHTML = '';
  interactionPromotedChunkGrid.innerHTML = '';
  interactionChunkGrid.innerHTML = '';
  reportLink.textContent = '';
}

function setRunning(isRunning) {
  runBtn.disabled = isRunning;
  runBtn.textContent = isRunning ? 'Running...' : 'Run Review';
}

function setStatus(message, isError) {
  statusBox.textContent = message;
  statusBox.classList.toggle('error', Boolean(isError));
}

function formatApiError(data, fallback) {
  const parts = [data.error || fallback];
  if (data.exit_code !== undefined) parts.push(`exit code: ${data.exit_code}`);
  if (data.stderr) parts.push(`stderr:\n${data.stderr}`);
  if (data.stdout) parts.push(`stdout:\n${data.stdout}`);
  return parts.filter(Boolean).join('\n\n');
}

function statusClass(status) {
  if (status === 'success') return 'success';
  if (status === 'partial') return 'partial';
  return 'bad';
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
