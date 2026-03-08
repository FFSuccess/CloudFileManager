const express = require('express');
const fs = require('fs');
const path = require('path');
const axios = require('axios');
const multer = require('multer');
const FormData = require('form-data');
const { readFile } = require('fs').promises;

const app = express();
app.use(express.json());

const BACKEND_URL = "http://localhost:8000"; // FastAPI backend
const TEMP_UPLOAD_DIR = path.join(__dirname, "temp_uploads");
const FAIL_MESSAGE = "Failed to load page";

// Ensure temp upload dir exists
if (!fs.existsSync(TEMP_UPLOAD_DIR)) fs.mkdirSync(TEMP_UPLOAD_DIR, { recursive: true });

// Multer for ZIP uploads
const upload = multer({
    dest: TEMP_UPLOAD_DIR,
    limits: { fileSize: 1024 * 1024 * 1024 } // 1GB
});

// Helper: get session token
function getSessionToken(req) {
    const authHeader = req.headers.authorization;
    if (authHeader && authHeader.startsWith('Bearer ')) return authHeader.slice(7);
    return req.headers['x-session-token'] || null;
}

// Helper: create headers
function getAuthHeaders(req, extra = {}) {
    const token = getSessionToken(req);
    const headers = { ...extra };
    if (token) headers['X-Session-Token'] = token;
    return headers;
}

// Serve HTML files
async function serveHTML(res, filePath) {
    try {
        const html = await readFile(filePath, 'utf-8');
        res.send(html);
    } catch (err) {
        console.error(err);
        res.status(500).send(FAIL_MESSAGE);
    }
}

// --- API Proxy Routes using axios --- //

app.get('/api/login', async (req, res) => {
    try {
        const { user_name, password } = req.query;
        const response = await axios.get(`${BACKEND_URL}/login`, { params: { user_name, password } });
        res.status(response.status).json(response.data);
    } catch (err) {
        console.error(err);
        res.status(err.response?.status || 500).json(err.response?.data || { error: 'Backend error' });
    }
});

app.get('/api/items', async (req, res) => {
    try {
        const response = await axios.get(`${BACKEND_URL}/api/items`, {
            headers: getAuthHeaders(req)
        });
        res.status(response.status).json(response.data);
    } catch (err) {
        console.error(err);
        res.status(err.response?.status || 500).json(err.response?.data || { error: 'Backend error' });
    }
});

app.get('/api/items/info', async (req, res) => {
    try {
        const response = await axios.get(`${BACKEND_URL}/api/items/info`, {
            headers: getAuthHeaders(req)
        });
        res.status(response.status).json(response.data);
    } catch (err) {
        console.error(err);
        res.status(err.response?.status || 500).json(err.response?.data || { error: 'Backend error' });
    }
});

app.get('/api/items/info/:item_names', async (req, res) => {
    try {
        const response = await axios.get(`${BACKEND_URL}/api/items/info/${req.params.item_names}`, {
            headers: getAuthHeaders(req)
        });
        res.status(response.status).json(response.data);
    } catch (err) {
        console.error(err);
        res.status(err.response?.status || 500).json(err.response?.data || { error: 'Backend error' });
    }
});

app.get('/api/file_content', async (req, res) => {
    try {
        const response = await axios.get(`${BACKEND_URL}/api/file_content`, {
            params: { item_name: req.query.item_name },
            headers: getAuthHeaders(req)
        });
        res.status(response.status).json(response.data);
    } catch (err) {
        console.error(err);
        res.status(err.response?.status || 500).json(err.response?.data || { error: 'Backend error' });
    }
});

// DELETE items
app.delete('/api/items/:item_names', async (req, res) => {
    try {
        const response = await axios.delete(`${BACKEND_URL}/api/items/${encodeURIComponent(req.params.item_names)}`, {
            headers: getAuthHeaders(req)
        });
        res.status(response.status).json(response.data);
    } catch (err) {
        console.error(err);
        res.status(err.response?.status || 500).json(err.response?.data || { error: 'Backend error' });
    }
});

// Download file
app.get('/download/:filename', async (req, res) => {
    try {
        const response = await axios.get(`${BACKEND_URL}/download/${encodeURIComponent(req.params.filename)}`, {
            headers: getAuthHeaders(req),
            responseType: 'stream'
        });

        const filename = req.params.filename.includes('.') ? req.params.filename : req.params.filename + '.zip';
        res.setHeader('Content-Type', response.headers['content-type'] || 'application/zip');
        res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
        response.data.pipe(res);
    } catch (err) {
        console.error("Download failed:", err.message);
        res.status(err.response?.status || 500).send("Download failed");
    }
});

// Serve frontend HTML
app.get('/', (req, res) => serveHTML(res, './home.html'));
app.get('/login', (req, res) => serveHTML(res, './login.html'));

// ZIP upload
app.post("/upload/files", upload.single("files"), async (req, res) => {
    if (!req.file) return res.status(400).json({ status: "fail", error: "No file uploaded" });

    const zipPath = req.file.path;
    const zipName = req.file.originalname;

    try {
        const formData = new FormData();
        formData.append("file", fs.createReadStream(zipPath), zipName);
        if (req.body.relative_path) formData.append("relative_path", req.body.relative_path);

        const token = getSessionToken(req);
        const headers = { ...formData.getHeaders() };
        if (token) headers['X-Session-Token'] = token;

        const response = await axios.post(`${BACKEND_URL}/upload/files`, formData, {
            headers,
            maxContentLength: Infinity,
            maxBodyLength: Infinity
        });

        res.json(response.data);
    } catch (err) {
        console.error("Upload failed:", err.message);
        res.status(err.response?.status || 500).json({ status: "fail", error: "Upload failed" });
    } finally {
        fs.unlink(zipPath, () => {});
    }
});

// Icon proxy
app.get("/get-icon", async (req, res) => {
    try {
        const token = getSessionToken(req);
        const headers = {};
        if (token) headers['X-Session-Token'] = token;

        const response = await axios.get(`${BACKEND_URL}/icon`, {
            params: { relative_path: req.query.relative_path },
            responseType: 'arraybuffer',
            headers
        });

        res.setHeader("Content-Type", "image/png");
        res.send(response.data);
    } catch (err) {
        console.error(err.message);
        res.status(err.response?.status || 500).send("Icon error");
    }
});

// Start server
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Server running on ${PORT}`));
