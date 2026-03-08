import math
from datetime import datetime, timedelta, time
from collections import deque
from typing import List, Optional
import heapq

import httpx
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from icalendar import Calendar

from app.init_db import SessionLocal
from app.models import Stop, Route, StopResponse
from app.schemas import RouteBase
from app.constants import BUILDING_TO_STOP
from app.services.recommender import get_best_recommendation

app = FastAPI(title="ZotRoute API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CAMPUS_ZONES = {
    "North": {"hub": "University Center", "buildings": ["HIB", "SSLH", "SSH", "HH", "DBH", "LLIB", "ALH"]},
    "South": {"hub": "Physical Sciences/MSTB", "buildings": ["MSTB", "PSLH", "RH", "FRH", "NS1", "NS2"]},
    "East":  {"hub": "Engineering Gateway", "buildings": ["EH", "ISEB", "ET", "ENG", "MDE", "DBH"]}
}

HUB_COORDINATES = {
    "University Center": {"lat": 33.6487, "lon": -117.8427},
    "Physical Sciences/MSTB": {"lat": 33.6425, "lon": -117.8421},
    "Engineering Gateway": {"lat": 33.6437, "lon": -117.8416}
}

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_osm_businesses(lat: float, lon: float, business_type: Optional[str] = None, radius: int = 1200, db: Session = Depends(get_db)):
    
    cat_filter = ""
    if business_type:
        bt = business_type.lower().strip()
        if bt in ["coffee", "cafe", "boba"]:
            cat_filter = "AND category = 'cafe'"
        elif bt in ["food", "restaurant", "restaurants"]:
            cat_filter = "AND category = 'food'"
        elif bt in ["shop", "shopping", "store", "retail"]:
            cat_filter = "AND category = 'shop'"
        elif bt in ["bar", "pubs", "nightlife"]:
            cat_filter = "AND category = 'bar'"

    query = text(f"""
        SELECT name, category, lat, lon,
                ST_Distance(
                    ST_MakePoint(:lon, :lat)\:\:geography,
                    ST_MakePoint(lon, lat)\:\:geography
                ) as distance_meters
        FROM businesses
        WHERE 1=1 {cat_filter}
        ORDER BY distance_meters ASC
        LIMIT 10
    """)
    
    results = db.execute(query, {"lat": lat, "lon": lon}).fetchall()

    final_data = []
    for r in results:
        if r.distance_meters <= radius:
            final_data.append({
                "name": r.name,
                "category": r.category,
                "distance_meters": round(r.distance_meters),
                "lat": r.lat,
                "lon": r.lon
            })
            
    return final_data

@app.get("/")
def read_root():
    return {"message": "ZotRoute Backend is Running!"}

@app.get("/routes/", response_model=List[RouteBase])
def get_routes(db: Session = Depends(get_db)):
    return db.query(Route).all()

def parse_schedule_to_gaps(content):
    cal = Calendar.from_ical(content)
    events = []

    def to_naive(dt):
        return dt.replace(tzinfo=None) if dt.tzinfo else dt

    for component in cal.walk('vevent'):
        loc = str(component.get('LOCATION', 'UNKNOWN'))
        start = component.get('DTSTART').dt
        end = component.get('DTEND').dt
        if not isinstance(start, datetime):
            continue
        events.append({
            "building": loc.split(' ')[0],
            "start": to_naive(start),
            "end": to_naive(end)
        })

    events.sort(key=lambda x: x['start'])
    gaps = []
    seen = set()

    for i in range(len(events) - 1):
        if events[i]['start'].date() != events[i+1]['start'].date():
            continue
        diff = (events[i+1]['start'] - events[i]['end']).total_seconds() / 60
        if 15 < diff < 400:
            key = (events[i]['building'], events[i]['end'].strftime("%H:%M"))
            if key in seen:
                continue
            seen.add(key)
            gaps.append({
                "from_building": events[i]['building'],
                "duration_minutes": round(diff),
                "gap_start": events[i]['end'].strftime("%H:%M")
            })

    return gaps

@app.post("/student/process-schedule")
async def process_schedule(file: UploadFile = File(...), db: Session = Depends(get_db)):
    from app.constants import LANDMARKS

    content = await file.read()
    gaps = parse_schedule_to_gaps(content)
    itinerary = []

    for gap in gaps:
        origin_bldg = gap['from_building'].upper()
        stop_id = BUILDING_TO_STOP.get(origin_bldg)
        if not stop_id:
            continue

        coord_sql = text("SELECT stop_lat, stop_lon FROM stops WHERE TRIM(stop_id) = :sid LIMIT 1")
        origin = db.execute(coord_sql, {"sid": stop_id}).fetchone()

        walk_spots = await get_osm_businesses(origin.stop_lat, origin.stop_lon, radius=900) if origin else []

        bus_results = []
        if gap['duration_minutes'] >= 120:
            landmark_stop_ids = [k for k, v in LANDMARKS.items() if v["mode"] == "bus"]
            for landmark_stop_id in landmark_stop_ids:
                try:
                    route = plan_multi_transfer(
                        origin_stop_id=stop_id,
                        dest_stop_id=landmark_stop_id,
                        arrive_by=None,
                        db=db
                    )
                    if isinstance(route, dict) and route.get("status") == "success":
                        bus_results.append({
                            "landmark_stop_id": landmark_stop_id,
                            "landmark": LANDMARKS[landmark_stop_id],
                            "path": route["path"]
                        })
                except Exception:
                    continue

        best_move = get_best_recommendation(bus_results, walk_spots, gap['gap_start'], gap['duration_minutes'])

        itinerary.append({
            "gap": f"{gap['gap_start']} ({gap['duration_minutes']} min)",
            "origin": origin_bldg,
            "recommendation": best_move or "Stay put: Check the library."
        })

    return {"status": "success", "itinerary": itinerary}

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
async def explore_nearby(
    stop_id: str, 
    business_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    stop_query = text("SELECT stop_lat, stop_lon FROM stops WHERE TRIM(stop_id) = :id")
    stop = db.execute(stop_query, {"id": stop_id}).fetchone()
    
    if not stop:
        raise HTTPException(status_code=404, detail="Stop not found.")
        
    nearby = await get_osm_businesses(stop.stop_lat, stop.stop_lon, business_type, radius=1200, db=db)
    return {"stop_id": stop_id, "filter_applied": business_type, "nearby_businesses": nearby}

@app.get("/plan_trip")
def plan_trip(origin_stop_id: str, dest_stop_id: str, db: Session = Depends(get_db)):
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
        if r.origin_seq < r.dest_seq:
            itinerary.append({
                "route": r.route_short_name,
                "type": "Direct",
                "leave": r.departure_time.strip(),
                "arrive": r.arrival_time.strip(),
                "trip_id": r.trip_id
            })
        else:
            itinerary.append({
                "route": r.route_short_name,
                "type": "Loop (Stay on board)",
                "leave": r.departure_time.strip(),
                "arrive": f"{r.arrival_time.strip()} (Next Loop)",
                "trip_id": r.trip_id
            })

    return itinerary[:5]

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
        except Exception:
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

import heapq
import math

import heapq
import math
from datetime import datetime, timedelta, time

@app.get("/plan_trip/coordinates")
def plan_trip_by_coords(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    arrive_by: Optional[str] = None,
    db: Session = Depends(get_db)
):
    # --- Helper: Haversine Distance ---
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371000
        phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
        dphi = math.radians(float(lat2) - float(lat1))
        dlam = math.radians(float(lon2) - float(lon1))
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    # 1. IMMEDIATE WALK CHECK (< 700 meters)
    direct_dist = haversine(origin_lat, origin_lon, dest_lat, dest_lon)
    if direct_dist <= 700:
        return {
            "status": "success",
            "mode": "walk-only",
            "itinerary": [{
                "action": "Walk",
                "destination": "Final Destination",
                "distance_meters": round(direct_dist),
                "walk_time_minutes": math.ceil(direct_dist / 84) 
            }]
        }

    # 2. SEED MULTIPLE STARTING STOPS (Prevents Nearest-Stop Transfer Bias)
    def get_nearby_stops(lat: float, lon: float):
        query = text("""
            SELECT stop_id, stop_name, stop_lat, stop_lon,
                    ST_Distance(
                        ST_MakePoint(:lon, :lat)\:\:geography,
                        ST_MakePoint(stop_lon, stop_lat)\:\:geography
                    ) as walk_dist
            FROM stops
            ORDER BY walk_dist ASC
            LIMIT 4
        """)
        return db.execute(query, {"lat": lat, "lon": lon}).fetchall()

    orig_stops = get_nearby_stops(origin_lat, origin_lon)
    dest_stops = get_nearby_stops(dest_lat, dest_lon)

    if not orig_stops or not dest_stops:
        raise HTTPException(status_code=404, detail="No transit stops found near these coordinates.")

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

    start_stops = dest_stops if is_time_sensitive else orig_stops
    target_stops = orig_stops if is_time_sensitive else dest_stops
    target_ids = {s.stop_id.strip(): s for s in target_stops}
    
    queue = []
    best_costs = {}
    max_depth = 4 

    # Push ALL 4 nearby stops into the queue
    for s_stop in start_stops:
        s_id = s_stop.stop_id.strip()
        s_g = s_stop.walk_dist
        s_h = haversine(s_stop.stop_lat, s_stop.stop_lon, target_stops[0].stop_lat, target_stops[0].stop_lon)
        
        heapq.heappush(queue, (s_g + s_h, s_g, s_id, [], deadline_str, s_stop.walk_dist))
        best_costs[s_id] = s_g

    while queue:
        f, g, curr_id, path, current_constraint, initial_walk = heapq.heappop(queue)
        
        if len(path) >= max_depth: continue

        order_clause = "ORDER BY st2.arrival_time DESC" if is_time_sensitive else "ORDER BY st1.departure_time ASC"

        query_sql = f"""
            SELECT DISTINCT
                st1.stop_id AS prev_id,
                st2.stop_id AS next_id,
                orig_s.stop_name AS from_name,
                dest_s.stop_name AS to_name,
                dest_s.stop_lat AS next_lat,
                dest_s.stop_lon AS next_lon,
                r.route_short_name,
                st1.departure_time,
                st2.arrival_time,
                tr.walk_meters,
                st1.trip_id
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
        except Exception:
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
                "route": route_name, "from": from_name, "to": to_name,
                "from_id": prev_id, "to_id": next_id, "walk_meters": round(dist),
                "trip_id": row.trip_id.strip() if hasattr(row, 'trip_id') and row.trip_id else None
            }
            
            time_penalty = 0 # NEW: Start with 0 time penalty

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
                    
                    # NEW: Calculate how many seconds "too early" this bus is!
                    target_sec = constraint_obj.hour * 3600 + constraint_obj.minute * 60 + constraint_obj.second
                    arr_sec = arr_obj.hour * 3600 + arr_obj.minute * 60 + arr_obj.second
                    time_diff = target_sec - arr_sec
                    if time_diff < 0: time_diff += 86400
                    
                    # Multiply by 5 to make waiting time severely penalize the route's score
                    time_penalty = time_diff * 5 

                    new_constraint_str = dep_time_str
                    new_path = [leg] + path
                except Exception:
                    continue 
            else:
                new_path = path + [leg]
                new_constraint_str = None
            
            # Destination reached!
            if next_search_id in target_ids:
                final_walk = target_ids[next_search_id].walk_dist
                readable_itinerary = []
                
                for i, step in enumerate(new_path):
                    if i == 0:
                        total_start_walk = initial_walk + step.get("walk_meters", 0)
                        if total_start_walk > 0:
                            readable_itinerary.append({
                                "action": "Walk", "destination": step["from"], 
                                "distance_meters": total_start_walk, "walk_time_minutes": math.ceil(total_start_walk / 84)
                            })
                    else:
                        if step.get("walk_meters", 0) > 0:
                            readable_itinerary.append({
                                "action": "Walk", "destination": step["from"], 
                                "distance_meters": step["walk_meters"], "walk_time_minutes": math.ceil(step["walk_meters"] / 84)
                            })
                    
                    transit_leg = {
                        "action": "Ride Bus", "route": step["route"], "from": step["from"], "to": step["to"],
                        "from_id": step.get("from_id"), "to_id": step.get("to_id"), "trip_id": step.get("trip_id")
                    }
                    if is_time_sensitive:
                        transit_leg["departure"] = step["departure"]
                        transit_leg["arrival"] = step["arrival"]
                        
                    readable_itinerary.append(transit_leg)

                if final_walk > 0:
                    readable_itinerary.append({
                        "action": "Walk", "destination": "Final Destination", 
                        "distance_meters": final_walk, "walk_time_minutes": math.ceil(final_walk / 84)
                    })

                return {
                    "status": "success", 
                    "mode": "time-constrained" if is_time_sensitive else "generic",
                    "itinerary": readable_itinerary
                }

            is_anteater = "anteater" in (row.trip_id.lower() if row.trip_id else "")
            agency_penalty = 0 if is_anteater else 50000 
            
            # NEW: Add the time_penalty to the total cost function!
            new_g = g + 10000 + dist + agency_penalty + time_penalty
            
            h = haversine(row.next_lat, row.next_lon, target_stops[0].stop_lat, target_stops[0].stop_lon)
            new_f = new_g + h

            if next_search_id not in best_costs or new_g < best_costs[next_search_id]:
                best_costs[next_search_id] = new_g
                heapq.heappush(queue, (new_f, new_g, next_search_id, new_path, new_constraint_str, initial_walk))

    raise HTTPException(status_code=404, detail="No route found between these coordinates.")

@app.get("/stops/", response_model=List[StopResponse])
def get_stops(
    min_lat: Optional[float] = None,
    max_lat: Optional[float] = None,
    min_lon: Optional[float] = None,
    max_lon: Optional[float] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Stop)
    
    if all(v is not None for v in [min_lat, max_lat, min_lon, max_lon]):
        query = query.filter(
            Stop.stop_lat >= min_lat,
            Stop.stop_lat <= max_lat,
            Stop.stop_lon >= min_lon,
            Stop.stop_lon <= max_lon
        )
        
    return query.all()

@app.get("/shape/{trip_id}")
def get_shape(trip_id: str, start_stop_id: Optional[str] = None, end_stop_id: Optional[str] = None, db: Session = Depends(get_db)):
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371000
        phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
        dphi = math.radians(float(lat2) - float(lat1))
        dlam = math.radians(float(lon2) - float(lon1))
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    query_shape = text("""
        SELECT CAST(s.shape_pt_lat AS FLOAT) as lat, 
               CAST(s.shape_pt_lon AS FLOAT) as lon
        FROM shapes s
        JOIN trips t ON s.shape_id = t.shape_id
        WHERE TRIM(t.trip_id) = TRIM(:trip_id)
        ORDER BY CAST(s.shape_pt_sequence AS INTEGER) ASC
    """)
    shape_results = db.execute(query_shape, {"trip_id": trip_id}).fetchall()
    
    coordinates = []
    
    if shape_results:
        coordinates = [[r.lon, r.lat] for r in shape_results]
        
        if start_stop_id and end_stop_id and len(coordinates) > 0:
            start_stop = db.execute(text("SELECT CAST(stop_lat AS FLOAT) as lat, CAST(stop_lon AS FLOAT) as lon FROM stops WHERE TRIM(stop_id) = :id"), {"id": start_stop_id}).fetchone()
            end_stop = db.execute(text("SELECT CAST(stop_lat AS FLOAT) as lat, CAST(stop_lon AS FLOAT) as lon FROM stops WHERE TRIM(stop_id) = :id"), {"id": end_stop_id}).fetchone()
            
            if start_stop and end_stop:
                start_idx = min(range(len(coordinates)), key=lambda i: haversine(start_stop.lat, start_stop.lon, coordinates[i][1], coordinates[i][0]))
                end_idx = min(range(len(coordinates)), key=lambda i: haversine(end_stop.lat, end_stop.lon, coordinates[i][1], coordinates[i][0]))
                
                if start_idx <= end_idx:
                    coordinates = coordinates[start_idx:end_idx+1]
                else:
                    coordinates = coordinates[start_idx:] + coordinates[:end_idx+1]
    else:
        query_stops = text("""
            SELECT CAST(s.stop_lon AS FLOAT) as lon, CAST(s.stop_lat AS FLOAT) as lat
            FROM stop_times st
            JOIN stops s ON TRIM(st.stop_id) = TRIM(s.stop_id)
            WHERE TRIM(st.trip_id) = TRIM(:trip_id)
            ORDER BY CAST(st.stop_sequence AS INTEGER) ASC
        """)
        stop_results = db.execute(query_stops, {"trip_id": trip_id}).fetchall()
        if not stop_results:
            raise HTTPException(status_code=404, detail="Shape not found")
        coordinates = [[r.lon, r.lat] for r in stop_results]

    if len(coordinates) == 1:
        coordinates.append(coordinates[0])

    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates
        }
    }