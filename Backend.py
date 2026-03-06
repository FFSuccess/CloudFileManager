from fastapi import FastAPI, HTTPException, File, UploadFile, Query, Header, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import uvicorn
import os
from datetime import datetime
from typing import List
import shutil
from PIL import Image
import io
import sys
import ctypes
import win32gui, win32ui, win32con
import zipfile
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict
from bcrypt import gensalt, hashpw, checkpw
from starlette.responses import FileResponse
from base64 import b64decode
from fastapi.responses import JSONResponse

STORAGE_FOLDER = "Storage_folder"
TEMPORARY_FOLDER = 'TEMP'
ARCHIVE_EXTENTION = 'zip'
HASHED_PASSWORDS_FILE = 'Passwords.txt'
if not os.path.exists(HASHED_PASSWORDS_FILE):
    with open(HASHED_PASSWORDS_FILE, "w+") as password_file:
        pass

app = FastAPI()

# CORS (Express proxy)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def check_user_login(user_name: str, password: str):
    with open(HASHED_PASSWORDS_FILE, "r") as password_file:
        for line in password_file:
            # Each line is in the format: base64username:hashed_password
            try:
                encoded_username, hashed_password = line.strip().split(":", 1)
            except ValueError:
                continue
            decoded_username = b64decode(encoded_username.encode("utf-8")).decode("utf-8")
            if decoded_username == user_name:
                if checkpw(password.encode("utf-8"), hashed_password.encode("utf-8")):
                    return True
                return False
        return False

def is_file(path):
    try:
        with open(path, "rb") as file:
            pass
        return True
    except:
        return False

def zip_file(output_name, archive_format, target_file):
    target_path = os.path.join(STORAGE_FOLDER, target_file)
    tempory_path = os.path.join(TEMPORARY_FOLDER, output_name)
    return shutil.make_archive(tempory_path, archive_format, target_path)

def extract_zip(output_path, target_path):
    with zipfile.ZipFile(target_path, 'r') as zip_ref:

        # Normalize output path once
        output_path = os.path.abspath(output_path)

        # 1️⃣ Pre-scan for collisions
        for member in zip_ref.namelist():
            # Skip directory entries
            if member.endswith("/"):
                continue

            dest_path = os.path.abspath(os.path.join(output_path, member))

            # Security: prevent zip-slip
            if not dest_path.startswith(output_path + os.sep):
                raise ValueError(f"Illegal path in zip: {member}")

            # Check if file OR parent folder exists
            if os.path.exists(dest_path):
                raise FileExistsError(f"File already exists: {dest_path}")

            # Also block folder collisions
            parent_dir = os.path.dirname(dest_path)
            if os.path.exists(parent_dir) and not os.path.isdir(parent_dir):
                raise FileExistsError(f"Path collision: {parent_dir}")

        # 2️⃣ Safe to extract
        zip_ref.extractall(output_path)

def get_file_icon(file_path, size=64):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File {file_path} not found")

    if sys.platform.startswith("win"):


        SHGFI_ICON = 0x100
        SHGFI_LARGEICON = 0x0
        SHGFI_SMALLICON = 0x1

        class SHFILEINFO(ctypes.Structure):
            _fields_ = [
                ("hIcon", ctypes.c_void_p),
                ("iIcon", ctypes.c_int),
                ("dwAttributes", ctypes.c_uint),
                ("szDisplayName", ctypes.c_wchar * 260),
                ("szTypeName", ctypes.c_wchar * 80)
            ]

        # Get the icon handle
        shfileinfo = SHFILEINFO()
        flags = SHGFI_ICON | (SHGFI_SMALLICON if size <= 32 else SHGFI_LARGEICON)
        ctypes.windll.shell32.SHGetFileInfoW(
            file_path,
            0,
            ctypes.byref(shfileinfo),
            ctypes.sizeof(shfileinfo),
            flags
        )
        hicon = shfileinfo.hIcon

        # Create compatible DC
        hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
        hdc_mem = hdc.CreateCompatibleDC()

        # Create 32-bit bitmap for alpha channel
        hbmp = win32ui.CreateBitmap()
        hbmp.CreateCompatibleBitmap(hdc, size, size)
        hdc_mem.SelectObject(hbmp)

        # Fill bitmap with transparency
        brush = win32gui.GetStockObject(win32con.WHITE_BRUSH)
        win32gui.FillRect(hdc_mem.GetSafeHdc(), (0, 0, size, size), brush)

        # Draw icon into bitmap
        win32gui.DrawIconEx(hdc_mem.GetSafeHdc(), 0, 0, hicon, size, size, 0, 0, win32con.DI_NORMAL)

        # Convert bitmap to bytes
        bmpinfo = hbmp.GetInfo()
        bmpstr = hbmp.GetBitmapBits(True)

        # Create RGBA image to preserve transparency
        img = Image.frombuffer(
            'RGBA',
            (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
            bmpstr, 'raw', 'BGRA', 0, 1
        )

        # Cleanup
        win32gui.DestroyIcon(hicon)
        hdc_mem.DeleteDC()
        hdc.DeleteDC()
        return img

    else:
        raise NotImplementedError("This version only handles Windows icons.")

def ensure_storage_folder():
    os.makedirs(STORAGE_FOLDER, exist_ok=True)

def list_all_items() -> List[str]:
    ensure_storage_folder()
    return os.listdir(STORAGE_FOLDER)

def format_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"

def get_file_info(filename: str) -> dict:
    path = os.path.join(STORAGE_FOLDER, filename)

    if not os.path.exists(path):
        raise FileNotFoundError(filename)

    if os.path.isdir(path):
        sum_size = 0
        for root, dirs, files in os.walk(path):
            for file in files:
                full_file_path = os.path.join(root, file)
                try:
                    sum_size += int(os.path.getsize(full_file_path))
                except FileNotFoundError:
                    pass
        size_bytes = sum_size
    else:
        size_bytes = os.path.getsize(path)

    created_time = datetime.fromtimestamp(os.path.getctime(path))

    return {
        "file": filename,
        "size": {
            "formatted": format_size(size_bytes),
            "raw": size_bytes,
        },
        "upload_time": {
            "formatted": created_time.strftime("%d/%m/%Y %H:%M:%S"),
            "raw": created_time.isoformat(),
        },
    }

def delete_items(item_names: List[str]) -> dict:
    print(item_names)
    deleted = []
    failed = []

    for name in item_names:
        try:
            file_path = os.path.join(STORAGE_FOLDER, name)
            if not os.path.isdir(file_path):
                os.remove(file_path)
            else:
                for root, dirs, files in os.walk(file_path):
                    for filename in files:
                        delete_file_path = os.path.join(root, filename)
                        os.remove(delete_file_path)
                for root, dirs, files in os.walk(file_path):
                    for directory in dirs:
                        os.rmdir(os.path.join(root, directory))
                os.rmdir(file_path)
            deleted.append(name)
        except Exception as e:
            print(e)
            failed.append(name)

    return {
        "status": "success" if not failed else "fail",
        "deleted_items": deleted,
        "failed_items": failed,
    }

class SessionManager:
    def __init__(self, session_timeout_minutes: int = 60):
        self.sessions: Dict[str, dict] = {}
        self.session_timeout = timedelta(minutes=session_timeout_minutes)

    def create_session(self, user_id: str) -> str:
        # Generate a secure random token
        token = secrets.token_urlsafe(32)

        # Store session information
        self.sessions[token] = {
            "user_id": user_id,
            "created_at": datetime.now(),
            "last_active": datetime.now()
        }
        return token

    def validate_session(self, token: str) -> Optional[str]:
        if token not in self.sessions:
            return None
        session = self.sessions[token]
        # check if session has expired
        if datetime.now() - session["last_active"] > self.session_timeout:
            self.delete_session(token)
            return None
        # update last active time
        session["last_active"] = datetime.now()
        return session["user_id"]

    def delete_session(self, token: str) -> bool:
        if token in self.sessions:
            del self.sessions[token]
            return True
        return False

    def cleanup_expired_sessions(self):
        now = datetime.now()
        expired_tokens = [
            token for token, session in self.sessions.items()
            if now - session["last_active"] > self.session_timeout
        ]
        for token in expired_tokens:
            del self.sessions[token]
        return len(expired_tokens)

current_session = SessionManager()

def authenticate(user: str = None, password: str = None, session_token: str = None):
    if session_token:
        if current_session.validate_session(session_token):
            return True, session_token
    if not (user and password):
        return False, None
    if check_user_login(user, password):
        return True, current_session.create_session(gensalt())
    return False, None

@app.middleware("http")
async def check_session_token_middleware(request: Request, call_next):
    protected_paths = ("/api", "/download", "/upload")

    # Only enforce token if the request path starts with a protected path
    if request.url.path.startswith(protected_paths):
        token = request.headers.get("X-Session-Token")
        if not token or not current_session.validate_session(token):
            return JSONResponse({"detail": "Invalid or missing session token"}, status_code=401)

    response = await call_next(request)
    return response

@app.get("/")
async def root():
    return {"message": "FastAPI backend is running"}

@app.get("/api/items")
async def get_all_items():
    return {"items": list_all_items()}

@app.get("/api/items/info")
async def get_all_items_info():
    items = list_all_items()
    return {
        "items": [get_file_info(item) for item in items]
    }

@app.get("/login")
async def try_login(user_name: str, password: str):
    login_success, login_token = authenticate(user_name, password)
    login_status = "success" if login_success else "fail"
    return {"status": login_status,
            "token": login_token}

@app.get("/api/items/info/{item_names}")
async def get_specific_items_info(item_names: str):
    names = item_names.split(",")
    info = []

    for name in names:
        try:
            info.append(get_file_info(name))
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"{name} not found")

    return {"items": info}

@app.get("/api/file_content")
async def get_file_content(item_name: str):
    file_path = os.path.join(STORAGE_FOLDER, item_name)
    try:
        with open(file_path, "r") as file:
            contence = file.read()
        return {"status" : "success",
                "content" : contence}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"{item_name} not found")
    except Exception as e:
        return {"status" : "fail",
                "error" : e}

@app.delete("/api/items/{item_names}")
async def delete_item(item_names: str):
    names = item_names.split(",")
    return delete_items(names)

@app.get("/download/{filename}")
async def download_file(filename: str):
    try:
        format_path = os.path.normpath(filename)
        file_path = os.path.join(STORAGE_FOLDER, format_path)

        if not os.path.isdir(file_path):
            return FileResponse(
                path=file_path,
                filename=filename,
                media_type="application/octet-stream"
            )
        else:
            archive_name = os.path.basename(format_path)
            archive_file_path = zip_file(format_path, ARCHIVE_EXTENTION, archive_name)
            return FileResponse(
                path=archive_file_path,
                filename=f"{archive_name}.{ARCHIVE_EXTENTION}",
                media_type="application/octet-stream"
            )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"{item_name} not found")
    except Exception as e:
        HTTPException(status_code=404, detail=f"Error getting file: {e}")

@app.get("/icon")
async def get_icon(relative_path: str):
    relative_path = os.path.normpath(relative_path)
    file = os.path.join(STORAGE_FOLDER, relative_path)
    try:
        # Get the PIL.Image
        img = get_file_icon(file, size=64)
        # Convert PIL image to PNG bytes
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        # Return as StreamingResponse
        return StreamingResponse(buf, media_type="image/png")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")

@app.post("/upload/files")
async def folder_upload(file: UploadFile = File(...), relative_path: str = STORAGE_FOLDER):
    os.makedirs(TEMPORARY_FOLDER, exist_ok=True)
    if relative_path != STORAGE_FOLDER:
        if not ("." in relative_path):
            extract_dir = os.path.join(STORAGE_FOLDER, relative_path)
        else:
            extract_dir = STORAGE_FOLDER
    else:
        extract_dir = STORAGE_FOLDER

    temp_zip_path = os.path.join(TEMPORARY_FOLDER, f"{file.filename}")
    if os.path.exists(extract_dir) and (extract_dir != STORAGE_FOLDER):
        return {
            "status": "fail",
            "info": {"status": "fail", "file_path": extract_dir, "error": "File already exists."}
        }
    os.makedirs(extract_dir, exist_ok=True)
    file_upload_info = []
    successful_uploads = 0

    try:
        with open(temp_zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        extract_zip(extract_dir, temp_zip_path)

        for root, dirs, files in os.walk(extract_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                file_upload_info.append({"status": "success", "file_path": file_path})
                successful_uploads += 1

    except Exception as e:
        file_upload_info.append({"status": "fail", "file_path": temp_zip_path, "error": str(e)})

    finally:
        if os.path.exists(temp_zip_path):
            os.remove(temp_zip_path)
        return {
            "status": "success" if successful_uploads > 0 else "fail",
            "info": file_upload_info
        }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
