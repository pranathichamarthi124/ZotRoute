from typing import List, Dict, Optional, Any
from datetime import datetime

WALKING_SPEED_MPS = 1.4  # average walking speed in meters per second


def rank_businesses(businesses: List[Dict], gap_minutes: int) -> List[Dict]:
    """
    Ranks businesses by category match based on gap length.
    - Short gap (< 30 min): coffee/snack categories first
    - Medium gap (30-60 min): fast food / convenience first
    - Long gap (> 60 min): sit-down restaurants first

    Designed to be replaced/extended when user preferences are implemented.
    """
    if gap_minutes < 30:
        priority = ["cafe", "fast_food", "convenience"]
    elif gap_minutes < 60:
        priority = ["fast_food", "food_court", "convenience", "cafe"]
    else:
        priority = ["restaurant", "food_court", "cafe", "fast_food"]

    def sort_key(b):
        category = b.get("category") or ""
        try:
            return priority.index(category)
        except ValueError:
            return len(priority)  # unlisted categories go to the bottom

    return sorted(businesses, key=sort_key)


def estimate_walk_time(distance_meters: float) -> str:
    """Converts a distance in meters to a human-readable walk time string."""
    if not distance_meters:
        return "unknown"
    # Apply 1.4x multiplier to account for roads/paths vs straight-line distance
    adjusted = distance_meters * 1.4
    seconds = adjusted / WALKING_SPEED_MPS
    minutes = round(seconds / 60)
    if minutes < 1:
        return "less than 1 min walk"
    return f"{minutes} min walk"


def get_best_recommendation(
    bus_options: List[Any],
    walk_spots: List[Dict],
    gap_start: str,
    gap_minutes: int
) -> Optional[Dict]:
    """
    - All gaps: returns top 3 nearby walkable businesses ranked by category/gap length
    - Long gaps (>= 120 min): also returns transit routes to known landmarks
    """
    result = {}

    # 1. WALK RECOMMENDATIONS (always)
    if walk_spots:
        ranked = rank_businesses(walk_spots, gap_minutes)
        top_3 = ranked[:3]
        result["walk_suggestions"] = [
            {
                "name": b.get("name", "Unknown"),
                "category": b.get("category", "Unknown"),
                "walk_time": estimate_walk_time(b.get("distance_meters")),
            }
            for b in top_3
        ]
    else:
        result["walk_suggestions"] = []

    # 2. BUS RECOMMENDATIONS (long gaps only, via multi-transfer planner)
    if gap_minutes >= 120 and bus_options:
        bus_suggestions = []
        for option in bus_options:
            landmark = option.get("landmark", {})
            path = option.get("path", [])

            if not path:
                continue

            # Summarize the path into a readable format
            legs = []
            for leg in path:
                if leg.get("action") == "Ride Bus":
                    legs.append(f"Route {leg['route']} from {leg['from']} to {leg['to']}")
                elif leg.get("action") == "Walk":
                    legs.append(f"Walk {leg.get('distance_meters', '?')}m to {leg.get('destination', '?')}")

            bus_suggestions.append({
                "name": landmark.get("name", "Unknown"),
                "description": landmark.get("description", ""),
                "directions": legs
            })

        result["bus_suggestions"] = bus_suggestions

    if not result.get("walk_suggestions") and not result.get("bus_suggestions"):
        return None

    result["type"] = "Explore"
    return result