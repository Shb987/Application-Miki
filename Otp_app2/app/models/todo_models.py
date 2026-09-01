from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class TodoCreate(BaseModel):
    title: str = Field(..., description="Title of the to-do item")
    description: Optional[str] = Field(None, description="Detailed description of the task")
    category: Optional[str] = Field("general", description="Category/tag e.g. homework, exam, personal")
    due_date: Optional[str] = Field(None, description="Due date string in ISO format or YYYY-MM-DD")
    is_important: Optional[bool] = Field(False, description="Boolean flag marking priority/importance")
    status: Optional[str] = Field("pending", description="Status of task: 'pending' or 'completed'")
    reminder_time: Optional[str] = Field(None, description="Reminder ISO datetime string e.g. 2026-08-22T18:00:00+05:30")
    is_reminder_enabled: Optional[bool] = Field(None, description="Boolean flag enabling OneSignal push reminder")
    images: Optional[List[str]] = Field(default=[], description="Optional array of images/image URLs")
    image_urls: Optional[List[str]] = Field(default=[], description="Optional array of image URLs")

class TodoUpdate(BaseModel):
    title: Optional[str] = Field(None, description="Updated title")
    description: Optional[str] = Field(None, description="Updated description")
    category: Optional[str] = Field(None, description="Updated category")
    due_date: Optional[str] = Field(None, description="Updated due date")
    is_important: Optional[bool] = Field(None, description="Boolean flag marking importance")
    is_completed: Optional[bool] = Field(None, description="Boolean flag marking completion")
    status: Optional[str] = Field(None, description="Updated status: 'pending' or 'completed'")
    reminder_time: Optional[str] = Field(None, description="Updated reminder datetime string")
    is_reminder_enabled: Optional[bool] = Field(None, description="Updated reminder enabled flag")
    images: Optional[List[str]] = Field(None, description="Optional updated images list")
    image_urls: Optional[List[str]] = Field(None, description="Optional updated image URLs list")
    delete_image_urls: Optional[List[str]] = Field(None, description="Optional image URLs to delete")

class TodoStatusUpdate(BaseModel):
    status: Optional[str] = Field(None, description="Status update: 'pending' or 'completed'")
    is_completed: Optional[bool] = Field(None, description="Boolean completion status")

class TodoResponse(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = "pending"
    is_completed: bool = False
    is_important: bool = False
    due_date: Optional[str] = None
    reminder_time: Optional[str] = None
    is_reminder_enabled: bool = False
    reminder_sent: bool = False
    image_urls: Optional[List[str]] = Field(default=[], description="List of image URLs attached to the to-do")
    created_at: str
    updated_at: str

