from fastapi import FastAPI, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from typing import List
import shutil
import zipfile
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict
from bcrypt import gensalt, checkpw
from base64 import b64decode
from fastapi.responses import JSONResponse
from fastapi import Request, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path

TEMPORARY_FOLDER = 'TEMP'
ARCHIVE_EXTENTION = 'zip'
HASHED_PASSWORDS_FILE = 'Passwords.txt'
ICONS_DIR = Path("Icons")
ICON_GROUPS = {
    "xlsx": ["xls", "xlsx", "xlsm", "ods", "csv"],
    "docx": ["doc", "docx", "odt", "rtf", "txt"],
    "pdf": ["pdf"],
    "jpeg": ["jpg", "jpeg", "jpe"],
    "png": ["png"],
    "zip": ["zip", "rar", "7z", "tar", "gz"],
}
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

def resolve_icon(ext: str) -> str:
    for icon, exts in ICON_GROUPS.items():
        if ext in exts:
            return f"{icon}.png"
    return "file.png"

def check_user_login(user_name: str, password: str):
    with open(HASHED_PASSWORDS_FILE, "r") as current_password_file:
        for line in current_password_file:
            # Each line is in the format: base64username:hashed_password
            try:
                encoded_username, hashed_password, user_id = line.strip().split(":", 2)
            except ValueError:
                continue
            decoded_username = b64decode(encoded_username.encode("utf-8")).decode("utf-8")
            if decoded_username == user_name:
                if checkpw(password.encode("utf-8"), hashed_password.encode("utf-8")):
                    return user_id
                return False
        return False

def zip_file(storage_folder, output_name, archive_format, target_file):
    target_path = os.path.join(storage_folder, target_file)
    tempory_path = os.path.join(TEMPORARY_FOLDER, output_name)
    return shutil.make_archive(tempory_path, archive_format, str(target_path))

def extract_zip(output_path, target_path):
    with zipfile.ZipFile(target_path, 'r') as zip_ref:
        output_path = os.path.abspath(output_path)
        # scan for collisions
        for member in zip_ref.namelist():
            if member.endswith("/"):
                continue
            dest_path = os.path.abspath(os.path.join(output_path, member))
            # prevent zip-slip
            if not dest_path.startswith(output_path + os.sep):
                raise ValueError(f"Illegal path in zip: {member}")
            # check if file ir parent folder exists
            if os.path.exists(dest_path):
                raise FileExistsError(f"File already exists: {dest_path}")
            # block folder collisions
            parent_dir = os.path.dirname(dest_path)
            if os.path.exists(parent_dir) and not os.path.isdir(parent_dir):
                raise FileExistsError(f"Path collision: {parent_dir}")
        zip_ref.extractall(output_path)

def list_all_items(storage_folder) -> List[str]:
    return os.listdir(storage_folder)

def format_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"

def get_file_info(storage_folder, filename: str) -> dict:
    path = os.path.join(storage_folder, filename)

    if not os.path.exists(path):
        raise FileNotFoundError(filename)

    if os.path.isdir(path):
        sum_size = 0
        for root_folder, dirs, files in os.walk(path):
            for file in files:
                full_file_path = os.path.join(root_folder, file)
                try:
                    sum_size += os.path.getsize(full_file_path)
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

def delete_items(storage_folder, item_names: List[str]) -> dict:
    print(item_names)
    deleted = []
    failed = []

    for name in item_names:
        try:
            file_path = os.path.join(storage_folder, name)
            if not os.path.isdir(file_path):
                os.remove(file_path)
            else:
                for root_folder, dirs, files in os.walk(file_path):
                    for filename in files:
                        delete_file_path = os.path.join(root_folder, filename)
                        os.remove(delete_file_path)
                for root_folder, dirs, files in os.walk(file_path):
                    for directory in dirs:
                        os.rmdir(os.path.join(root_folder, directory))
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

    def create_session(self, token_representation: str, user_storage_id: str) -> str:
        token = secrets.token_urlsafe(32)
        self.sessions[token] = {
            "user_id": token_representation,
            "created_at": datetime.now(),
            "last_active": datetime.now(),
            "user_storage_id": user_storage_id,
        }
        return token

    def validate_session(self, token: str) -> Optional[any]:
        if token not in self.sessions:
            return None
        session = self.sessions[token]
        # check if session has expired
        if datetime.now() - session["last_active"] > self.session_timeout:
            self.delete_session(token)
            return None
        # update last active time
        session["last_active"] = datetime.now()
        return session["user_id"], session["user_storage_id"]

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
        validated = current_session.validate_session(session_token)
        if validated:
            user_id, storage_id = validated
            return True, session_token, storage_id
    if not (user and password):
        return False, None, None
    possible_user_id = check_user_login(user, password)
    if possible_user_id:
        return True, current_session.create_session(str(gensalt()), possible_user_id), possible_user_id
    return False, None, None

@app.middleware("http")
async def check_session_token_middleware(request: Request, call_next):
    protected_paths = ("/api", "/download", "/upload", "/login, /icon")
    if not request.url.path.startswith(protected_paths):
        return await call_next(request)
    token = request.headers.get("X-Session-Token")
    user_password = request.headers.get("X-Password")
    user_name = request.headers.get("X-Username")
    was_successful, session_token, storage_id = authenticate(
        user=user_name, password=user_password, session_token=token
    )
    if not was_successful:
        return JSONResponse({"detail": "Invalid or missing session token, username or password"}, status_code=401)
    storage_folder = f"USER_STORAGE_{storage_id}"
    request.state.user_storage_folder = storage_folder
    # only create if not exists
    os.makedirs(storage_folder, exist_ok=True)
    response = await call_next(request)
    return response

@app.get("/")
async def root():
    return {"message": "FastAPI backend is running"}

@app.get("/api/items")
async def get_all_items(request: Request):
    storage_folder_to_user = getattr(request.state, "user_storage_folder", None)
    return {"items": list_all_items(storage_folder_to_user)}

@app.get("/api/items/info")
async def get_all_items_info(request: Request):
    storage_folder_to_user = getattr(request.state, "user_storage_folder", None)
    items = list_all_items(storage_folder_to_user)
    return {
        "items": [get_file_info(storage_folder_to_user, item) for item in items]
    }

@app.get("/login")
async def try_login(user_name: str, password: str):
    login_success, login_token, storage_id = authenticate(user_name, password)
    login_status = "success" if login_success else "fail"
    return {"status": login_status,
            "token": login_token,}

@app.get("/api/items/info/{item_names}")
async def get_specific_items_info(request: Request, item_names: str):
    storage_folder_to_user = getattr(request.state, "user_storage_folder", None)
    names = item_names.split(",")
    info = []

    for name in names:
        try:
            info.append(get_file_info(storage_folder_to_user, name))
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"{name} not found")

    return {"items": info}

@app.get("/api/file_content")
async def get_file_content(storage_folder, item_name: str):
    file_path = os.path.join(storage_folder, item_name)
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
async def delete_item(request: Request, item_names: str):
    storage_folder_to_user = getattr(request.state, "user_storage_folder", None)
    names = item_names.split(",")
    return delete_items(storage_folder_to_user, names)

@app.get("/download/{filename}")
async def download_file(request: Request, filename: str):
    storage_folder_to_user = getattr(request.state, "user_storage_folder", None)
    try:
        format_path = os.path.normpath(filename)
        file_path = os.path.join(storage_folder_to_user, format_path)

        if not os.path.isdir(file_path):
            return FileResponse(
                path=file_path,
                filename=filename,
                media_type="application/octet-stream"
            )
        else:
            archive_name = os.path.basename(format_path)
            archive_file_path = zip_file(storage_folder_to_user, format_path, ARCHIVE_EXTENTION, archive_name)
            return FileResponse(
                path=archive_file_path,
                filename=f"{archive_name}.{ARCHIVE_EXTENTION}",
                media_type="application/octet-stream"
            )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Item not found")
    except Exception as e:
        HTTPException(status_code=404, detail=f"Error getting file: {e}")

@app.get("/icon")
async def get_icon(request: Request, relative_path: str):
    try:
        path = Path(relative_path)

        # Folder detection
        if relative_path.endswith("/") or path.suffix == "":
            icon_path = ICONS_DIR / "folder.png"
        else:
            ext = path.suffix.lower().replace(".", "")
            icon_file = resolve_icon(ext)
            icon_path = ICONS_DIR / icon_file

        # Fallback safety
        if not icon_path.exists():
            icon_path = ICONS_DIR / "file.png"

        return FileResponse(icon_path, media_type="image/png")

    except Exception:
        raise HTTPException(status_code=500, detail="Icon error")

@app.post("/upload/files")
async def folder_upload(request: Request, file: UploadFile = File(...), relative_path: str = ""):
    storage_folder_to_user = getattr(request.state, "user_storage_folder", None)
    if storage_folder_to_user is None:
        raise HTTPException(status_code=400, detail="User storage folder not set")

    # Target folder
    if relative_path:
        extract_dir = os.path.join(storage_folder_to_user, relative_path)
    else:
        extract_dir = storage_folder_to_user

    os.makedirs(TEMPORARY_FOLDER, exist_ok=True)
    os.makedirs(extract_dir, exist_ok=True)

    temp_zip_path = os.path.join(TEMPORARY_FOLDER, f"{file.filename}.zip")

    file_upload_info = []
    successful_uploads = 0

    try:
        # Save uploaded file temporarily
        with open(temp_zip_path, "wb") as buffer:
            # noinspection PyTypeChecker
            shutil.copyfileobj(file.file, buffer)

        # Extract
        extract_zip(extract_dir, temp_zip_path)

        # List extracted files
        for folder_root, dirs, files in os.walk(extract_dir):
            for filename in files:
                file_path = os.path.join(folder_root, filename)
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
