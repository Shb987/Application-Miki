from pydantic import BaseModel
from typing import Dict, Optional, Any

class AdminLogin(BaseModel):
    username: str
    password: str

class AdminCreate(BaseModel):
    username: str
    password: str
    role_name: Optional[str] = "superadmin"

class Permission(BaseModel):
    create: bool = False
    read: bool = False
    update: bool = False
    delete: bool = False

class RoleCreate(BaseModel):
    role_name: str
    description: Optional[str] = ""
    permissions: Optional[Dict[str, Any]] = {}

class RoleUpdate(BaseModel):
    description: Optional[str] = None
    permissions: Optional[Dict[str, Any]] = None

class RoleInDB(BaseModel):
    id: str
    role_name: str
    description: Optional[str] = ""
    permissions: Dict[str, Any] = {}

