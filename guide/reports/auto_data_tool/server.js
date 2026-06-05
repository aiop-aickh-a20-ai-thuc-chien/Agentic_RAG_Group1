require('dotenv').config();
const { Blob, File } = require('node:buffer');
if (!globalThis.Blob) globalThis.Blob = Blob;
if (!globalThis.File) globalThis.File = File;

const express = require('express');
const cors = require('cors');
const axios = require('axios');
const cheerio = require('cheerio');
const fs = require('fs');
const path = require('path');
const XLSX = require('xlsx');
const { OpenAI } = require('openai');
const { execFile } = require('child_process');

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.static('public'));

const LINKS_FILE = path.join(__dirname, '../../../vinfast_vn_vi_links - Copy.txt');
const EXCEL_FILE = path.join(__dirname, '../result.xlsx');

function chunkText(text, chunkSize = 1500, overlap = 200) {
    text = text.replace(/\s+/g, ' ').trim();
    const chunks = [];
    let i = 0;
    while (i < text.length) {
        let chunk = text.slice(i, i + chunkSize);
        if (i + chunkSize < text.length) {
            let lastPeriod = chunk.lastIndexOf('.');
            let lastSpace = chunk.lastIndexOf(' ');
            let breakPoint = lastPeriod > chunk.length - 200 ? lastPeriod + 1 : (lastSpace > 0 ? lastSpace : chunk.length);
            chunk = chunk.slice(0, breakPoint);
            i += breakPoint - overlap;
        } else {
            i += chunkSize;
        }
        if (chunk.trim()) chunks.push(chunk.trim());
    }
    return chunks;
}

// Read links from file
app.post('/api/parse_list', (req, res) => {
    try {
        const { txtFilePath, pdfFolderPath } = req.body;
        let sources = [];
        
        // 1. TXT Links
        if (txtFilePath && fs.existsSync(txtFilePath)) {
            const data = fs.readFileSync(txtFilePath, 'utf8');
            const linkRegex = /https?:\/\/[^\s]+/g;
            const links = data.match(linkRegex) || [];
            const uniqueLinks = [...new Set(links)];
            uniqueLinks.forEach(l => sources.push({ type: 'url', path: l }));
        }
        
        // 2. PDF Folder
        if (pdfFolderPath && fs.existsSync(pdfFolderPath)) {
            const files = fs.readdirSync(pdfFolderPath);
            files.forEach(f => {
                if (f.toLowerCase().endsWith('.pdf')) {
                    sources.push({ type: 'pdf', path: path.join(pdfFolderPath, f) });
                }
            });
        }
        
        res.json({ sources });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/chunk', (req, res) => {
    const { url, type } = req.body; // 'url' here is generic path or actual url
    if (!url) return res.status(400).json({ error: 'No url/path provided' });

    try {
        const pythonInterpreter = path.join(__dirname, '../../..', '.venv', 'Scripts', 'python.exe');
        const scriptPath = path.join(__dirname, 'python_parser.py');
        const flag = type === 'pdf' ? '--pdf' : '--url';
        const env = Object.assign({}, process.env, { PYTHONPATH: '../../../src' });
        
        execFile(pythonInterpreter, [scriptPath, flag, url], { cwd: __dirname, env, maxBuffer: 1024 * 1024 * 10 }, (error, stdout, stderr) => {
            if (error) {
                console.error("Python Error:", stderr || error.message);
                return res.status(500).json({ error: stderr || error.message });
            }
            
            try {
                const out = JSON.parse(stdout);
                if (out.success) {
                    res.json({ chunks: out.chunks, markdown: out.markdown || '' });
                } else {
                    res.status(500).json({ error: out.error });
                }
            } catch (e) {
                res.status(500).json({ error: "Invalid JSON from python parser: " + e.message });
            }
        });
    } catch (err) {
        console.error("Scrape Error:", err.message);
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/generate', async (req, res) => {
    const { chunkText, apiKey, modelName, gatewayUrl } = req.body;
    if (!chunkText) return res.status(400).json({ error: 'Chunk text is required.' });

    try {
        const prompt = `Bạn là một chuyên gia tạo dữ liệu AI (Data Labeler). Dựa vào đoạn văn bản sau, hãy tạo ra MỘT câu hỏi phù hợp mà người dùng có thể hỏi, và MỘT câu trả lời chính xác dựa hoàn toàn vào đoạn văn bản.
Phải trả về MỘT chuỗi JSON hợp lệ theo format sau, KHÔNG thêm bất kỳ markdown code block hay text nào khác ngoài JSON:
{"question": "Câu hỏi ở đây?", "expected_answer": "Câu trả lời ở đây."}

Đoạn văn bản:
${chunkText}`;

        const url = (gatewayUrl || 'https://token-plan-sgp.xiaomimimo.com/v1').replace(/\/$/, '') + '/chat/completions';
        
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${apiKey || 'sk-dummy'}`
            },
            body: JSON.stringify({
                model: modelName || 'mimo-v2.5',
                messages: [{ role: 'user', content: prompt }]
            })
        });

        const resultData = await response.json();
        
        if (!response.ok) {
            throw new Error(`Proxy error: ${response.status} ${response.statusText} - ${JSON.stringify(resultData)}`);
        }

        const rawResponse = resultData.choices[0].message.content;
        let jsonStr = rawResponse.replace(/```json/g, '').replace(/```/g, '').trim();
        const responseJson = JSON.parse(jsonStr);

        res.json({ 
            question: responseJson.question, 
            expected_answer: responseJson.expected_answer 
        });

    } catch (err) {
        console.error("LLM Error:", err.message);
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/generate_batch', async (req, res) => {
    const { chunksTextArray, apiKey, modelName, gatewayUrl } = req.body;
    if (!chunksTextArray || !Array.isArray(chunksTextArray)) return res.status(400).json({ error: 'chunksTextArray is required and must be an array.' });

    try {
        let textsStr = chunksTextArray.map((text, idx) => `[Văn bản ${idx}]:\n${text}`).join('\n\n');
        
        const prompt = `Bạn là một chuyên gia tạo dữ liệu AI (Data Labeler). Tôi sẽ cung cấp cho bạn một mảng gồm ${chunksTextArray.length} văn bản đầu vào.
Với mỗi văn bản, hãy tạo ra MỘT câu hỏi phù hợp và MỘT câu trả lời chính xác dựa hoàn toàn vào đoạn văn bản đó.
Phải trả về MỘT mảng JSON hợp lệ chứa các object tương ứng với đúng thứ tự của văn bản, KHÔNG thêm bất kỳ markdown code block hay text nào khác ngoài mảng JSON.
Format trả về bắt buộc:
[
  {"question": "Câu hỏi 0", "expected_answer": "Câu trả lời 0"},
  {"question": "Câu hỏi 1", "expected_answer": "Câu trả lời 1"}
]

Đầu vào:
${textsStr}`;

        const url = (gatewayUrl || 'https://token-plan-sgp.xiaomimimo.com/v1').replace(/\/$/, '') + '/chat/completions';
        
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${apiKey || 'sk-dummy'}`
            },
            body: JSON.stringify({
                model: modelName || 'mimo-v2.5',
                messages: [{ role: 'user', content: prompt }]
            })
        });

        const resultData = await response.json();
        
        if (!response.ok) {
            throw new Error(`Proxy error: ${response.status} ${response.statusText} - ${JSON.stringify(resultData)}`);
        }

        const rawResponse = resultData.choices[0].message.content;
        let jsonStr = rawResponse.replace(/```json/g, '').replace(/```/g, '').trim();
        const responseArray = JSON.parse(jsonStr);

        if (!Array.isArray(responseArray) || responseArray.length !== chunksTextArray.length) {
             throw new Error('LLM did not return the correct number of items in the JSON array.');
        }

        res.json({ results: responseArray });

    } catch (err) {
        console.error("LLM Batch Error:", err.message);
        res.status(500).json({ error: err.message });
    }
});

const ExcelJS = require('exceljs');
const crypto = require('crypto');

app.post('/api/excel', async (req, res) => {
    const { item } = req.body; 
    if (!item) return res.status(400).json({ error: 'No data to save.' });

    try {
        if (!fs.existsSync(EXCEL_FILE)) {
            return res.status(404).json({ error: 'Excel file not found.' });
        }

        const workbook = new ExcelJS.Workbook();
        await workbook.xlsx.readFile(EXCEL_FILE);
        
        const worksheet = workbook.worksheets[0];
        
        // Find highest Q_n
        let maxQ = 0;
        worksheet.eachRow((row, rowNumber) => {
            const idVal = row.getCell(1).value;
            if (idVal && typeof idVal === 'string' && idVal.startsWith('Q_')) {
                const num = parseInt(idVal.substring(2), 10);
                if (!isNaN(num) && num > maxQ) maxQ = num;
            }
        });
        const newId = `Q_${maxQ + 1}`;
        
        const chunkId = item.id || '';

        const newRow = worksheet.addRow([]);
        
        newRow.getCell(1).value = newId;                                // id
        newRow.getCell(2).value = item.title || '';                     // section_name
        newRow.getCell(3).value = item.question || '';                  // question
        newRow.getCell(4).value = item.expected_answer || '';           // expected_answer
        newRow.getCell(5).value = chunkId;                              // ground_truth_chunk_ids
        newRow.getCell(6).value = item.url || '';                       // ground_truth_doc
        newRow.getCell(8).value = false;                                // is_out_of_scope
        newRow.getCell(9).value = 'single-turn';                        // custom_preconds
        
        // wrap text for visual appeal
        [1, 2, 3, 4, 5, 6, 8, 9].forEach(colIdx => {
            newRow.getCell(colIdx).alignment = { wrapText: true, vertical: 'top' };
        });
        
        newRow.commit();
        
        await workbook.xlsx.writeFile(EXCEL_FILE);

        res.json({ success: true, message: `Saved to Excel.` });
    } catch (err) {
        console.error("Excel Error:", err);
        res.status(500).json({ error: err.message });
    }
});

app.post('/api/excel_batch', async (req, res) => {
    const { items } = req.body; 
    if (!items || !Array.isArray(items)) return res.status(400).json({ error: 'items is required and must be an array.' });

    try {
        if (!fs.existsSync(EXCEL_FILE)) {
            return res.status(404).json({ error: 'Excel file not found.' });
        }

        const workbook = new ExcelJS.Workbook();
        await workbook.xlsx.readFile(EXCEL_FILE);
        
        const worksheet = workbook.worksheets[0];
        
        // Find highest Q_n
        let maxQ = 0;
        worksheet.eachRow((row, rowNumber) => {
            const idVal = row.getCell(1).value;
            if (idVal && typeof idVal === 'string' && idVal.startsWith('Q_')) {
                const num = parseInt(idVal.substring(2), 10);
                if (!isNaN(num) && num > maxQ) maxQ = num;
            }
        });

        items.forEach((item, i) => {
            const newId = `Q_${maxQ + 1 + i}`;
            const chunkId = item.id || '';
            const newRow = worksheet.addRow([]);
            
            newRow.getCell(1).value = newId;                                // id
            newRow.getCell(2).value = item.title || '';                     // section_name
            newRow.getCell(3).value = item.question || '';                  // question
            newRow.getCell(4).value = item.expected_answer || '';           // expected_answer
            newRow.getCell(5).value = chunkId;                              // ground_truth_chunk_ids
            newRow.getCell(6).value = item.url || '';                       // ground_truth_doc
            newRow.getCell(8).value = false;                                // is_out_of_scope
            newRow.getCell(9).value = 'single-turn';                        // custom_preconds
            
            // wrap text for visual appeal
            [1, 2, 3, 4, 5, 6, 8, 9].forEach(colIdx => {
                newRow.getCell(colIdx).alignment = { wrapText: true, vertical: 'top' };
            });
            newRow.commit();
        });
        
        await workbook.xlsx.writeFile(EXCEL_FILE);

        res.json({ success: true, message: `Saved ${items.length} items to Excel.` });
    } catch (err) {
        console.error("Excel Batch Error:", err);
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/processed', async (req, res) => {
    try {
        if (!fs.existsSync(EXCEL_FILE)) {
            return res.json({ processed_ids: [] });
        }
        const workbook = new ExcelJS.Workbook();
        await workbook.xlsx.readFile(EXCEL_FILE);
        const worksheet = workbook.worksheets[0];
        
        let ids = [];
        worksheet.eachRow((row, rowNumber) => {
            const chunkId = row.getCell(5).value;
            if (chunkId && typeof chunkId === 'string' && chunkId.trim()) {
                ids.push(chunkId.trim());
            }
        });
        res.json({ processed_ids: [...new Set(ids)] });
    } catch (err) {
        console.error("Processed API Error:", err);
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/label', async (req, res) => {
    const chunkId = (req.query.chunkId || '').toString().trim();
    if (!chunkId) return res.status(400).json({ error: 'chunkId is required.' });

    try {
        if (!fs.existsSync(EXCEL_FILE)) {
            return res.json({ found: false });
        }

        const workbook = new ExcelJS.Workbook();
        await workbook.xlsx.readFile(EXCEL_FILE);
        const worksheet = workbook.worksheets[0];

        let found = null;
        worksheet.eachRow((row, rowNumber) => {
            if (found || rowNumber === 1) return;
            const rowChunkId = (row.getCell(5).value || '').toString().trim();
            if (rowChunkId !== chunkId) return;
            found = {
                found: true,
                id: (row.getCell(1).value || '').toString(),
                title: (row.getCell(2).value || '').toString(),
                question: (row.getCell(3).value || '').toString(),
                expected_answer: (row.getCell(4).value || '').toString(),
                chunk_id: rowChunkId,
                url: (row.getCell(6).value || '').toString()
            };
        });

        res.json(found || { found: false });
    } catch (err) {
        console.error("Label API Error:", err);
        res.status(500).json({ error: err.message });
    }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
});
