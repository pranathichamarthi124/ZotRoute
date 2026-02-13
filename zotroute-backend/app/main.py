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

# Add this to ZotRoute/zotroute-backend/app/main.py

@app.get("/plan_trip")
def plan_trip(origin_stop_id: str, dest_stop_id: str, db: Session = Depends(get_db)):
    # This query finds all trips that hit BOTH stops, regardless of order
    query = text("""
        SELECT 
            st1.trip_id,
            r.route_short_name,
            st1.stop_sequence AS origin_seq,
            st2.stop_sequence AS dest_seq,
            st1.departure_time,
            st2.arrival_time,
            t.direction_id
        FROM stop_times st1
        JOIN stop_times st2 ON st1.trip_id = st2.trip_id
        JOIN trips t ON st1.trip_id = t.trip_id
        JOIN routes r ON t.route_id = r.route_id
        WHERE TRIM(st1.stop_id) = TRIM(:origin) 
          AND TRIM(st2.stop_id) = TRIM(:dest)
        ORDER BY st1.departure_time ASC
    """)
    
    results = db.execute(query, {"origin": origin_stop_id, "dest": dest_stop_id}).fetchall()
    
    if not results:
        return {"message": "No routes found between these stops."}

    itinerary = []
    for r in results:
        # Scenario A: Direct (Normal sequence)
        if r.origin_seq < r.dest_seq:
            itinerary.append({
                "route": r.route_short_name,
                "type": "Direct",
                "leave": r.departure_time.strip(),
                "arrive": r.arrival_time.strip(),
                "trip_id": r.trip_id
            })
        # Scenario B: Looping (The bus goes to the end and restarts)
        else:
            itinerary.append({
                "route": r.route_short_name,
                "type": "Loop (Stay on board)",
                "leave": r.departure_time.strip(),
                "arrive": f"{r.arrival_time.strip()} (Next Loop)",
                "trip_id": r.trip_id
            })

    # Return the first 5 options
    return itinerary[:5]

# Add to ZotRoute/zotroute-backend/app/main.py

from collections import deque

from datetime import datetime, time
from typing import List, Optional  # <--- Add Optional here
from collections import deque
from datetime import datetime, time
from collections import deque

# Update in ZotRoute/zotroute-backend/app/main.py

# Update in ZotRoute/zotroute-backend/app/main.py

# Update in ZotRoute/zotroute-backend/app/main.py

# Update in ZotRoute/zotroute-backend/app/main.py

@app.get("/plan_trip/multi-transfer")
def plan_multi_transfer(
    origin_stop_id: str, 
    dest_stop_id: str, 
    arrive_by: Optional[str] = None,
    db: Session = Depends(get_db)
):
    def parse_time(t_str):
        if not t_str: return None
        try:
            parts = list(map(int, t_str.strip().split(':')))
            return time(parts[0] % 24, parts[1], parts[2] if len(parts)>2 else 0)
        except: return None

    deadline_t = parse_time(arrive_by)
    is_time_sensitive = deadline_t is not None

    # Backward search starts at destination, Forward starts at origin
    start_node = dest_stop_id.strip() if is_time_sensitive else origin_stop_id.strip()
    queue = deque([(start_node, [], deadline_t if is_time_sensitive else None)])
    visited = {start_node}
    max_depth = 4 

    while queue:
        curr_id, path, current_constraint = queue.popleft()
        if len(path) >= max_depth: continue

        # The core logic: Find buses that connect to our current stop (or nearby)
        # For backward search: we look for trips ARRIVING at 'curr'
        # For forward search: we look for trips DEPARTING from 'curr'
        query_sql = """
            WITH nearby_stops AS (
                SELECT s2.stop_id, s2.stop_name,
                       ST_Distance(
                           ST_MakePoint(s1.stop_lon, s1.stop_lat)::geography,
                           ST_MakePoint(s2.stop_lon, s2.stop_lat)::geography
                       ) as walk_dist
                FROM stops s1, stops s2
                WHERE s1.stop_id = :curr
                  AND ST_DWithin(
                      ST_MakePoint(s1.stop_lon, s1.stop_lat)::geography,
                      ST_MakePoint(s2.stop_lon, s2.stop_lat)::geography,
                      300
                  )
            )
            SELECT DISTINCT
                st1.stop_id AS prev_id,
                st2.stop_id AS next_id,
                orig_s.stop_name AS from_name,
                dest_s.stop_name AS to_name,
                r.route_short_name,
                st1.departure_time,
                st2.arrival_time,
                ns.walk_dist
            FROM nearby_stops ns
            JOIN stop_times {target_join} ON ns.stop_id = {target_join}.stop_id
            JOIN stop_times {other_join} ON st1.trip_id = st2.trip_id
            JOIN trips t ON st1.trip_id = t.trip_id
            JOIN routes r ON t.route_id = r.route_id
            JOIN stops orig_s ON st1.stop_id = orig_s.stop_id
            JOIN stops dest_s ON st2.stop_id = dest_s.stop_id
            WHERE st1.stop_sequence < st2.stop_sequence
            {time_filter}
        """

        time_filter = ""
        if is_time_sensitive:
            # We convert "HH:MM:SS" to an interval and compare to our constraint
            time_filter = "AND (TRIM(st2.arrival_time)::interval <= :constraint::interval)"
            full_query = text(query_sql.format(target_join="st2", other_join="st1", time_filter=time_filter))
        else:
            full_query = text(query_sql.format(target_join="st1", other_join="st2", time_filter=""))

        try:
            results = db.execute(full_query, {"curr": curr_id, "constraint": current_constraint}).fetchall()
        except Exception as e:
            print(f"SQL Error: {e}")
            raise HTTPException(status_code=500, detail="Database query failed.")

        for row in results:
            next_search_id = row.prev_id.strip() if is_time_sensitive else row.next_id.strip()
            
            # Distance safety check
            dist = row.walk_dist if row.walk_dist is not None else 0
            
            leg = {
                "route": row.route_short_name,
                "from": row.from_name,
                "to": row.to_name,
                "walk_meters": round(dist)
            }
            
            if is_time_sensitive:
                leg.update({"departure": row.departure_time.strip(), "arrival": row.arrival_time.strip()})
                
                # Verify transfer time (walking speed ~1.2m/s)
                walk_buffer = timedelta(seconds=(dist / 1.2))
                arrival_dt = datetime.combine(datetime.today(), parse_time(row.arrival_time))
                if (arrival_dt + walk_buffer).time() > current_constraint:
                    continue
                new_path = [leg] + path
            else:
                new_path = path + [leg]

            if next_search_id == (origin_stop_id.strip() if is_time_sensitive else dest_stop_id.strip()):
                return {"status": "success", "mode": "time-constrained" if is_time_sensitive else "generic", "path": new_path}

            if next_search_id not in visited:
                visited.add(next_search_id)
                queue.append((next_search_id, new_path, parse_time(row.departure_time) if is_time_sensitive else None))

    raise HTTPException(status_code=404, detail="No route found.")