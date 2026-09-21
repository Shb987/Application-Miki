from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# 🚀 1. Space Explorer Models
# ─────────────────────────────────────────────────────────────────────────────

class SpaceExplorerBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Title / Planet Name")
    order: int = Field(1, ge=1, description="Order/number of planet (e.g. 3 for Earth)")
    category: str = Field("Planet", description="Category: Planet, Dwarf Planet, Moon, Star, Galaxy")
    short_description: Optional[str] = Field("", description="Short summary description")
    full_description: Optional[str] = Field("", description="Primary planet description")
    descriptions: Optional[List[str]] = Field(default_factory=list, description="Multiple descriptions list")
    image_url: Optional[str] = Field("", description="Planet Image URL")
    banner_image_url: Optional[str] = Field("", description="Cover Image URL")
    description_image_url: Optional[str] = Field("", description="Description Image URL")
    gallery_images: Optional[List[str]] = Field(default_factory=list, description="List of gallery image URLs")
    distance_from_sun: Optional[str] = Field(None, description="Distance from sun")
    diameter: Optional[str] = Field(None, description="Diameter")
    moons: Optional[int] = Field(None, description="Number of moons")
    gravity: Optional[str] = Field(None, description="Surface gravity")
    fun_fact: Optional[str] = Field(None, description="Interesting fun fact")
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
    description_image_url: Optional[str] = None
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


# ─────────────────────────────────────────────────────────────────────────────
# 🌊 2. Ocean Explorer Models
# ─────────────────────────────────────────────────────────────────────────────

class OceanExplorerBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Title / Ocean Feature or Creature Name")
    order: int = Field(1, ge=1, description="Order/display position")
    category: str = Field("Deep Sea", description="Category: Deep Sea, Coral Reef, Trench, Marine Life, Ocean Zone, Abyss")
    short_description: Optional[str] = Field("", description="Short summary description")
    full_description: Optional[str] = Field("", description="Primary ocean feature description")
    descriptions: Optional[List[str]] = Field(default_factory=list, description="Multiple description blocks list")
    image_url: Optional[str] = Field("", description="Primary Feature Image URL")
    banner_image_url: Optional[str] = Field("", description="Cover/Banner Image URL")
    description_image_url: Optional[str] = Field("", description="Description Image URL")
    gallery_images: Optional[List[str]] = Field(default_factory=list, description="List of gallery image URLs")
    depth: Optional[str] = Field(None, description="Depth measurement (e.g. 11,000m / 36,000ft)")
    location: Optional[str] = Field(None, description="Ocean / Region (e.g. Pacific Ocean, Mariana Trench)")
    temperature: Optional[str] = Field(None, description="Water temperature range (e.g. 1°C - 4°C)")
    species: Optional[str] = Field(None, description="Marine species / Key organisms")
    fun_fact: Optional[str] = Field(None, description="Interesting fun fact")
    is_active: bool = Field(True, description="Active status")

class OceanExplorerCreate(OceanExplorerBase):
    pass

class OceanExplorerUpdate(BaseModel):
    name: Optional[str] = None
    order: Optional[int] = None
    category: Optional[str] = None
    short_description: Optional[str] = None
    full_description: Optional[str] = None
    descriptions: Optional[List[str]] = None
    image_url: Optional[str] = None
    banner_image_url: Optional[str] = None
    description_image_url: Optional[str] = None
    gallery_images: Optional[List[str]] = None
    depth: Optional[str] = None
    location: Optional[str] = None
    temperature: Optional[str] = None
    species: Optional[str] = None
    fun_fact: Optional[str] = None
    is_active: Optional[bool] = None

class OceanExplorerResponse(OceanExplorerBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}


# ─────────────────────────────────────────────────────────────────────────────
# 🌿 3. Plant Explorer Models
# ─────────────────────────────────────────────────────────────────────────────

class PlantExplorerBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Title / Plant Name")
    order: int = Field(1, ge=1, description="Order/display position")
    category: str = Field("Rainforest", description="Category: Rainforest, Carnivorous, Medicinal, Flowering, Tree, Succulent, Aquatic")
    short_description: Optional[str] = Field("", description="Short summary description")
    full_description: Optional[str] = Field("", description="Primary plant description")
    descriptions: Optional[List[str]] = Field(default_factory=list, description="Multiple description blocks list")
    image_url: Optional[str] = Field("", description="Primary Plant Image URL")
    banner_image_url: Optional[str] = Field("", description="Cover/Banner Image URL")
    description_image_url: Optional[str] = Field("", description="Description Image URL")
    gallery_images: Optional[List[str]] = Field(default_factory=list, description="List of gallery image URLs")
    habitat: Optional[str] = Field(None, description="Natural Habitat / Ecosystem (e.g. Tropical Rainforest)")
    scientific_name: Optional[str] = Field(None, description="Botanical / Scientific Name")
    family: Optional[str] = Field(None, description="Plant Family (e.g. Orchidaceae)")
    climate: Optional[str] = Field(None, description="Climate & Growth requirements")
    fun_fact: Optional[str] = Field(None, description="Interesting fun fact")
    is_active: bool = Field(True, description="Active status")

class PlantExplorerCreate(PlantExplorerBase):
    pass

class PlantExplorerUpdate(BaseModel):
    name: Optional[str] = None
    order: Optional[int] = None
    category: Optional[str] = None
    short_description: Optional[str] = None
    full_description: Optional[str] = None
    descriptions: Optional[List[str]] = None
    image_url: Optional[str] = None
    banner_image_url: Optional[str] = None
    description_image_url: Optional[str] = None
    gallery_images: Optional[List[str]] = None
    habitat: Optional[str] = None
    scientific_name: Optional[str] = None
    family: Optional[str] = None
    climate: Optional[str] = None
    fun_fact: Optional[str] = None
    is_active: Optional[bool] = None

class PlantExplorerResponse(PlantExplorerBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}
