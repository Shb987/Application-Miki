from pydantic import BaseModel
from typing import Dict, Optional, Any

class AdminLogin(BaseModel):
    username: str
    password: str

class AdminCreate(BaseModel):
    username: str
    password: str
    full_name: str
    email: str
    phone_number: str
    address: str
    role_name: Optional[str] = "superadmin"


class AdminUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    address: Optional[str] = None
    role_name: Optional[str] = None
    password: Optional[str] = None

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
