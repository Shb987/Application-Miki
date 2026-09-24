from pydantic import BaseModel, Field
from typing import Optional, List, Any, Union, Dict
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# 🚀 1. Space Explorer Models
# ─────────────────────────────────────────────────────────────────────────────

class SpaceExplorerBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Title / Planet Name")
    order: int = Field(1, ge=1, description="Order/number of planet (e.g. 3 for Earth)")
    category: str = Field("Planet", description="Category: Planet")
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

class CultureAndHeritage(BaseModel):
    culture_image_url: Optional[str] = ""
    traditional_dances: Optional[str] = ""
    traditional_dances_image_url: Optional[str] = ""
    traditional_music: Optional[str] = ""
    traditional_music_image_url: Optional[str] = ""
    festivals: Optional[str] = ""
    festivals_image_url: Optional[str] = ""
    traditional_clothing: Optional[str] = ""
    traditional_clothing_image_url: Optional[str] = ""
    culture_arts_crafts: Optional[str] = ""
    culture_arts_crafts_image_url: Optional[str] = ""
    culture_food: Optional[str] = ""
    culture_food_image_url: Optional[str] = ""
    traditions_customs: Optional[str] = ""
    traditions_customs_image_url: Optional[str] = ""

class HeritageAndMonuments(BaseModel):
    heritage_image_url: Optional[str] = ""
    historical_monuments: Optional[str] = ""
    historical_monuments_image_url: Optional[str] = ""
    temples_churches_mosques: Optional[str] = ""
    temples_churches_mosques_image_url: Optional[str] = ""
    forts: Optional[str] = ""
    forts_image_url: Optional[str] = ""
    unesco_heritage: Optional[str] = ""
    unesco_heritage_image_url: Optional[str] = ""

class GeographySection(BaseModel):
    geography_image_url: Optional[str] = ""
    major_rivers: Optional[str] = ""
    major_rivers_image_url: Optional[str] = ""
    mountains: Optional[str] = ""
    mountains_image_url: Optional[str] = ""
    beaches: Optional[str] = ""
    beaches_image_url: Optional[str] = ""
    forests: Optional[str] = ""
    forests_image_url: Optional[str] = ""
    climate: Optional[str] = ""
    climate_image_url: Optional[str] = ""

class FoodAndTraditionalLifestyle(BaseModel):
    food_image_url: Optional[str] = ""
    famous_dishes: Optional[str] = ""
    famous_dishes_image_url: Optional[str] = ""
    traditional_cuisine: Optional[str] = ""
    traditional_cuisine_image_url: Optional[str] = ""
    famous_ingredients: Optional[str] = ""
    famous_ingredients_image_url: Optional[str] = ""

class TraditionalLifestyleAndCulture(BaseModel):
    lifestyle_image_url: Optional[str] = ""
    traditional_dress: Optional[str] = ""
    traditional_dress_image_url: Optional[str] = ""
    occupations: Optional[str] = ""
    occupations_image_url: Optional[str] = ""
    local_communities: Optional[str] = ""
    local_communities_image_url: Optional[str] = ""

class HighlightsAndPlaces(BaseModel):
    highlights_image_url: Optional[str] = ""
    famous_arts_crafts: Optional[str] = ""
    famous_arts_crafts_image_url: Optional[str] = ""
    famous_personalities: Optional[str] = ""
    famous_personalities_image_url: Optional[str] = ""
    famous_places: Optional[str] = ""
    famous_places_image_url: Optional[str] = ""

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
    description_images: Optional[List[Any]] = Field(default_factory=list, description="List of description block image URLs or image URL arrays")
    gallery_images: Optional[List[str]] = Field(default_factory=list, description="List of gallery image URLs")

    # 📍 Quick Facts
    capital: Optional[str] = Field(None, description="Capital city")
    area: Optional[str] = Field(None, description="Total area")
    population: Optional[str] = Field(None, description="Population")
    official_languages: Optional[str] = Field(None, description="Official Language(s)")
    formation: Optional[str] = Field(None, description="Formation Date / Year")

    # 📦 Grouped Section Objects
    culture_and_heritage: Optional[Union[CultureAndHeritage, Dict[str, Any]]] = Field(default_factory=CultureAndHeritage, alias="Culture & Heritage")
    heritage_and_monuments: Optional[Union[HeritageAndMonuments, Dict[str, Any]]] = Field(default_factory=HeritageAndMonuments, alias="Heritage & Monuments")
    geography: Optional[Union[GeographySection, Dict[str, Any]]] = Field(default_factory=GeographySection, alias="Geography")
    food_and_traditional_lifestyle: Optional[Union[FoodAndTraditionalLifestyle, Dict[str, Any]]] = Field(default_factory=FoodAndTraditionalLifestyle, alias="Food & Traditional Lifestyle")
    traditional_lifestyle_and_culture: Optional[Union[TraditionalLifestyleAndCulture, Dict[str, Any]]] = Field(default_factory=TraditionalLifestyleAndCulture, alias="Traditional Lifestyle & Culture")
    highlights_and_places: Optional[Union[HighlightsAndPlaces, Dict[str, Any]]] = Field(default_factory=HighlightsAndPlaces, alias="Highlights & Places")

    # 🐘 Wildlife
    state_animal: Optional[str] = Field(None, description="State Animal")
    state_bird: Optional[str] = Field(None, description="State Bird")
    state_tree: Optional[str] = Field(None, description="State Tree")
    state_flower: Optional[str] = Field(None, description="State Flower")
    national_parks_sanctuaries: Optional[str] = Field(None, description="National Parks / Sanctuaries")

    fun_fact: Optional[str] = Field(None, description="Interesting fun fact")
    is_active: bool = Field(True, description="Active status")

    class Config:
        populate_by_name = True
        by_alias = True


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
    description_images: Optional[List[Any]] = None
    gallery_images: Optional[List[str]] = None

    culture_image_url: Optional[str] = None
    heritage_image_url: Optional[str] = None
    geography_image_url: Optional[str] = None
    food_image_url: Optional[str] = None
    lifestyle_image_url: Optional[str] = None
    highlights_image_url: Optional[str] = None

    capital: Optional[str] = None
    area: Optional[str] = None
    population: Optional[str] = None
    official_languages: Optional[str] = None
    formation: Optional[str] = None

    traditional_dances: Optional[str] = None
    traditional_dances_image_url: Optional[str] = None
    traditional_music: Optional[str] = None
    traditional_music_image_url: Optional[str] = None
    festivals: Optional[str] = None
    festivals_image_url: Optional[str] = None
    traditional_clothing: Optional[str] = None
    traditional_clothing_image_url: Optional[str] = None
    culture_arts_crafts: Optional[str] = None
    culture_arts_crafts_image_url: Optional[str] = None
    culture_food: Optional[str] = None
    culture_food_image_url: Optional[str] = None
    traditions_customs: Optional[str] = None
    traditions_customs_image_url: Optional[str] = None

    historical_monuments: Optional[str] = None
    historical_monuments_image_url: Optional[str] = None
    temples_churches_mosques: Optional[str] = None
    temples_churches_mosques_image_url: Optional[str] = None
    forts: Optional[str] = None
    forts_image_url: Optional[str] = None
    unesco_heritage: Optional[str] = None
    unesco_heritage_image_url: Optional[str] = None

    major_rivers: Optional[str] = None
    major_rivers_image_url: Optional[str] = None
    mountains: Optional[str] = None
    mountains_image_url: Optional[str] = None
    beaches: Optional[str] = None
    beaches_image_url: Optional[str] = None
    forests: Optional[str] = None
    forests_image_url: Optional[str] = None
    climate: Optional[str] = None
    climate_image_url: Optional[str] = None

    state_animal: Optional[str] = None
    state_bird: Optional[str] = None
    state_tree: Optional[str] = None
    state_flower: Optional[str] = None
    national_parks_sanctuaries: Optional[str] = None

    famous_dishes: Optional[str] = None
    famous_dishes_image_url: Optional[str] = None
    traditional_cuisine: Optional[str] = None
    traditional_cuisine_image_url: Optional[str] = None
    famous_ingredients: Optional[str] = None
    famous_ingredients_image_url: Optional[str] = None

    traditional_dress: Optional[str] = None
    traditional_dress_image_url: Optional[str] = None
    occupations: Optional[str] = None
    occupations_image_url: Optional[str] = None
    local_communities: Optional[str] = None
    local_communities_image_url: Optional[str] = None

    famous_arts_crafts: Optional[str] = None
    famous_arts_crafts_image_url: Optional[str] = None
    famous_personalities: Optional[str] = None
    famous_personalities_image_url: Optional[str] = None
    famous_places: Optional[str] = None
    famous_places_image_url: Optional[str] = None

    culture_and_heritage: Optional[Union[CultureAndHeritage, Dict[str, Any]]] = Field(None, alias="Culture & Heritage")
    heritage_and_monuments: Optional[Union[HeritageAndMonuments, Dict[str, Any]]] = Field(None, alias="Heritage & Monuments")
    geography: Optional[Union[GeographySection, Dict[str, Any]]] = Field(None, alias="Geography")
    food_and_traditional_lifestyle: Optional[Union[FoodAndTraditionalLifestyle, Dict[str, Any]]] = Field(None, alias="Food & Traditional Lifestyle")
    traditional_lifestyle_and_culture: Optional[Union[TraditionalLifestyleAndCulture, Dict[str, Any]]] = Field(None, alias="Traditional Lifestyle & Culture")
    highlights_and_places: Optional[Union[HighlightsAndPlaces, Dict[str, Any]]] = Field(None, alias="Highlights & Places")

    fun_fact: Optional[str] = None
    is_active: Optional[bool] = None

    class Config:
        populate_by_name = True
        by_alias = True
        extra = "allow"


class IndianExplorerResponse(IndianExplorerBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        by_alias = True
        json_encoders = {datetime: lambda v: v.isoformat()}

