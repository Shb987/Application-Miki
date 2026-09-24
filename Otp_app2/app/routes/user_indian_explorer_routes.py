from typing import List
from fastapi import APIRouter
from app.core.database import db
from app.models.explorer_models import IndianExplorerResponse

router = APIRouter(prefix="/indian-explorer", tags=["Indian Explorer - User"])

def serialize_doc(doc):
    if not doc:
        return None

    doc = dict(doc)
    doc["id"] = str(doc.pop("_id")) if "_id" in doc else doc.get("id", "")
    if "gallery_images" not in doc or doc["gallery_images"] is None:
        doc["gallery_images"] = []
    if "descriptions" not in doc or doc["descriptions"] is None:
        doc["descriptions"] = [doc.get("full_description")] if doc.get("full_description") else []

    def get_val(key, section_names, default=""):
        for sec in section_names:
            if sec in doc and isinstance(doc[sec], dict) and key in doc[sec]:
                return doc[sec][key]
        return doc.get(key, default)

    culture_and_heritage = {
        "culture_image_url": get_val("culture_image_url", ["Culture & Heritage", "culture_and_heritage"], ""),
        "traditional_dances": get_val("traditional_dances", ["Culture & Heritage", "culture_and_heritage"], ""),
        "traditional_dances_image_url": get_val("traditional_dances_image_url", ["Culture & Heritage", "culture_and_heritage"], ""),
        "traditional_music": get_val("traditional_music", ["Culture & Heritage", "culture_and_heritage"], ""),
        "traditional_music_image_url": get_val("traditional_music_image_url", ["Culture & Heritage", "culture_and_heritage"], ""),
        "festivals": get_val("festivals", ["Culture & Heritage", "culture_and_heritage"], ""),
        "festivals_image_url": get_val("festivals_image_url", ["Culture & Heritage", "culture_and_heritage"], ""),
        "traditions_customs": get_val("traditions_customs", ["Culture & Heritage", "culture_and_heritage"], ""),
        "traditions_customs_image_url": get_val("traditions_customs_image_url", ["Culture & Heritage", "culture_and_heritage"], "")
    }

    heritage_and_monuments = {
        "heritage_image_url": get_val("heritage_image_url", ["Heritage & Monuments", "heritage_and_monuments"], ""),
        "historical_monuments": get_val("historical_monuments", ["Heritage & Monuments", "heritage_and_monuments"], ""),
        "historical_monuments_image_url": get_val("historical_monuments_image_url", ["Heritage & Monuments", "heritage_and_monuments"], ""),
        "temples_churches_mosques": get_val("temples_churches_mosques", ["Heritage & Monuments", "heritage_and_monuments"], ""),
        "temples_churches_mosques_image_url": get_val("temples_churches_mosques_image_url", ["Heritage & Monuments", "heritage_and_monuments"], ""),
        "forts": get_val("forts", ["Heritage & Monuments", "heritage_and_monuments"], ""),
        "forts_image_url": get_val("forts_image_url", ["Heritage & Monuments", "heritage_and_monuments"], ""),
        "unesco_heritage": get_val("unesco_heritage", ["Heritage & Monuments", "heritage_and_monuments"], ""),
        "unesco_heritage_image_url": get_val("unesco_heritage_image_url", ["Heritage & Monuments", "heritage_and_monuments"], "")
    }

    geography = {
        "geography_image_url": get_val("geography_image_url", ["Geography", "geography"], ""),
        "major_rivers": get_val("major_rivers", ["Geography", "geography"], ""),
        "major_rivers_image_url": get_val("major_rivers_image_url", ["Geography", "geography"], ""),
        "mountains": get_val("mountains", ["Geography", "geography"], ""),
        "mountains_image_url": get_val("mountains_image_url", ["Geography", "geography"], ""),
        "beaches": get_val("beaches", ["Geography", "geography"], ""),
        "beaches_image_url": get_val("beaches_image_url", ["Geography", "geography"], ""),
        "forests": get_val("forests", ["Geography", "geography"], ""),
        "forests_image_url": get_val("forests_image_url", ["Geography", "geography"], ""),
        "climate": get_val("climate", ["Geography", "geography"], ""),
        "climate_image_url": get_val("climate_image_url", ["Geography", "geography"], "")
    }

    famous_dishes_val = get_val("famous_dishes", ["Food & Traditional Lifestyle", "food_and_traditional_lifestyle"], "") or get_val("culture_food", ["Culture & Heritage", "culture_and_heritage"], "")
    famous_dishes_img = get_val("famous_dishes_image_url", ["Food & Traditional Lifestyle", "food_and_traditional_lifestyle"], "") or get_val("culture_food_image_url", ["Culture & Heritage", "culture_and_heritage"], "")

    food_and_lifestyle = {
        "food_image_url": get_val("food_image_url", ["Food & Traditional Lifestyle", "food_and_traditional_lifestyle"], ""),
        "famous_dishes": famous_dishes_val,
        "famous_dishes_image_url": famous_dishes_img,
        "traditional_cuisine": get_val("traditional_cuisine", ["Food & Traditional Lifestyle", "food_and_traditional_lifestyle"], ""),
        "traditional_cuisine_image_url": get_val("traditional_cuisine_image_url", ["Food & Traditional Lifestyle", "food_and_traditional_lifestyle"], ""),
        "famous_ingredients": get_val("famous_ingredients", ["Food & Traditional Lifestyle", "food_and_traditional_lifestyle"], ""),
        "famous_ingredients_image_url": get_val("famous_ingredients_image_url", ["Food & Traditional Lifestyle", "food_and_traditional_lifestyle"], "")
    }

    traditional_dress_val = get_val("traditional_dress", ["Traditional Lifestyle & Culture", "traditional_lifestyle_and_culture"], "") or get_val("traditional_clothing", ["Culture & Heritage", "culture_and_heritage"], "")
    traditional_dress_img = get_val("traditional_dress_image_url", ["Traditional Lifestyle & Culture", "traditional_lifestyle_and_culture"], "") or get_val("traditional_clothing_image_url", ["Culture & Heritage", "culture_and_heritage"], "")

    traditional_lifestyle = {
        "lifestyle_image_url": get_val("lifestyle_image_url", ["Traditional Lifestyle & Culture", "traditional_lifestyle_and_culture"], ""),
        "traditional_dress": traditional_dress_val,
        "traditional_dress_image_url": traditional_dress_img,
        "occupations": get_val("occupations", ["Traditional Lifestyle & Culture", "traditional_lifestyle_and_culture"], ""),
        "occupations_image_url": get_val("occupations_image_url", ["Traditional Lifestyle & Culture", "traditional_lifestyle_and_culture"], ""),
        "local_communities": get_val("local_communities", ["Traditional Lifestyle & Culture", "traditional_lifestyle_and_culture"], ""),
        "local_communities_image_url": get_val("local_communities_image_url", ["Traditional Lifestyle & Culture", "traditional_lifestyle_and_culture"], "")
    }

    famous_arts_val = get_val("famous_arts_crafts", ["Highlights & Places", "highlights_and_places"], "") or get_val("culture_arts_crafts", ["Culture & Heritage", "culture_and_heritage"], "")
    famous_arts_img = get_val("famous_arts_crafts_image_url", ["Highlights & Places", "highlights_and_places"], "") or get_val("culture_arts_crafts_image_url", ["Culture & Heritage", "culture_and_heritage"], "")

    highlights_and_places = {
        "highlights_image_url": get_val("highlights_image_url", ["Highlights & Places", "highlights_and_places"], ""),
        "famous_arts_crafts": famous_arts_val,
        "famous_arts_crafts_image_url": famous_arts_img,
        "famous_personalities": get_val("famous_personalities", ["Highlights & Places", "highlights_and_places"], ""),
        "famous_personalities_image_url": get_val("famous_personalities_image_url", ["Highlights & Places", "highlights_and_places"], ""),
        "famous_places": get_val("famous_places", ["Highlights & Places", "highlights_and_places"], ""),
        "famous_places_image_url": get_val("famous_places_image_url", ["Highlights & Places", "highlights_and_places"], "")
    }

    subfield_keys_to_remove = [
        "culture_image_url", "traditional_dances", "traditional_dances_image_url", "traditional_music",
        "traditional_music_image_url", "festivals", "festivals_image_url", "traditional_clothing",
        "traditional_clothing_image_url", "culture_arts_crafts", "culture_arts_crafts_image_url",
        "culture_food", "culture_food_image_url", "traditions_customs", "traditions_customs_image_url",
        "heritage_image_url", "historical_monuments", "historical_monuments_image_url",
        "temples_churches_mosques", "temples_churches_mosques_image_url", "forts", "forts_image_url",
        "unesco_heritage", "unesco_heritage_image_url",
        "geography_image_url", "major_rivers", "major_rivers_image_url", "mountains", "mountains_image_url",
        "beaches", "beaches_image_url", "forests", "forests_image_url", "climate", "climate_image_url",
        "food_image_url", "famous_dishes", "famous_dishes_image_url", "traditional_cuisine",
        "traditional_cuisine_image_url", "famous_ingredients", "famous_ingredients_image_url",
        "lifestyle_image_url", "traditional_dress", "traditional_dress_image_url", "occupations",
        "occupations_image_url", "local_communities", "local_communities_image_url",
        "highlights_image_url", "famous_arts_crafts", "famous_arts_crafts_image_url", "famous_personalities",
        "famous_personalities_image_url", "famous_places", "famous_places_image_url",
        "traditional_dances_title", "festivals_title",
        "culture_and_heritage", "heritage_and_monuments", "food_and_traditional_lifestyle",
        "traditional_lifestyle_and_culture", "highlights_and_places"
    ]
    for k in subfield_keys_to_remove:
        doc.pop(k, None)

    doc["Culture & Heritage"] = culture_and_heritage
    doc["Heritage & Monuments"] = heritage_and_monuments
    doc["Geography"] = geography
    doc["Food & Traditional Lifestyle"] = food_and_lifestyle
    doc["Traditional Lifestyle & Culture"] = traditional_lifestyle
    doc["Highlights & Places"] = highlights_and_places

    return doc

@router.get("", response_model=List[IndianExplorerResponse])
async def get_active_indian_entities():
    """Get active Indian Explorer entities for students & app users ordered by order number"""
    cursor = db.indian_explorer.find({"is_active": True}).sort("order", 1)
    entities = await cursor.to_list(length=None)
    return [serialize_doc(doc) for doc in entities]
