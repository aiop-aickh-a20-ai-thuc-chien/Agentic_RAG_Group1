let chunksData = [];
let currentChunkIndex = -1;
let linkQueue = [];
let isLoadingChunks = false;
let isBatchRunning = false;
let activeReviewMode = 'markdown';

const btnLoadLinks = document.getElementById('btn-load-links');
const tbody = document.getElementById('chunk-list-body');
const countAll = document.getElementById('count-all');
const countWait = document.getElementById('count-wait');
const countDone = document.getElementById('count-done');
const filterCount = document.getElementById('filter-count');

const ctxTitle = document.getElementById('ctx-title');
const ctxMeta = document.getElementById('ctx-meta');
const ctxContent = document.getElementById('ctx-content');
const currChunkId = document.getElementById('current-chunk-id');
const qaQuestion = document.getElementById('qa-question');
const qaAnswer = document.getElementById('qa-answer');
const btnGenerate = document.getElementById('btn-generate');
const btnSave = document.getElementById('btn-save');
const btnBatchRun = document.getElementById('btn-batch-run');
const statusMsg = document.getElementById('status-msg');

const workspaceTabs = document.querySelectorAll('.workspace-tab');
const labelPanel = document.getElementById('label-panel');
const reviewPanel = document.getElementById('review-panel');
const btnOpenSource = document.getElementById('btn-open-source');
const reviewSourceTitle = document.getElementById('review-source-title');
const reviewSourceUrl = document.getElementById('review-source-url');
const rawFrame = document.getElementById('raw-frame');
const rawFallback = document.getElementById('raw-fallback');
const reviewChunkCount = document.getElementById('review-chunk-count');
const parsedMarkdownView = document.getElementById('parsed-markdown-view');
const chunkHighlightView = document.getElementById('chunk-highlight-view');
const btnReviewMarkdown = document.getElementById('btn-review-markdown');
const btnReviewChunks = document.getElementById('btn-review-chunks');

btnLoadLinks.addEventListener('click', async () => {
    if (isLoadingChunks) {
        isLoadingChunks = false;
        btnLoadLinks.textContent = 'Đã dừng nạp.';
        return;
    }

    const txtFilePath = document.getElementById('txt-file-path').value;
    const pdfFolderPath = document.getElementById('pdf-folder-path').value;

    isLoadingChunks = true;
    btnLoadLinks.textContent = 'Đang tải danh sách dữ liệu...';
    try {
        const res = await fetch('/api/parse_list', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ txtFilePath, pdfFolderPath })
        });
        const data = await res.json();
        if (!data.sources || data.sources.length === 0) {
            alert('Không tìm thấy dữ liệu nào!');
            btnLoadLinks.textContent = '+ Nạp Document Chunk';
            return;
        }

        linkQueue = data.sources;
        let processedIds = [];
        try {
            const pRes = await fetch('/api/processed');
            const pData = await pRes.json();
            processedIds = pData.processed_ids || [];
        } catch (e) {
            console.error('Lỗi lấy danh sách đã xử lý:', e);
        }

        for (let i = 0; i < linkQueue.length; i++) {
            if (!isLoadingChunks) break;
            btnLoadLinks.textContent = `Dừng (đang nạp ${i + 1}/${linkQueue.length})...`;
            await loadChunksFromUrl(linkQueue[i], processedIds);
        }
        if (isLoadingChunks) {
            btnLoadLinks.textContent = '+ Nạp Document Chunk';
            statusMsg.textContent = 'Đã cào xong toàn bộ dữ liệu.';
        }
    } catch (err) {
        alert('Error loading data: ' + err.message);
        btnLoadLinks.textContent = '+ Nạp Document Chunk';
    } finally {
        isLoadingChunks = false;
    }
});

async function loadChunksFromUrl(source, processedIds = []) {
    const name = source.path;
    statusMsg.textContent = 'Đang cào dữ liệu: ' + name.substring(0, 80) + '...';
    try {
        const res = await fetch('/api/chunk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: source.path, type: source.type })
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        if (!data.chunks || data.chunks.length === 0) return;

        const isFirst = chunksData.length === 0;
        const docMarkdown = data.markdown || data.chunks.map(c => c.text).join('\n\n');
        const newChunks = data.chunks.map((c, idx) => ({
            id: c.id,
            title: c.title,
            url: c.url || source.path,
            sourceType: source.type,
            text: c.text,
            docMarkdown,
            docIndex: idx,
            status: processedIds.includes(c.id) ? 'Đã duyệt' : 'Chờ nhận',
            labelLoaded: false,
            labelId: ''
        }));
        chunksData = [...chunksData, ...newChunks];
        renderTable();
        if (isFirst && chunksData.length > 0) selectChunk(0);
    } catch (e) {
        console.error('Lỗi cào dữ liệu:', name, e);
        statusMsg.textContent = 'Lỗi cào dữ liệu: ' + name.substring(0, 80);
    }
}

function renderTable() {
    tbody.innerHTML = '';
    chunksData.forEach((chunk, index) => {
        const tr = document.createElement('tr');
        if (index === currentChunkIndex) tr.classList.add('selected');
        const statusCls = chunk.status === 'Chờ nhận' ? 'wait' : 'done';
        tr.innerHTML = `
            <td>${escapeHtml(chunk.id)}</td>
            <td style="font-weight: 500;">${escapeHtml(chunk.title || '(untitled)')}</td>
            <td style="color:#666; font-style:italic;">${escapeHtml(chunk.text.substring(0, 90))}...</td>
            <td><span class="status-badge ${statusCls}">${escapeHtml(chunk.status)}</span></td>
            <td>${chunk.status === 'Đã duyệt' ? 'Đủ QA' : 'Thiếu QA'}</td>
        `;
        tr.onclick = () => selectChunk(index);
        tbody.appendChild(tr);
    });

    const waitCnt = chunksData.filter(c => c.status === 'Chờ nhận').length;
    countAll.textContent = chunksData.length;
    filterCount.textContent = chunksData.length;
    countWait.textContent = waitCnt;
    countDone.textContent = chunksData.length - waitCnt;
    document.getElementById('progress-text').textContent = `${chunksData.length - waitCnt}/${chunksData.length} Chunks`;
}

async function selectChunk(index) {
    currentChunkIndex = index;
    renderTable();
    const chunk = chunksData[index];
    if (!chunk) return;

    currChunkId.textContent = `CHUNK_ID: ${chunk.id}`;
    ctxTitle.value = chunk.title || '';
    ctxMeta.value = `doc: ${chunk.url}`;
    ctxContent.value = chunk.text || '';
    qaQuestion.value = chunk.question || '';
    qaAnswer.value = chunk.answer || '';
    renderReviewPanel(chunk);

    if (!chunk.labelLoaded) {
        await loadExistingLabelForChunk(chunk);
    }
}

async function loadExistingLabelForChunk(chunk) {
    chunk.labelLoaded = true;
    try {
        const res = await fetch(`/api/label?chunkId=${encodeURIComponent(chunk.id)}`);
        const data = await res.json();
        if (!data.found) return;

        chunk.labelId = data.id || '';
        chunk.question = data.question || '';
        chunk.answer = data.expected_answer || '';
        chunk.status = 'Đã duyệt';

        if (chunksData[currentChunkIndex] && chunksData[currentChunkIndex].id === chunk.id) {
            qaQuestion.value = chunk.question;
            qaAnswer.value = chunk.answer;
            statusMsg.textContent = `Đã lazy-load QA từ Excel${chunk.labelId ? ` (${chunk.labelId})` : ''}.`;
        }
        renderTable();
    } catch (err) {
        console.error('Không load được label từ Excel:', err);
    }
}

function renderReviewPanel(chunk) {
    const docChunks = chunksData.filter(c => c.url === chunk.url);
    reviewSourceTitle.textContent = chunk.title || '(untitled)';
    reviewSourceUrl.textContent = chunk.url || '';
    reviewChunkCount.textContent = `${docChunks.length} chunks`;

    if (isHttpUrl(chunk.url)) {
        rawFrame.src = chunk.url;
        rawFrame.classList.remove('hidden');
        rawFallback.classList.add('hidden');
    } else {
        rawFrame.removeAttribute('src');
        rawFrame.classList.add('hidden');
        rawFallback.classList.remove('hidden');
        rawFallback.textContent = `Raw preview chỉ mở trực tiếp cho URL http/https. Source hiện tại: ${chunk.url || '(empty)'}`;
    }

    parsedMarkdownView.innerHTML = renderMarkdownReview(chunk.docMarkdown || '', docChunks, chunk.id);
    chunkHighlightView.innerHTML = renderChunkBlocks(docChunks, chunk.id);
    toggleReviewMode(activeReviewMode);
}

function renderMarkdownReview(markdown, docChunks, activeChunkId) {
    const chunksHtml = docChunks.map((chunk, index) => `
        <article class="review-chunk-card ${chunk.id === activeChunkId ? 'active' : ''}" style="--chunk-color:${chunkColor(index)}">
            <div class="review-chunk-head">Chunk ${index + 1} · ${escapeHtml(chunk.id)}</div>
            <pre>${escapeHtml(chunk.text)}</pre>
        </article>
    `).join('');

    return `
        <div class="markdown-source-block">
            <div class="markdown-label">Parsed Markdown sau HTML extraction</div>
            <pre>${escapeHtml(markdown || '(chưa có markdown)')}</pre>
        </div>
        <div class="markdown-label">Chunk highlight theo document</div>
        <div class="review-chunk-grid">${chunksHtml}</div>
    `;
}

function renderChunkBlocks(docChunks, activeChunkId) {
    if (!docChunks.length) return '<div class="empty-state">Chưa có chunk để hiển thị.</div>';
    return docChunks.map((chunk, index) => `
        <article class="chunk-block ${chunk.id === activeChunkId ? 'active' : ''}" style="--chunk-color:${chunkColor(index)}">
            <header>
                <span>Chunk ${index + 1}</span>
                <code>${escapeHtml(chunk.id)}</code>
            </header>
            <div class="chunk-block-title">${escapeHtml(chunk.title || '(untitled)')}</div>
            <pre>${escapeHtml(chunk.text)}</pre>
        </article>
    `).join('');
}

function toggleReviewMode(mode) {
    activeReviewMode = mode;
    const markdownActive = mode === 'markdown';
    parsedMarkdownView.classList.toggle('hidden', !markdownActive);
    chunkHighlightView.classList.toggle('hidden', markdownActive);
    btnReviewMarkdown.classList.toggle('active', markdownActive);
    btnReviewChunks.classList.toggle('active', !markdownActive);
}

workspaceTabs.forEach(tab => {
    tab.addEventListener('click', () => {
        workspaceTabs.forEach(item => item.classList.remove('active'));
        tab.classList.add('active');
        const view = tab.dataset.view;
        labelPanel.classList.toggle('active', view === 'label');
        reviewPanel.classList.toggle('active', view === 'review');
    });
});

btnReviewMarkdown.addEventListener('click', () => toggleReviewMode('markdown'));
btnReviewChunks.addEventListener('click', () => toggleReviewMode('chunks'));
btnOpenSource.addEventListener('click', () => {
    const chunk = chunksData[currentChunkIndex];
    if (chunk && isHttpUrl(chunk.url)) window.open(chunk.url, '_blank', 'noopener,noreferrer');
});

async function generateQA(index) {
    if (index < 0) {
        alert('Vui lòng click chọn 1 Vector Chunk trước khi sinh QA.');
        return false;
    }
    const chunk = chunksData[index];
    statusMsg.textContent = 'Đang sinh QA...';

    const apiKey = document.getElementById('api-key').value;
    const modelName = document.getElementById('model-name').value;
    const gatewayUrl = document.getElementById('gateway-url').value;

    try {
        const res = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chunkText: chunk.text, apiKey, modelName, gatewayUrl })
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);

        chunk.question = data.question;
        chunk.answer = data.expected_answer;
        chunk.status = 'Đã duyệt';
        selectChunk(index);
        statusMsg.textContent = 'Sinh thành công. Nhớ bấm Lưu Excel.';
        return true;
    } catch (err) {
        statusMsg.textContent = 'Lỗi sinh: ' + err.message;
        return false;
    }
}

async function saveQA(index) {
    if (index < 0) return false;
    const chunk = chunksData[index];
    chunk.question = qaQuestion.value;
    chunk.answer = qaAnswer.value;

    if (!chunk.question || !chunk.answer) {
        alert('Chưa có Question hoặc Answer!');
        return false;
    }

    statusMsg.textContent = 'Đang lưu...';
    try {
        const res = await fetch('/api/excel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                item: {
                    id: chunk.id,
                    title: chunk.title,
                    question: chunk.question,
                    expected_answer: chunk.answer,
                    rag_context: chunk.text,
                    url: chunk.url
                }
            })
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        chunk.status = 'Đã duyệt';
        chunk.labelLoaded = true;
        renderTable();
        statusMsg.textContent = 'Lưu Excel thành công!';
        return true;
    } catch (err) {
        statusMsg.textContent = 'Lỗi lưu Excel: ' + err.message;
        return false;
    }
}

async function generateQABatch(indices) {
    if (!indices || indices.length === 0) return false;
    const apiKey = document.getElementById('api-key').value;
    const modelName = document.getElementById('model-name').value;
    const gatewayUrl = document.getElementById('gateway-url').value;
    const chunksTextArray = indices.map(idx => chunksData[idx].text);

    try {
        const res = await fetch('/api/generate_batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chunksTextArray, apiKey, modelName, gatewayUrl })
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        if (!data.results || data.results.length !== indices.length) {
            throw new Error('Dữ liệu trả về không khớp số lượng.');
        }

        indices.forEach((idx, i) => {
            chunksData[idx].question = data.results[i].question;
            chunksData[idx].answer = data.results[i].expected_answer;
            chunksData[idx].status = 'Đã duyệt';
        });
        selectChunk(indices[0]);
        statusMsg.textContent = 'Sinh batch thành công. Đang lưu...';
        return true;
    } catch (err) {
        statusMsg.textContent = 'Lỗi sinh batch: ' + err.message;
        return false;
    }
}

async function saveQABatch(indices) {
    if (!indices || indices.length === 0) return false;
    const items = indices.map(idx => ({
        id: chunksData[idx].id,
        title: chunksData[idx].title,
        question: chunksData[idx].question,
        expected_answer: chunksData[idx].answer,
        rag_context: chunksData[idx].text,
        url: chunksData[idx].url
    }));

    try {
        const res = await fetch('/api/excel_batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ items })
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        statusMsg.textContent = `Lưu Excel batch thành công ${items.length} items!`;
        return true;
    } catch (err) {
        statusMsg.textContent = 'Lỗi lưu Excel batch: ' + err.message;
        return false;
    }
}

btnGenerate.addEventListener('click', () => generateQA(currentChunkIndex));
btnSave.addEventListener('click', () => saveQA(currentChunkIndex));

btnBatchRun.addEventListener('click', async () => {
    if (isBatchRunning) {
        isBatchRunning = false;
        btnBatchRun.textContent = 'Chạy hàng loạt';
        statusMsg.textContent = 'Đã dừng quá trình chạy auto.';
        return;
    }

    isBatchRunning = true;
    btnBatchRun.textContent = 'Dừng auto batch';
    const delay = parseInt(document.getElementById('batch-delay').value, 10) || 1000;
    const batchSize = parseInt(document.getElementById('batch-size').value, 10) || 5;
    const pendingIndices = chunksData
        .map((chunk, index) => chunk.status === 'Chờ nhận' ? index : -1)
        .filter(index => index >= 0);

    let processed = 0;
    for (let i = 0; i < pendingIndices.length; i += batchSize) {
        if (!isBatchRunning) break;
        const batch = pendingIndices.slice(i, i + batchSize);
        selectChunk(batch[0]);
        statusMsg.textContent = `Đang gọi AI (${batch.length} chunks)... (${processed + 1}-${processed + batch.length}/${pendingIndices.length})`;
        const genSuccess = await generateQABatch(batch);
        if (!genSuccess || !isBatchRunning) break;
        await new Promise(resolve => setTimeout(resolve, delay));
        if (!isBatchRunning) break;
        await saveQABatch(batch);
        processed += batch.length;
    }

    isBatchRunning = false;
    btnBatchRun.textContent = 'Chạy hàng loạt';
    if (statusMsg.textContent.includes('thành công')) {
        statusMsg.textContent = 'Hoàn tất chạy hàng loạt!';
    }
});

function chunkColor(index) {
    const colors = ['#1a73e8', '#d93025', '#188038', '#f9ab00', '#9334e6', '#00acc1', '#e8710a', '#5f6368'];
    return colors[index % colors.length];
}

function isHttpUrl(value) {
    return /^https?:\/\//i.test(value || '');
}

function escapeHtml(value) {
    return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
