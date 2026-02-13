from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
import httpx
from datetime import datetime, timedelta

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

async def get_osm_businesses(lat: float, lon: float):
    overpass_url = "https://overpass-api.de/api/interpreter"
    query = f"""
    [out:json];
    (
      nwr["amenity"~"restaurant|cafe|fast_food|bar"](around:300,{lat},{lon});
      nwr["shop"](around:300,{lat},{lon});
    );
    out center;
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(overpass_url, data={'data': query}, timeout=5.0)
            if response.status_code == 200:
                elements = response.json().get("elements", [])
                return [
                    {
                        "name": e.get("tags", {}).get("name", "Unknown Business"),
                        "category": e.get("tags", {}).get("amenity") or e.get("tags", {}).get("shop")
                    }
                    for e in elements if "tags" in e and "name" in e["tags"]
                ][:5]
    except Exception:
        return []
    return []

@app.get("/")
def read_root():
    return {"message": "ZotRoute Backend is Running!"}

@app.get("/routes/", response_model=List[RouteBase])
def get_routes(db: Session = Depends(get_db)):
    return db.query(Route).all()

@app.get("/recommend/transit")
async def recommend_transit(
    user_lat: float, 
    user_lon: float, 
    dest_stop_id: str, 
    arrive_by: str = "10:00:00", 
    db: Session = Depends(get_db)
):
    nearest_query = text("""
        SELECT stop_id, stop_name, 
               ST_Distance(
                   ST_MakePoint(stop_lon, stop_lat)\:\:geography,
                   ST_MakePoint(:lon, :lat)\:\:geography
               ) as meters
        FROM stops
        ORDER BY meters ASC LIMIT 1
    """)
    origin = db.execute(nearest_query, {"lon": user_lon, "lat": user_lat}).fetchone()
    
    if not origin:
        raise HTTPException(status_code=404, detail="No nearby stops found.")
    
    dest_query = text("SELECT stop_name FROM stops WHERE TRIM(stop_id) = :id")
    dest_stop = db.execute(dest_query, {"id": dest_stop_id}).fetchone()
    
    if not dest_stop:
        raise HTTPException(status_code=404, detail="Destination stop not found.")

    trip_query = text("""
        SELECT trip_id, arrival_time FROM stop_times 
        WHERE TRIM(stop_id) = :dest_id 
          AND CAST(TRIM(arrival_time) AS TIME) <= CAST(:arrive_time AS TIME) 
        ORDER BY CAST(arrival_time AS TIME) DESC LIMIT 1
    """)
    trip = db.execute(trip_query, {"dest_id": dest_stop_id, "arrive_time": arrive_by}).fetchone()
    
    if not trip:
        raise HTTPException(status_code=404, detail="No buses found arriving by that time.")
    
    departure_query = text("""
        SELECT departure_time FROM stop_times 
        WHERE trip_id = :trip_id AND TRIM(stop_id) = :origin_id
    """)
    departure = db.execute(departure_query, {"trip_id": trip.trip_id, "origin_id": origin.stop_id}).fetchone()
    
    if not departure:
        raise HTTPException(status_code=400, detail="Bus does not hit your closest stop.")

    try:
        clean_departure = departure.departure_time.strip()
        h, m, s = map(int, clean_departure.split(':'))
        dep_dt = datetime.strptime(f"{h%24:02d}:{m:02d}:{s:02d}", "%H:%M:%S")
        walk_seconds = (origin.meters / 1.2) + 120
        leave_dt = dep_dt - timedelta(seconds=walk_seconds)

        return {
            "origin": origin.stop_name,
            "destination": dest_stop.stop_name,
            "bus_departure": clean_departure,
            "bus_arrival": trip.arrival_time.strip(),
            "suggested_leave_time": leave_dt.strftime("%H:%M"),
            "walk_dist_meters": round(origin.meters)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/recommend/explore")
async def explore_nearby(stop_id: str, db: Session = Depends(get_db)):
    stop_query = text("SELECT stop_lat, stop_lon FROM stops WHERE TRIM(stop_id) = :id")
    stop = db.execute(stop_query, {"id": stop_id}).fetchone()
    
    if not stop:
        raise HTTPException(status_code=404, detail="Stop not found.")
        
    nearby = await get_osm_businesses(stop.stop_lat, stop.stop_lon)
    return {"stop_id": stop_id, "nearby_businesses": nearby}