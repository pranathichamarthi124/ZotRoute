from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import List

# Import from our new models file
from app.init_db import SessionLocal
from app.models import Stop, Route
from app.schemas import StopBase, RouteBase

app = FastAPI(title="ZotRoute API")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def read_root():
    return {"message": "ZotRoute Backend is Running with Full GTFS!"}

# --- Route Endpoints ---

@app.get("/routes/", response_model=List[RouteBase])
def get_routes(db: Session = Depends(get_db)):
    """Fetch all available bus routes."""
    return db.query(Route).all()

# --- Stop Endpoints ---

@app.get("/stops/nearest/", response_model=List[StopBase])
def find_nearest_stop(lat: float, lon: float, db: Session = Depends(get_db)):
    """
    Finds the 5 closest bus stops using raw SQL for maximum speed.
    This assumes your 'stops' table has stop_lat and stop_lon.
    """
    # We use a raw SQL query here to construct the geometry on the fly 
    # if a dedicated 'geom' column doesn't exist yet.
    query = text("""
        SELECT stop_id, stop_name, stop_lat, stop_lon,
               ST_Distance(
                   ST_MakePoint(stop_lon, stop_lat)::geography,
                   ST_MakePoint(:user_lon, :user_lat)::geography
               ) as distance
        FROM stops
        ORDER BY distance ASC
        LIMIT 5
    """)
    
    result = db.execute(query, {"user_lon": lon, "user_lat": lat})
    
    stops = []
    for row in result:
        stops.append({
            "stop_id": row.stop_id,
            "stop_name": row.stop_name,
            "stop_lat": row.stop_lat,
            "stop_lon": row.stop_lon
        })
    return stops