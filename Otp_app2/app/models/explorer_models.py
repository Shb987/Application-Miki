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
    category: str = Field("Ocean", description="Category: Ocean")
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
    category: str = Field("Trees", description="Category: Trees, Shrubs, Herbs, Grasses, Cacti & Succulents, Flowering Plants, Aquatic Plants, Climbers & Creepers, Conifers, Ferns, Mosses & Other Spore Plants")
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


# ─────────────────────────────────────────────────────────────────────────────
# 🇮🇳 4. Indian Explorer Models
# ─────────────────────────────────────────────────────────────────────────────

class IndianExplorerBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="State / Union Territory Name (e.g. Kerala)")
    order: int = Field(1, ge=1, description="Order/display position")
    category: str = Field("State", description="Category: State")
    short_description: Optional[str] = Field("", description="Short summary description")
    full_description: Optional[str] = Field("", description="Primary state description")
    descriptions: Optional[List[str]] = Field(default_factory=list, description="Multiple description blocks list")
    image_url: Optional[str] = Field("", description="Primary State Emblem/Feature Image URL")
    banner_image_url: Optional[str] = Field("", description="Cover/Banner Image URL")
    description_image_url: Optional[str] = Field("", description="Description Image URL")
    gallery_images: Optional[List[str]] = Field(default_factory=list, description="List of gallery image URLs")

    # 📍 Quick Facts
    capital: Optional[str] = Field(None, description="Capital city")
    area: Optional[str] = Field(None, description="Total area")
    population: Optional[str] = Field(None, description="Population")
    official_languages: Optional[str] = Field(None, description="Official Language(s)")
    formation: Optional[str] = Field(None, description="Formation Date / Year")

    # 🎭 Culture
    traditional_dances: Optional[str] = Field(None, description="Traditional Dances")
    traditional_music: Optional[str] = Field(None, description="Traditional Music")
    festivals: Optional[str] = Field(None, description="Major Festivals")
    traditional_clothing: Optional[str] = Field(None, description="Traditional Clothing")
    culture_arts_crafts: Optional[str] = Field(None, description="Cultural Arts & Crafts")
    culture_food: Optional[str] = Field(None, description="Cultural Food")
    traditions_customs: Optional[str] = Field(None, description="Traditions & Customs")

    # 🏛️ Heritage
    historical_monuments: Optional[str] = Field(None, description="Historical Monuments")
    temples_churches_mosques: Optional[str] = Field(None, description="Temples / Churches / Mosques")
    forts: Optional[str] = Field(None, description="Forts & Palaces")
    unesco_heritage: Optional[str] = Field(None, description="UNESCO Heritage Sites")

    # 🗺️ Geography
    major_rivers: Optional[str] = Field(None, description="Major Rivers")
    mountains: Optional[str] = Field(None, description="Mountains & Peaks")
    beaches: Optional[str] = Field(None, description="Beaches & Coastal regions")
    forests: Optional[str] = Field(None, description="Forests & Vegetation")
    climate: Optional[str] = Field(None, description="Climate & Weather")

    # 🐘 Wildlife
    state_animal: Optional[str] = Field(None, description="State Animal")
    state_bird: Optional[str] = Field(None, description="State Bird")
    state_tree: Optional[str] = Field(None, description="State Tree")
    state_flower: Optional[str] = Field(None, description="State Flower")
    national_parks_sanctuaries: Optional[str] = Field(None, description="National Parks / Sanctuaries")

    # 🍛 Food
    famous_dishes: Optional[str] = Field(None, description="Famous Dishes")
    traditional_cuisine: Optional[str] = Field(None, description="Traditional Cuisine")
    famous_ingredients: Optional[str] = Field(None, description="Famous Spices / Ingredients")

    # 👕 Traditional Lifestyle
    traditional_dress: Optional[str] = Field(None, description="Traditional Dress")
    occupations: Optional[str] = Field(None, description="Main Occupations")
    local_communities: Optional[str] = Field(None, description="Local Communities & Tribes")

    # 🎨 🏆 📍 Highlights
    famous_arts_crafts: Optional[str] = Field(None, description="Famous Arts & Crafts")
    famous_personalities: Optional[str] = Field(None, description="Famous Personalities")
    famous_places: Optional[str] = Field(None, description="Famous Tourist Places")

    fun_fact: Optional[str] = Field(None, description="Interesting fun fact")
    is_active: bool = Field(True, description="Active status")


class IndianExplorerCreate(IndianExplorerBase):
    pass


class IndianExplorerUpdate(BaseModel):
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

    capital: Optional[str] = None
    area: Optional[str] = None
    population: Optional[str] = None
    official_languages: Optional[str] = None
    formation: Optional[str] = None

    traditional_dances: Optional[str] = None
    traditional_music: Optional[str] = None
    festivals: Optional[str] = None
    traditional_clothing: Optional[str] = None
    culture_arts_crafts: Optional[str] = None
    culture_food: Optional[str] = None
    traditions_customs: Optional[str] = None

    historical_monuments: Optional[str] = None
    temples_churches_mosques: Optional[str] = None
    forts: Optional[str] = None
    unesco_heritage: Optional[str] = None

    major_rivers: Optional[str] = None
    mountains: Optional[str] = None
    beaches: Optional[str] = None
    forests: Optional[str] = None
    climate: Optional[str] = None

    state_animal: Optional[str] = None
    state_bird: Optional[str] = None
    state_tree: Optional[str] = None
    state_flower: Optional[str] = None
    national_parks_sanctuaries: Optional[str] = None

    famous_dishes: Optional[str] = None
    traditional_cuisine: Optional[str] = None
    famous_ingredients: Optional[str] = None

    traditional_dress: Optional[str] = None
    occupations: Optional[str] = None
    local_communities: Optional[str] = None

    famous_arts_crafts: Optional[str] = None
    famous_personalities: Optional[str] = None
    famous_places: Optional[str] = None

    fun_fact: Optional[str] = None
    is_active: Optional[bool] = None


class IndianExplorerResponse(IndianExplorerBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}

