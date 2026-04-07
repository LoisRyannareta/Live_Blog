from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import datetime
import uuid

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database in-memory
db_users = {}
db_blogs = []
user_id_counter = 1
blog_id_counter = 1

# --- Schemas (sama seperti sebelumnya) ---
class MahasiswaRegister(BaseModel):
    nama: str
    nim: str
    kelas: str

class BlogCreate(BaseModel):
    judul: str
    isi: str

class BlogUpdate(BaseModel):
    judul: Optional[str] = None
    isi: Optional[str] = None

# --- Connection Manager (sama) ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

# --- AUTH DEPENDENCY (DIPERBAIKI) ---
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    if token not in db_users:
        raise HTTPException(status_code=401, detail="User not found or token expired")
    return db_users[token]

# --- ENDPOINTS (sama, yang berubah hanya auth dependency) ---

@app.get("/")
def root():
    return {"message": "Live Blog API is running"}

@app.post("/api/register")
def register(user: MahasiswaRegister):
    global user_id_counter
    access_token = str(uuid.uuid4())
    user_data = {
        "id": user_id_counter,
        "nama": user.nama,
        "nim": user.nim,
        "kelas": user.kelas,
        "created_at": datetime.datetime.now().isoformat()
    }
    db_users[access_token] = user_data
    user_id_counter += 1
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "mahasiswa": user_data
    }

@app.get("/api/blogs")
def get_all_blogs():
    return db_blogs

@app.post("/api/blogs")
async def create_blog(blog: BlogCreate, user=Depends(get_current_user)):
    global blog_id_counter
    now = datetime.datetime.now().isoformat()
    new_blog = {
        "id": blog_id_counter,
        "judul": blog.judul,
        "isi": blog.isi,
        "author_id": user["id"],
        "author_nama": user["nama"],
        "author_nim": user["nim"],
        "author_kelas": user["kelas"],
        "created_at": now,
        "updated_at": now
    }
    db_blogs.append(new_blog)
    blog_id_counter += 1
    await manager.broadcast({"action": "CREATE", "data": new_blog})
    return new_blog

@app.put("/api/blogs/{blog_id}")
async def update_blog(blog_id: int, update_data: BlogUpdate, user=Depends(get_current_user)):
    for blog in db_blogs:
        if blog["id"] == blog_id:
            if blog["author_id"] != user["id"]:
                raise HTTPException(status_code=403, detail="Not authorized to edit this blog")
            if update_data.judul:
                blog["judul"] = update_data.judul
            if update_data.isi:
                blog["isi"] = update_data.isi
            blog["updated_at"] = datetime.datetime.now().isoformat()
            await manager.broadcast({"action": "UPDATE", "data": blog})
            return blog
    raise HTTPException(status_code=404, detail="Blog not found")

@app.delete("/api/blogs/{blog_id}")
async def delete_blog(blog_id: int, user=Depends(get_current_user)):
    global db_blogs
    for index, blog in enumerate(db_blogs):
        if blog["id"] == blog_id:
            if blog["author_id"] != user["id"]:
                raise HTTPException(status_code=403, detail="Not authorized to delete this blog")
            db_blogs.pop(index)
            await manager.broadcast({"action": "DELETE", "blog_id": blog_id})
            return {"message": f"Blog {blog_id} deleted"}
    raise HTTPException(status_code=404, detail="Blog not found")

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

