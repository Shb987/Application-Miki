from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, Form, File, UploadFile
from typing import List, Dict, Optional
import os
import uuid
import shutil
from bson import ObjectId
from datetime import datetime, timezone
from core.database import db
from utils.user_auth import get_current_user
from models.chat_models import GroupCreate, GroupResponse, ChatMessage

UPLOAD_DIR = "uploads/group_images"
os.makedirs(UPLOAD_DIR, exist_ok=True)

router = APIRouter(prefix="/chat", tags=["Group Chat"])

# ------------------------------------------------------------------------
# 🔌 WebSocket Connection Manager
# ------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        # active_connections[group_id] = { student_id: websocket }
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, group_id: str, student_id: str):
        await websocket.accept()
        if group_id not in self.active_connections:
            self.active_connections[group_id] = {}
        self.active_connections[group_id][student_id] = websocket

    def disconnect(self, group_id: str, student_id: str):
        if group_id in self.active_connections:
            if student_id in self.active_connections[group_id]:
                del self.active_connections[group_id][student_id]
            if not self.active_connections[group_id]:
                del self.active_connections[group_id]

    async def broadcast_to_group(self, group_id: str, message: dict):
        if group_id in self.active_connections:
            for connection in self.active_connections[group_id].values():
                await connection.send_json(message)

manager = ConnectionManager()

# ------------------------------------------------------------------------
# 🛠️ Helpers
# ------------------------------------------------------------------------
def serialize_mongo(doc):
    if not doc: return doc
    if isinstance(doc, list):
        return [serialize_mongo(d) for d in doc]
    doc["id"] = str(doc.pop("_id"))
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
        if isinstance(v, ObjectId):
            doc[k] = str(v)
    return doc

# ------------------------------------------------------------------------
# 🚀 Group Management
# ------------------------------------------------------------------------

@router.get("/classmates")
async def get_classmates(student_id: str, current_user: dict = Depends(get_current_user)):
    """Fetch students in the same class as the current user"""
    # Find the current student's class
    try:
        s_oid = ObjectId(student_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    me = await db.students.find_one({"_id": s_oid})
    if not me:
        raise HTTPException(status_code=404, detail="Student record not found")

    my_class = me.get("student_class")
    
    # Find others in the same class
    cursor = db.students.find({"student_class": my_class, "_id": {"$ne": s_oid}})
    classmates = await cursor.to_list(length=100)
    
    return [serialize_mongo(c) for c in classmates]

@router.post("/groups")
async def create_group(
    name: str = Form(...),
    student_id: str = Form(...),
    member_ids: str = Form(...), # Expecting comma-separated IDs
    group_image: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user)
):
    """Create a new chat group"""
    # Parse member IDs
    id_list = [id.strip() for id in member_ids.split(",") if id.strip()]
    if student_id not in id_list:
        id_list.append(student_id)

    # Fetch creator details for class info
    creator = await db.students.find_one({"_id": ObjectId(student_id)})
    if not creator:
        raise HTTPException(status_code=404, detail="Creator student record not found")

    # Handle image upload
    image_url = None
    if group_image:
        file_extension = os.path.splitext(group_image.filename)[1]
        file_name = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(UPLOAD_DIR, file_name)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(group_image.file, buffer)
        
        image_url = f"uploads/group_images/{file_name}"

    group_doc = {
        "name": name,
        "class_name": creator.get("student_class"),
        "member_ids": id_list,
        "image_url": image_url,
        "created_by": student_id,
        "created_at": datetime.now(timezone.utc)
    }

    result = await db.chat_groups.insert_one(group_doc)
    return {"message": "Group created", "group_id": str(result.inserted_id)}

@router.get("/my-groups")
async def get_my_groups(student_id: str, current_user: dict = Depends(get_current_user)):
    """List all groups the student belongs to"""
    cursor = db.chat_groups.find({"member_ids": student_id})
    groups = await cursor.to_list(length=100)
    return [serialize_mongo(g) for g in groups]

@router.get("/history/{group_id}")
async def get_chat_history(group_id: str, student_id: str, current_user: dict = Depends(get_current_user)):
    """Fetch message history for a group"""
    # Check if student is a member
    group = await db.chat_groups.find_one({"_id": ObjectId(group_id), "member_ids": student_id})
    if not group:
        raise HTTPException(status_code=403, detail="Not a member of this group")

    cursor = db.chat_messages.find({"group_id": group_id}).sort("timestamp", 1)
    messages = await cursor.to_list(length=200)
    return [serialize_mongo(m) for m in messages]

# ------------------------------------------------------------------------
# 💬 Real-Time Chat (WebSocket)
# ------------------------------------------------------------------------

@router.websocket("/ws/{group_id}/{student_id}")
async def websocket_endpoint(websocket: WebSocket, group_id: str, student_id: str):
    await websocket.accept() # Accept immediately to complete the handshake
    print('check1')
    try:
        print('check2')

        # Verify membership (basic check)
        group = await db.chat_groups.find_one({
            "_id": ObjectId(group_id), 
            "member_ids": student_id
        })
        print('check3')
        if not group:
            print('check4')
            await websocket.close(code=4003) # Forbidden
            return

        # Fetch sender name
        student = await db.students.find_one({"_id": ObjectId(student_id)})
        sender_name = student.get("student_name", "Unknown") if student else "Unknown"

        # Register in connection manager (already accepted, so we just add to list)
        if group_id not in manager.active_connections:
            manager.active_connections[group_id] = {}
        manager.active_connections[group_id][student_id] = websocket
        
    except Exception as e:
        print(f"WebSocket Validation Error: {e}")
        await websocket.close(code=4000) # Internal Error/Invalid ID
        return
    
    try:
        while True:
            # Receive data from the client
            data = await websocket.receive_text()
            
            # Prepare message object
            msg_doc = {
                "group_id": group_id,
                "sender_id": student_id,
                "sender_name": sender_name,
                "message": data,
                "timestamp": datetime.now(timezone.utc)
            }
            
            # Save to database
            await db.chat_messages.insert_one(msg_doc)
            
            # Broadcast to everyone in the group
            await manager.broadcast_to_group(group_id, serialize_mongo(msg_doc))
            
    except WebSocketDisconnect:
        manager.disconnect(group_id, student_id)
