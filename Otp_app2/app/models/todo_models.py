from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class TodoCreate(BaseModel):
    title: str = Field(..., description="Title of the to-do item")
    description: Optional[str] = Field(None, description="Detailed description of the task")
    category: Optional[str] = Field("General", description="Category/tag e.g. Homework, Exam, Personal")
    due_date: Optional[str] = Field(None, description="Due date string in ISO format or YYYY-MM-DD")
    is_important: Optional[bool] = Field(False, description="Boolean flag marking priority/importance")
    status: Optional[str] = Field("pending", description="Status of task: 'pending' or 'completed'")

class TodoUpdate(BaseModel):
    title: Optional[str] = Field(None, description="Updated title")
    description: Optional[str] = Field(None, description="Updated description")
    category: Optional[str] = Field(None, description="Updated category")
    due_date: Optional[str] = Field(None, description="Updated due date")
    is_important: Optional[bool] = Field(None, description="Boolean flag marking importance")
    is_completed: Optional[bool] = Field(None, description="Boolean flag marking completion")
    status: Optional[str] = Field(None, description="Updated status: 'pending' or 'completed'")

class TodoStatusUpdate(BaseModel):
    status: Optional[str] = Field(None, description="Status update: 'pending' or 'completed'")
    is_completed: Optional[bool] = Field(None, description="Boolean completion status")

class TodoResponse(BaseModel):
    id: str
    student_id: str
    title: str
    description: Optional[str] = None
    status: str = "pending"
    is_completed: bool = False
    is_important: bool = False
    category: Optional[str] = "General"
    due_date: Optional[str] = None
    image_urls: List[str] = []
    created_at: str
    updated_at: str
