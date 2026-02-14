from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, Form, File, UploadFile
from typing import List, Dict, Optional
import os
import uuid
import shutil
from bson import ObjectId
from datetime import datetime, timezone
from app.core.database import db
from app.utils.user_auth import get_current_user
from app.models.chat_models import GroupCreate, GroupResponse, ChatMessage

UPLOAD_DIR = "app/static/uploads/group_images"
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

@router.post("/groups/{group_id}/add-member")
async def add_member(
    group_id: str,
    member_ids: str = Form(...), # Expecting comma-separated IDs
    student_id: str = Query(...), # The requester
    current_user: dict = Depends(get_current_user)
):
    """Add students to the group (Only by Creator)"""
    # 1. Parse member IDs
    new_member_list = [id.strip() for id in member_ids.split(",") if id.strip()]
    if not new_member_list:
        raise HTTPException(status_code=400, detail="No member IDs provided")

    try:
        g_oid = ObjectId(group_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid group_id format")

    # 2. Fetch group & Verify creator
    group = await db.chat_groups.find_one({"_id": g_oid})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    if group.get("created_by") != student_id:
        raise HTTPException(status_code=403, detail="Only the group creator can add members")

    # 3. Add to member_ids using $each
    await db.chat_groups.update_one(
        {"_id": g_oid},
        {"$addToSet": {"member_ids": {"$each": new_member_list}}}
    )

    # 4. Broadcast system message
    creator = await db.students.find_one({"_id": ObjectId(student_id)})
    c_name = creator.get("student_name", "Admin") if creator else "Admin"
    
    # Fetch names for all new members
    new_names = []
    for mid in new_member_list:
        try:
            m_data = await db.students.find_one({"_id": ObjectId(mid)})
            if m_data:
                new_names.append(m_data.get("student_name", "New Member"))
            else:
                new_names.append(mid)
        except:
            new_names.append(mid)

    names_str = ", ".join(new_names)
    
    system_msg = {
        "group_id": group_id,
        "sender_id": "system",
        "sender_name": "System",
        "message": f"{c_name} added {names_str} to the group",
        "timestamp": datetime.now(timezone.utc)
    }
    await db.chat_messages.insert_one(system_msg)
    await manager.broadcast_to_group(group_id, serialize_mongo(system_msg))

    return {"message": f"Successfully added members: {names_str}"}

@router.delete("/groups/{group_id}/remove-member/{member_to_remove}")
async def remove_member(
    group_id: str,
    member_to_remove: str,
    student_id: str = Query(...), # The requester
    current_user: dict = Depends(get_current_user)
):
    """Remove a student from the group (Only by Creator)"""
    try:
        g_oid = ObjectId(group_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid group_id format")

    # 1. Fetch group & Verify creator
    group = await db.chat_groups.find_one({"_id": g_oid})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    if group.get("created_by") != student_id:
        raise HTTPException(status_code=403, detail="Only the group creator can remove members")

    # Prevent creator from removing themselves (optional, but safer)
    if member_to_remove == group.get("created_by"):
        raise HTTPException(status_code=400, detail="Cannot remove the creator from the group")

    # 2. Remove from member_ids
    await db.chat_groups.update_one(
        {"_id": g_oid},
        {"$pull": {"member_ids": member_to_remove}}
    )

    # 3. Broadcast system message
    creator = await db.students.find_one({"_id": ObjectId(student_id)})
    removed_member = await db.students.find_one({"_id": ObjectId(member_to_remove)})
    
    c_name = creator.get("student_name", "Admin") if creator else "Admin"
    r_name = removed_member.get("student_name", "Member") if removed_member else "Member"

    system_msg = {
        "group_id": group_id,
        "sender_id": "system",
        "sender_name": "System",
        "message": f"{c_name} removed {r_name} from the group",
        "timestamp": datetime.now(timezone.utc)
    }
    await db.chat_messages.insert_one(system_msg)
    await manager.broadcast_to_group(group_id, serialize_mongo(system_msg))

    # 4. Disconnect if active (WebSocket)
    manager.disconnect(group_id, member_to_remove)

    return {"message": f"Student {member_to_remove} removed successfully"}

@router.post("/groups/{group_id}/update")
async def update_group(
    group_id: str,
    name: Optional[str] = Form(None),
    student_id: str = Form(...), # The requester
    group_image: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user)
):
    """Update group details (Name and Image) - Only by Creator"""
    try:
        g_oid = ObjectId(group_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid group_id format")

    # 1. Fetch group & Verify creator
    group = await db.chat_groups.find_one({"_id": g_oid})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    if group.get("created_by") != student_id:
        raise HTTPException(status_code=403, detail="Only the group creator can update group details")

    update_data = {}
    changes = []

    # 2. Update Name
    if name and name != group.get("name"):
        update_data["name"] = name
        changes.append(f"name to '{name}'")

    # 3. Update Image
    if group_image:
        file_extension = os.path.splitext(group_image.filename)[1]
        file_name = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(UPLOAD_DIR, file_name)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(group_image.file, buffer)
        
        new_image_url = f"uploads/group_images/{file_name}"
        update_data["image_url"] = new_image_url
        changes.append("group image")
        
        # Optional: Delete old image if it exists
        old_image = group.get("image_url")
        if old_image:
            old_path = os.path.join("app/static", old_image)
            if os.path.exists(old_path):
                try: os.remove(old_path)
                except: pass

    if not update_data:
        return {"message": "No changes provided"}

    # 4. Apply Updates
    await db.chat_groups.update_one({"_id": g_oid}, {"$set": update_data})

    # 5. Broadcast system message
    creator = await db.students.find_one({"_id": ObjectId(student_id)})
    c_name = creator.get("student_name", "Admin") if creator else "Admin"
    
    changes_str = " and ".join(changes)
    system_msg = {
        "group_id": group_id,
        "sender_id": "system",
        "sender_name": "System",
        "message": f"{c_name} updated the {changes_str}",
        "timestamp": datetime.now(timezone.utc)
    }
    await db.chat_messages.insert_one(system_msg)
    await manager.broadcast_to_group(group_id, serialize_mongo(system_msg))

    return {"message": "Group updated successfully", "updated_fields": list(update_data.keys())}

@router.post("/groups/{group_id}/leave")
async def leave_group(
    group_id: str,
    student_id: str = Query(...), # The student who wants to leave
    current_user: dict = Depends(get_current_user)
):
    """Allow a student to leave the group (Creator cannot leave)"""
    try:
        g_oid = ObjectId(group_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid group_id format")

    # 1. Fetch group
    group = await db.chat_groups.find_one({"_id": g_oid})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # 2. Prevent creator from leaving
    if group.get("created_by") == student_id:
        raise HTTPException(status_code=400, detail="Group creator cannot leave the group")

    # 3. Verify membership
    if student_id not in group.get("member_ids", []):
        raise HTTPException(status_code=404, detail="Student is not a member of this group")

    # 4. Remove from member_ids
    await db.chat_groups.update_one(
        {"_id": g_oid},
        {"$pull": {"member_ids": student_id}}
    )

    # 5. Broadcast system message
    student = await db.students.find_one({"_id": ObjectId(student_id)})
    s_name = student.get("student_name", "A student") if student else "A student"

    system_msg = {
        "group_id": group_id,
        "sender_id": "system",
        "sender_name": "System",
        "message": f"{s_name} has left the group",
        "timestamp": datetime.now(timezone.utc)
    }
    await db.chat_messages.insert_one(system_msg)
    await manager.broadcast_to_group(group_id, serialize_mongo(system_msg))

    # 6. Disconnect if active (WebSocket)
    manager.disconnect(group_id, student_id)

    return {"message": "You have left the group successfully"}

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
