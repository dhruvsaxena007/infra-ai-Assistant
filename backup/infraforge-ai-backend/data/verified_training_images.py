"""
Verified downloadable image URLs for YOLO training seed (Pexels + Cloudinary + S3).

Wikimedia URLs often block automated downloads; these sources work with GET.
"""

from __future__ import annotations

def _pexels(photo_id: int) -> str:
    return f"https://images.pexels.com/photos/{photo_id}/pexels-photo-{photo_id}.jpeg"


# Pools keyed by visual family (4+ images each)
_POOLS: dict[str, list[str]] = {
    "lift": [
        _pexels(16105409),
        _pexels(1090638),
        _pexels(276724),
        _pexels(256424),
    ],
    "forklift": [
        _pexels(16105409),
        _pexels(122164),
        _pexels(380769),
        _pexels(1287145),
    ],
    "excavator": [
        _pexels(2101137),
        _pexels(1078884),
        "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507295/652234-excavator-1174428.jpg.jpg",
        "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507335/pexels-digger-1867268.jpg.jpg",
    ],
    "bulldozer": [
        _pexels(15363842),
        _pexels(8361810),
        "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507294/dimitrisvetsikas1969-bulldozer-2195329.jpg.jpg",
        _pexels(256541),
    ],
    "grader": [
        "https://infraforge-docs.s3.ap-south-1.amazonaws.com/dev/uploads/productImages/productImages_1779780612094_motor_grader_front.jpg",
        "https://infraforge-docs.s3.ap-south-1.amazonaws.com/dev/uploads/productImages/productImages_1779860870640_motor_grader_side.jpg",
        "https://infraforge-docs.s3.ap-south-1.amazonaws.com/dev/uploads/productImages/productImages_1779860870638_motor_grader_front.jpg",
        "https://res.cloudinary.com/dzjzxbebz/image/upload/v1776916740/productImages_1776916737372_motor_grader.png",
    ],
    "roller": [
        "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507294/katerwursty-road-roller-6564386.jpg.jpg",
        _pexels(333848),
        _pexels(248547),
        _pexels(1427107),
    ],
    "truck": [
        "https://infraforge-docs.s3.ap-south-1.amazonaws.com/dev/uploads/productImages/productImages_1779942377195_press-13aug20-lowres.jpg",
        "https://infraforge-docs.s3.ap-south-1.amazonaws.com/dev/uploads/productImages/productImages_1779942341129_press-13aug20-lowres.jpg",
        "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507423/memorycatcher-truck-417149.jpg.jpg",
        _pexels(1141853),
    ],
    "loader": [
        "https://res.cloudinary.com/dzjzxbebz/image/upload/v1776857303/productImages_1776857300241_backhoe_loader.png",
        _pexels(1099198),
        _pexels(1141853),
        "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507376/dimitrisvetsikas1969-machine-3023906.jpg.jpg",
    ],
    "crane": [
        "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507411/dimitrisvetsikas1969-crane-1842747.jpg.jpg",
        _pexels(1090638),
        _pexels(256424),
        _pexels(276724),
    ],
    "drill": [
        "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507461/ds_30-equipment-4840223.jpg.jpg",
        "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507412/retinacreative-piling-rig-4429049.jpg.jpg",
        _pexels(1427107),
        _pexels(248547),
    ],
    "pump": [
        "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507295/652234-excavator-1174428.jpg.jpg",
        _pexels(1141853),
        _pexels(1099198),
        _pexels(256424),
    ],
    "compressor": [
        "https://infraforge-docs.s3.ap-south-1.amazonaws.com/dev/uploads/productImages/productImages_1779943190787_air-compressor-support-truck-1702019936-7199582.webp",
        _pexels(1287145),
        _pexels(380769),
        _pexels(122164),
    ],
    "crusher": [
        "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507333/elsemargriet-excavator-5907586.jpg.jpg",
        "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507333/dimitrisvetsikas1969-heavy-machinery-6761291.jpg.jpg",
        _pexels(2101137),
        _pexels(1078884),
    ],
    "forestry": [
        _pexels(256541),
        _pexels(333848),
        _pexels(248547),
        _pexels(1427107),
    ],
    "paver": [
        _pexels(276024),
        _pexels(1427107),
        "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507294/katerwursty-road-roller-6564386.jpg.jpg",
        _pexels(333848),
    ],
    "support": [
        _pexels(1099198),
        _pexels(380769),
        _pexels(122164),
        _pexels(1287145),
    ],
    "mining": [
        _pexels(2101137),
        _pexels(1078884),
        _pexels(1141853),
        "https://res.cloudinary.com/dzjzxbebz/image/upload/v1774507423/memorycatcher-truck-417149.jpg.jpg",
    ],
}

# canonical category -> visual pool
_CATEGORY_POOL: dict[str, str] = {
    "boom lift": "lift",
    "scissor lift": "lift",
    "single man lift": "lift",
    "forklift": "forklift",
    "walkie stacker": "forklift",
    "telehandler": "loader",
    "knuckleboom loader": "crane",
    "excavator": "excavator",
    "dragline excavator": "mining",
    "backhoe loader": "loader",
    "bulldozer": "bulldozer",
    "motor grader": "grader",
    "wheel loader": "loader",
    "compact loader": "loader",
    "compact track loader": "loader",
    "wheel tractor scraper": "bulldozer",
    "trencher": "excavator",
    "dump truck": "truck",
    "articulated hauler": "truck",
    "off highway truck": "mining",
    "road roller": "roller",
    "drum roller": "roller",
    "compactor": "roller",
    "asphalt paver": "paver",
    "cold planer": "paver",
    "crane": "crane",
    "hydra crane": "crane",
    "truck mounted crane": "crane",
    "carry deck crane": "crane",
    "concrete mixer": "truck",
    "concrete mixer truck": "truck",
    "concrete pump": "pump",
    "crawler drill": "drill",
    "drill rig": "drill",
    "feller buncher": "forestry",
    "harvester": "forestry",
    "skidder": "forestry",
    "forwarder": "forestry",
    "tunnel boring machine": "mining",
    "rock breaker": "excavator",
    "pipe layer": "crane",
    "mobile crusher": "crusher",
    "air compressor": "compressor",
    "towable light tower": "support",
    "utility vehicle": "support",
}


def get_images_for_category(canonical: str) -> list[str]:
    """Return 4 image URLs for a canonical equipment category."""
    pool_key = _CATEGORY_POOL.get(canonical, "support")
    pool = _POOLS.get(pool_key) or _POOLS["support"]
    return list(pool[:4])
