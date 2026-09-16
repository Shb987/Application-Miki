from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class SpaceExplorerBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Title / Planet Name")
    order: int = Field(1, ge=1, description="Order/number of planet (e.g. 3 for Earth)")
    category: str = Field("Planet", description="Category: Planet, Dwarf Planet, Moon, Star, Galaxy")
    short_description: Optional[str] = Field("", description="Short summary description")
    full_description: Optional[str] = Field("", description="Primary planet description")
    descriptions: Optional[List[str]] = Field(default_factory=list, description="Multiple descriptions list (Description 1, Description 2, etc.)")
    image_url: Optional[str] = Field("", description="Planet Image URL")
    banner_image_url: Optional[str] = Field("", description="Cover Image URL")
    gallery_images: Optional[List[str]] = Field(default_factory=list, description="List of gallery image URLs")
    distance_from_sun: Optional[str] = Field(None, description="Distance from sun (Optional)")
    diameter: Optional[str] = Field(None, description="Diameter (Optional)")
    moons: Optional[int] = Field(None, description="Number of moons (Optional)")
    gravity: Optional[str] = Field(None, description="Surface gravity (Optional)")
    fun_fact: Optional[str] = Field(None, description="Interesting fun fact (Optional)")
    is_active: bool = Field(True, description="Active status")

class SpaceExplorerCreate(SpaceExplorerBase):
    pass

class SpaceExplorerUpdate(BaseModel):
    name: Optional[str] = None
    order: Optional[int] = None
    category: Optional[str] = None
    short_description: Optional[str] = None
    full_description: Optional[str] = None
    descriptions: Optional[List[str]] = None
    image_url: Optional[str] = None
    banner_image_url: Optional[str] = None
    gallery_images: Optional[List[str]] = None
    distance_from_sun: Optional[str] = None
    diameter: Optional[str] = None
    moons: Optional[int] = None
    gravity: Optional[str] = None
    fun_fact: Optional[str] = None
    is_active: Optional[bool] = None

class SpaceExplorerResponse(SpaceExplorerBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}
