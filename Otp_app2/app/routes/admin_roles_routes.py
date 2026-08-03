from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from bson import ObjectId
from app.core.database import db
from app.models.admin_models import RoleCreate, RoleUpdate
from app.utils.admin_auth import get_current_admin

router = APIRouter(tags=["Admin Roles"])


async def log_admin_activity(username: str, role: str, action: str, details: str, status: str = "success"):
    await db.admin_activity_logs.insert_one({
        "username": username,
        "role": role,
        "action": action,
        "status": status,
        "details": details,
        "timestamp": datetime.now(timezone.utc),
    })

# Only superadmins should manage roles.
def require_superadmin(current_admin: dict = Depends(get_current_admin)):
    if current_admin.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return current_admin

@router.post("/roles")
async def create_role(role_data: RoleCreate, admin: dict = Depends(require_superadmin)):
    try:
        existing = await db.roles.find_one({"role_name": role_data.role_name})
        if existing:
            raise HTTPException(status_code=400, detail="Role already exists")

        role_dict = role_data.model_dump()
        result = await db.roles.insert_one(role_dict)
        await log_admin_activity(
            admin["sub"],
            admin["role"],
            "create_role",
            f"Created role '{role_data.role_name}'",
        )
        return {"message": "Role created", "id": str(result.inserted_id)}
    except HTTPException as exc:
        await log_admin_activity(
            admin["sub"],
            admin["role"],
            "create_role",
            f"Failed to create role '{role_data.role_name}': {exc.detail}",
            status="failed",
        )
        raise
    except Exception as exc:
        await log_admin_activity(
            admin["sub"],
            admin["role"],
            "create_role",
            f"Failed to create role '{role_data.role_name}': {exc}",
            status="failed",
        )
        raise

@router.get("/roles")
async def list_roles(admin: dict = Depends(require_superadmin)):
    cursor = db.roles.find()
    roles = await cursor.to_list(length=100)
    for r in roles:
        r["_id"] = str(r["_id"])
    return roles

@router.put("/roles/{role_name}/permissions")
async def update_role_permissions(role_name: str, role_update: RoleUpdate, admin: dict = Depends(require_superadmin)):
    try:
        existing = await db.roles.find_one({"role_name": role_name})
        if not existing:
            raise HTTPException(status_code=404, detail="Role not found")

        update_data = role_update.model_dump(exclude_none=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No data to update")

        await db.roles.update_one({"role_name": role_name}, {"$set": update_data})
        await log_admin_activity(
            admin["sub"],
            admin["role"],
            "update_role",
            f"Updated role '{role_name}' permissions and details",
        )
        return {"message": "Role updated successfully"}
    except HTTPException as exc:
        await log_admin_activity(
            admin["sub"],
            admin["role"],
            "update_role",
            f"Failed to update role '{role_name}': {exc.detail}",
            status="failed",
        )
        raise
    except Exception as exc:
        await log_admin_activity(
            admin["sub"],
            admin["role"],
            "update_role",
            f"Failed to update role '{role_name}': {exc}",
            status="failed",
        )
        raise

@router.delete("/roles/{role_name}")
async def delete_role(role_name: str, admin: dict = Depends(require_superadmin)):
    try:
        existing = await db.roles.find_one({"role_name": role_name})
        if not existing:
            raise HTTPException(status_code=404, detail="Role not found")

        # Prevent deletion if admins use it
        admins_using = await db.admins.find_one({"role_name": role_name})
        if admins_using:
            raise HTTPException(status_code=400, detail="Cannot delete role currently assigned to admins")

        await db.roles.delete_one({"role_name": role_name})
        await log_admin_activity(
            admin["sub"],
            admin["role"],
            "delete_role",
            f"Deleted role '{role_name}'",
        )
        return {"message": "Role deleted"}
    except HTTPException as exc:
        await log_admin_activity(
            admin["sub"],
            admin["role"],
            "delete_role",
            f"Failed to delete role '{role_name}': {exc.detail}",
            status="failed",
        )
        raise
    except Exception as exc:
        await log_admin_activity(
            admin["sub"],
            admin["role"],
            "delete_role",
            f"Failed to delete role '{role_name}': {exc}",
            status="failed",
        )
        raise
