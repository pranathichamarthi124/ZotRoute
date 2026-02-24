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

from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from collections import deque
from datetime import datetime, time, timedelta

@app.get("/plan_trip/multi-transfer")
def plan_multi_transfer(
    origin_stop_id: str, 
    dest_stop_id: str, 
    arrive_by: Optional[str] = None,
    db: Session = Depends(get_db)
):
    def parse_time_str(t_str):
        if not t_str: return None
        t_str = t_str.strip()
        try:
            if ":" not in t_str: return f"{int(t_str):02d}:00:00"
            parts = list(map(int, t_str.split(':')))
            return f"{parts[0]:02d}:{parts[1]:02d}:{parts[2] if len(parts)>2 else 0:02d}"
        except: return None

    def get_py_time(t_str):
        if not t_str: return time(0,0,0)
        try:
            h, m, s = map(int, t_str.strip().split(':'))
            return time(h % 24, m, s)
        except: return time(0,0,0)

    deadline_str = parse_time_str(arrive_by)
    is_time_sensitive = deadline_str is not None

    start_node = dest_stop_id.strip() if is_time_sensitive else origin_stop_id.strip()
    queue = deque([(start_node, [], deadline_str if is_time_sensitive else None)])
    visited = {start_node}
    max_depth = 4 

    while queue:
        curr_id, path, current_constraint = queue.popleft()
        if len(path) >= max_depth: continue

        order_clause = "ORDER BY st2.arrival_time DESC" if is_time_sensitive else "ORDER BY st1.departure_time ASC"

        # The optimized query using the pre-computed 'transfers' table
        query_sql = f"""
            SELECT DISTINCT
                st1.stop_id AS prev_id,
                st2.stop_id AS next_id,
                orig_s.stop_name AS from_name,
                dest_s.stop_name AS to_name,
                r.route_short_name,
                st1.departure_time,
                st2.arrival_time,
                tr.walk_meters
            FROM transfers tr
            JOIN stop_times {{target_join}} ON tr.to_stop_id = {{target_join}}.stop_id
            JOIN stop_times {{other_join}} ON st1.trip_id = st2.trip_id
            JOIN trips t ON st1.trip_id = t.trip_id
            JOIN routes r ON t.route_id = r.route_id
            JOIN stops orig_s ON st1.stop_id = orig_s.stop_id
            JOIN stops dest_s ON st2.stop_id = dest_s.stop_id
            WHERE tr.from_stop_id = :curr
              AND st1.stop_sequence < st2.stop_sequence
            {{time_filter}}
            {order_clause}
        """

        time_filter = ""
        if is_time_sensitive:
            time_filter = "AND TRIM(st2.arrival_time) <= :constraint"
            full_query = text(query_sql.format(target_join="st2", other_join="st1", time_filter=time_filter))
        else:
            full_query = text(query_sql.format(target_join="st1", other_join="st2", time_filter=""))

        try:
            results = db.execute(full_query, {"curr": curr_id, "constraint": current_constraint}).fetchall()
        except Exception as e:
            print(f"SQL Error: {e}")
            continue

        for row in results:
            prev_id = row.prev_id.strip() if row.prev_id else ""
            next_id = row.next_id.strip() if row.next_id else ""
            next_search_id = prev_id if is_time_sensitive else next_id
            
            if not next_search_id:
                continue
            
            dist = row.walk_meters if row.walk_meters is not None else 0
            route_name = row.route_short_name if row.route_short_name else "Bus"
            from_name = row.from_name if row.from_name else "Unknown Stop"
            to_name = row.to_name if row.to_name else "Unknown Stop"
            
            leg = {
                "route": route_name,
                "from": from_name,
                "to": to_name,
                "walk_meters": round(dist)
            }
            
            if is_time_sensitive:
                if not row.departure_time or not row.arrival_time:
                    continue 
                
                dep_time_str = row.departure_time.strip()
                arr_time_str = row.arrival_time.strip()
                leg.update({"departure": dep_time_str, "arrival": arr_time_str})
                
                try:
                    dep_obj = get_py_time(dep_time_str)
                    arr_obj = get_py_time(arr_time_str)
                    constraint_obj = get_py_time(current_constraint)
                    
                    walk_buffer = timedelta(seconds=(dist / 1.0)) 
                    arr_dt = datetime.combine(datetime.today(), arr_obj)
                    const_dt = datetime.combine(datetime.today(), constraint_obj)
                    
                    if (arr_dt + walk_buffer) > const_dt:
                        continue
                        
                    new_constraint_str = dep_time_str
                    new_path = [leg] + path
                except Exception:
                    continue 
            else:
                new_path = path + [leg]
                new_constraint_str = None

            target_id = origin_stop_id.strip() if is_time_sensitive else dest_stop_id.strip()
            
            if next_search_id == target_id:
                return {
                    "status": "success", 
                    "mode": "time-constrained" if is_time_sensitive else "generic", 
                    "path": new_path
                }

            if next_search_id not in visited:
                visited.add(next_search_id)
                queue.append((next_search_id, new_path, new_constraint_str))

    raise HTTPException(status_code=404, detail="No route found.")


@app.get("/plan_trip/coordinates")
def plan_trip_by_coords(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    arrive_by: Optional[str] = None,
    db: Session = Depends(get_db)
):
    # --- Helper: Find Nearest Stop ---
    def get_nearest_stop(lat: float, lon: float):
        query = text("""
            SELECT stop_id, stop_name,
                   ST_Distance(
                       ST_MakePoint(:lon, :lat)::geography,
                       ST_MakePoint(stop_lon, stop_lat)::geography
                   ) as walk_dist
            FROM stops
            ORDER BY walk_dist ASC
            LIMIT 1
        """)
        result = db.execute(query, {"lat": lat, "lon": lon}).fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="No transit stops found near these coordinates.")
        return result.stop_id.strip(), result.stop_name, round(result.walk_dist)

    orig_stop_id, orig_stop_name, orig_walk_meters = get_nearest_stop(origin_lat, origin_lon)
    dest_stop_id, dest_stop_name, dest_walk_meters = get_nearest_stop(dest_lat, dest_lon)

    # --- Helper: Time Parsers ---
    def parse_time_str(t_str):
        if not t_str: return None
        t_str = t_str.strip()
        try:
            if ":" not in t_str: return f"{int(t_str):02d}:00:00"
            parts = list(map(int, t_str.split(':')))
            return f"{parts[0]:02d}:{parts[1]:02d}:{parts[2] if len(parts)>2 else 0:02d}"
        except: return None

    def get_py_time(t_str):
        if not t_str: return time(0,0,0)
        try:
            h, m, s = map(int, t_str.strip().split(':'))
            return time(h % 24, m, s)
        except: return time(0,0,0)

    # --- Setup Search ---
    deadline_str = parse_time_str(arrive_by)
    is_time_sensitive = deadline_str is not None

    start_node = dest_stop_id if is_time_sensitive else orig_stop_id
    queue = deque([(start_node, [], deadline_str if is_time_sensitive else None)])
    visited = {start_node}
    max_depth = 4 

    # --- BFS Algorithm ---
    while queue:
        curr_id, path, current_constraint = queue.popleft()
        if len(path) >= max_depth: continue

        order_clause = "ORDER BY st2.arrival_time DESC" if is_time_sensitive else "ORDER BY st1.departure_time ASC"

        query_sql = f"""
            SELECT DISTINCT
                st1.stop_id AS prev_id,
                st2.stop_id AS next_id,
                orig_s.stop_name AS from_name,
                dest_s.stop_name AS to_name,
                r.route_short_name,
                st1.departure_time,
                st2.arrival_time,
                tr.walk_meters
            FROM transfers tr
            JOIN stop_times {{target_join}} ON tr.to_stop_id = {{target_join}}.stop_id
            JOIN stop_times {{other_join}} ON st1.trip_id = st2.trip_id
            JOIN trips t ON st1.trip_id = t.trip_id
            JOIN routes r ON t.route_id = r.route_id
            JOIN stops orig_s ON st1.stop_id = orig_s.stop_id
            JOIN stops dest_s ON st2.stop_id = dest_s.stop_id
            WHERE tr.from_stop_id = :curr
              AND st1.stop_sequence < st2.stop_sequence
            {{time_filter}}
            {order_clause}
        """

        time_filter = ""
        if is_time_sensitive:
            time_filter = "AND TRIM(st2.arrival_time) <= :constraint"
            full_query = text(query_sql.format(target_join="st2", other_join="st1", time_filter=time_filter))
        else:
            full_query = text(query_sql.format(target_join="st1", other_join="st2", time_filter=""))

        try:
            results = db.execute(full_query, {"curr": curr_id, "constraint": current_constraint}).fetchall()
        except Exception as e:
            continue

        for row in results:
            prev_id = row.prev_id.strip() if row.prev_id else ""
            next_id = row.next_id.strip() if row.next_id else ""
            next_search_id = prev_id if is_time_sensitive else next_id
            
            if not next_search_id: continue
            
            dist = row.walk_meters if row.walk_meters is not None else 0
            route_name = row.route_short_name if row.route_short_name else "Bus"
            from_name = row.from_name if row.from_name else "Unknown Stop"
            to_name = row.to_name if row.to_name else "Unknown Stop"
            
            leg = {
                "route": route_name,
                "from": from_name,
                "to": to_name,
                "walk_meters": round(dist)
            }
            
            if is_time_sensitive:
                if not row.departure_time or not row.arrival_time: continue 
                
                dep_time_str = row.departure_time.strip()
                arr_time_str = row.arrival_time.strip()
                leg.update({"departure": dep_time_str, "arrival": arr_time_str})
                
                try:
                    dep_obj = get_py_time(dep_time_str)
                    arr_obj = get_py_time(arr_time_str)
                    constraint_obj = get_py_time(current_constraint)
                    
                    walk_buffer = timedelta(seconds=(dist / 1.0)) 
                    arr_dt = datetime.combine(datetime.today(), arr_obj)
                    const_dt = datetime.combine(datetime.today(), constraint_obj)
                    
                    if (arr_dt + walk_buffer) > const_dt: continue
                        
                    new_constraint_str = dep_time_str
                    new_path = [leg] + path
                except Exception:
                    continue 
            else:
                new_path = path + [leg]
                new_constraint_str = None

            target_id = orig_stop_id if is_time_sensitive else dest_stop_id
            
            if next_search_id == target_id:
                # --- Format the JSON to be a readable step-by-step itinerary ---
                readable_itinerary = []
                
                for i, step in enumerate(new_path):
                    # 1. Combine the starting GPS walk with the walk to the first bus
                    if i == 0:
                        total_start_walk = orig_walk_meters + step.get("walk_meters", 0)
                        if total_start_walk > 0:
                            readable_itinerary.append({
                                "action": "Walk",
                                "destination": step["from"],
                                "distance_meters": total_start_walk
                            })
                    # 1b. Handle walking between transfers
                    else:
                        if step.get("walk_meters", 0) > 0:
                            readable_itinerary.append({
                                "action": "Walk",
                                "destination": step["from"],
                                "distance_meters": step["walk_meters"]
                            })
                    
                    # 2. Add the Bus Ride
                    transit_leg = {
                        "action": "Ride Bus",
                        "route": step["route"],
                        "from": step["from"],
                        "to": step["to"]
                    }
                    if is_time_sensitive:
                        transit_leg["departure"] = step["departure"]
                        transit_leg["arrival"] = step["arrival"]
                        
                    readable_itinerary.append(transit_leg)

                # 3. Add the final walk from the last stop to the destination GPS
                if dest_walk_meters > 0:
                    readable_itinerary.append({
                        "action": "Walk",
                        "destination": "Final Destination",
                        "distance_meters": dest_walk_meters
                    })

                return {
                    "status": "success", 
                    "mode": "time-constrained" if is_time_sensitive else "generic",
                    "itinerary": readable_itinerary
                }

            if next_search_id not in visited:
                visited.add(next_search_id)
                queue.append((next_search_id, new_path, new_constraint_str))

    raise HTTPException(status_code=404, detail="No route found between these coordinates.")