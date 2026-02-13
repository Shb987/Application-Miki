# models/notification.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class Notification(BaseModel):
    notification_id: str
    user_id: str
    title: str
    message: str
    type: str
    is_read: bool = False
    created_at: datetime
