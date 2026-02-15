from pydantic import BaseModel
from typing import Optional, List

# --- Routes ---
class RouteBase(BaseModel):
    route_id: str
    route_short_name: Optional[str] = None
    route_long_name: Optional[str] = None
    route_color: Optional[str] = None

    class Config:
        from_attributes = True

# --- Stops ---
class StopBase(BaseModel):
    stop_id: str
    stop_name: str
    stop_lat: float
    stop_lon: float

    class Config:
        from_attributes = True

# --- Trip/Schedule (for later) ---
class TripResponse(BaseModel):
    trip_id: str
    headsign: Optional[str] = None