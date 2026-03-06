const express = require('express');
const fetch = require('node-fetch');
const { readFile } = require('fs').promises;
const fs = require('fs');
const path = require('path');
const axios = require("axios");
const multer = require('multer');
const FormData = require('form-data');

const app = express();
app.use(express.json());

const FAIL_MESSAGE = "Failed to load page";
const BACKEND_URL = "http://localhost:8000"; // FastAPI backend
const TEMP_UPLOAD_DIR = path.join(__dirname, "temp_uploads");

// Ensure temp dir exists
if (!fs.existsSync(TEMP_UPLOAD_DIR)) {
    fs.mkdirSync(TEMP_UPLOAD_DIR, { recursive: true });
}

 
// MULTER (ZIP UPLOAD ONLY)
const upload = multer({
    dest: TEMP_UPLOAD_DIR,
    limits: {
        fileSize: 1024 * 1024 * 1024 // 1GB
    }
});


// HELPER: Get session token from request
function getSessionToken(req) {
    // Check Authorization header first (Bearer token)
    const authHeader = req.headers.authorization;
    if (authHeader && authHeader.startsWith('Bearer ')) {
        return authHeader.substring(7);
    }

    // Check X-Session-Token header
    return req.headers['x-session-token'] || null;
}

// HELPER: Create headers with session token
function getAuthHeaders(req, additionalHeaders = {}) {
    const token = getSessionToken(req);
    const headers = { ...additionalHeaders };

    if (token) {
        headers['X-Session-Token'] = token;
    }

    return headers;
}


// HTML SERVING
async function serveHTML(res, filePath) {
    try {
        const html = await readFile(filePath, 'utf-8');
        res.send(html);
    } catch (err) {
        console.error(err);
        res.status(500).send(FAIL_MESSAGE);
    }
}


// API PROXY ROUTES
app.get('/api/login', async (req, res) => {
    try {
        const { user_name, password } = req.query;
        const response = await fetch(
            `${BACKEND_URL}/login?user_name=${encodeURIComponent(user_name)}&password=${encodeURIComponent(password)}`
        );
        res.status(response.status).json(await response.json());
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Backend error' });
    }
});

app.get('/api/items', async (req, res) => {
    try {
        const response = await fetch(`${BACKEND_URL}/api/items`, {
            headers: getAuthHeaders(req)
        });
        res.status(response.status).json(await response.json());
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Backend error' });
    }
});

app.get('/api/items/info', async (req, res) => {
    try {
        const response = await fetch(`${BACKEND_URL}/api/items/info`, {
            headers: getAuthHeaders(req)
        });
        res.status(response.status).json(await response.json());
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Backend error' });
    }
});

app.get('/api/items/info/:item_names', async (req, res) => {
    try {
        const response = await fetch(`${BACKEND_URL}/api/items/info/${req.params.item_names}`, {
            headers: getAuthHeaders(req)
        });
        res.status(response.status).json(await response.json());
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Backend error' });
    }
});

app.get('/api/file_content', async (req, res) => {
    try {
        const response = await fetch(
            `${BACKEND_URL}/api/file_content?item_name=${encodeURIComponent(req.query.item_name)}`,
            {
                headers: getAuthHeaders(req)
            }
        );
        res.status(response.status).json(await response.json());
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Backend error' });
    }
});

// DOWNLOAD
app.get('/download/:filename', async (req, res) => {
    try {
        const response = await fetch(`${BACKEND_URL}/download/${encodeURIComponent(req.params.filename)}`, {
            headers: getAuthHeaders(req)
        });

        if (!response.ok) {
            if (response.status === 401) return res.status(401).json({ error: 'Unauthorized' });
            return res.sendStatus(response.status);
        }

        // 1. Determine the filename
        let filename = req.params.filename;

        // 2. Logic: If the filename doesn't contain a dot, add .zip
        if (!filename.includes('.')) {
            filename += '.zip';
        }

        // 3. Set headers
        const contentType = response.headers.get("content-type") || "application/zip";
        res.setHeader("Content-Type", contentType);
        res.setHeader("Content-Disposition", `attachment; filename="${filename}"`);

        // Pipe the raw stream properly
        response.body.pipe(res);

        response.body.on("error", (err) => {
            console.error("Stream error:", err);
            res.end();
        });
    } catch (err) {
        console.error("Download failed:", err);
        res.status(500).send("Download failed");
    }
});


// DELETE
app.delete('/api/items/:item_names', async (req, res) => {
    try {
        const itemNames = req.params.item_names;

        if (!itemNames) {
            return res.status(400).json({ error: 'No items specified' });
        }

        const encoded = encodeURIComponent(itemNames);

        const response = await fetch(`${BACKEND_URL}/api/items/${encoded}`, {
            method: "DELETE",
            headers: getAuthHeaders(req)
        });

        const text = await response.text();
        res.status(response.status);

        try {
            res.json(JSON.parse(text));
        } catch {
            res.send(text);
        }
    } catch (err) {
        console.error('Express delete error:', err);
        res.status(500).json({ error: 'Backend error', details: err.message });
    }
});

// FRONTEND ROUTES (NO AUTH)
app.get('/', (req, res) => serveHTML(res, './home.html'));
app.get('/login', (req, res) => serveHTML(res, './login.html'));

// ZIP UPLOAD → FASTAPI
app.post("/upload/files", upload.single("files"), async (req, res) => {
    if (!req.file) {
        return res.status(400).json({ status: "fail", error: "No file uploaded" });
    }

    const zipPath = req.file.path;
    const zipName = req.file.originalname;

    try {
        const formData = new FormData();
        formData.append("file", fs.createReadStream(zipPath), zipName);

        if (req.body.relative_path) {
            formData.append("relative_path", req.body.relative_path);
        }

        // Get session token and add to headers
        const token = getSessionToken(req);
        const headers = {
            ...formData.getHeaders()
        };

        if (token) {
            headers['X-Session-Token'] = token;
        }

        const response = await axios.post(
            `${BACKEND_URL}/upload/files`,
            formData,
            {
                headers: headers,
                maxBodyLength: Infinity,
                maxContentLength: Infinity
            }
        );

        res.json(response.data);
    } catch (err) {
        console.error("Upload forwarding failed:", err.message);

        // Handle authentication errors
        if (err.response?.status === 401) {
            return res.status(401).json({ status: "fail", error: "Unauthorized" });
        }

        res.status(500).json({ status: "fail", error: "Upload forwarding failed" });
    } finally {
        fs.unlink(zipPath, () => {});
    }
});

// ICON PROXY
app.get("/get-icon", async (req, res) => {
    try {
        const token = getSessionToken(req);
        const headers = {};

        if (token) {
            headers['X-Session-Token'] = token;
        }

        const pythonResponse = await axios.get(`${BACKEND_URL}/icon`, {
            params: { relative_path: req.query.relative_path },
            responseType: "arraybuffer",
            headers: headers
        });

        res.set("Content-Type", "image/png");
        res.send(pythonResponse.data);
    } catch (err) {
        if (err.response?.status === 401) {
            return res.status(401).json({ error: 'Unauthorized' });
        }
        res.status(err.response?.status || 500).send("Icon error");
    }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, "0.0.0.0", () => {
  console.log("Server running on", PORT);
});
