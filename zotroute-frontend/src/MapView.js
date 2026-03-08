import React, { useState, useEffect, useRef, useCallback } from "react";
import Map, { Marker, Popup, Source, Layer } from "react-map-gl";
import "mapbox-gl/dist/mapbox-gl.css";

const MAPBOX_TOKEN = process.env.REACT_APP_MAPBOX_TOKEN;

function MapView({ filter }) {
  const [popupInfo, setPopupInfo] = useState(null);
  const [busStops, setBusStops] = useState([]);
  const mapRef = useRef();

  // State for routing
  const [origin, setOrigin] = useState(null);
  const [destination, setDestination] = useState(null);
  const [routeGeoJSON, setRouteGeoJSON] = useState(null);
  const [walkGeoJSON, setWalkGeoJSON] = useState(null); 
  const [itinerary, setItinerary] = useState([]);
  const [usedStopIds, setUsedStopIds] = useState([]);
  
  // State for Progress Bar, Time, and Nearby Places
  const [isLoading, setIsLoading] = useState(false);
  const [arriveByTime, setArriveByTime] = useState("");
  const [explorePlaces, setExplorePlaces] = useState([]); 
  const [businessType, setBusinessType] = useState("cafe");

  const fetchStopsInBounds = useCallback(async () => {
    if (!mapRef.current) return;
    const bounds = mapRef.current.getBounds();
    try {
      const response = await fetch(
        `http://localhost:8000/stops/?min_lat=${bounds.getSouth()}&max_lat=${bounds.getNorth()}&min_lon=${bounds.getWest()}&max_lon=${bounds.getEast()}`
      );
      const data = await response.json();
      setBusStops(data.map(stop => ({
        id: stop.stop_id, 
        name: stop.stop_name, 
        lat: stop.stop_lat, 
        long: stop.stop_lon,
        route: stop.stop_id.startsWith("anteater-express") ? "AntExp" : "OCTA"
      })));
    } catch (error) { 
      console.error("Failed to fetch stops in bounds:", error); 
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => fetchStopsInBounds(), 500);
    return () => clearTimeout(timer);
  }, [fetchStopsInBounds]);

  const handleMapClick = async (e) => {
    const { lng, lat } = e.lngLat;
    
    if (!origin) {
      setOrigin({ lng, lat });
    } else if (!destination) {
      setDestination({ lng, lat });
      planTrip(origin.lat, origin.lng, lat, lng, arriveByTime);
    } else {
      clearRoute();
      setOrigin({ lng, lat });
    }
  };

  const clearRoute = () => {
    setOrigin(null);
    setDestination(null);
    setRouteGeoJSON(null);
    setWalkGeoJSON(null);
    setItinerary([]);
    setUsedStopIds([]);
    setExplorePlaces([]); 
  }

  const handleTimeChange = (e) => {
    const newTime = e.target.value;
    setArriveByTime(newTime);
    if (origin && destination) {
      planTrip(origin.lat, origin.lng, destination.lat, destination.lng, newTime);
    }
  };

  const fetchExplorePlaces = async (stops, type) => {
    if (!stops || stops.length === 0) {
      setExplorePlaces([]);
      return;
    }
    try {
      const placesPromises = stops.map(id => 
        fetch(`http://localhost:8000/recommend/explore?stop_id=${id}&business_type=${type}`)
          .then(r => r.json())
          .then(data => data.nearby_businesses ? data.nearby_businesses.slice(0, 5) : [])
      );
      const placesArrays = await Promise.all(placesPromises);
      setExplorePlaces(placesArrays.flat()); 
    } catch (error) {
      console.error("Failed to fetch places", error);
    }
  };

  const handleBusinessTypeChange = (e) => {
    const newType = e.target.value;
    setBusinessType(newType);
    if (usedStopIds.length > 0) {
      fetchExplorePlaces(usedStopIds, newType);
    }
  };

  // --- NEW: Handle Geolocation (Locate Me) ---
  const handleLocateMe = () => {
    if (!navigator.geolocation) {
      alert("Geolocation is not supported by your browser.");
      return;
    }

    setIsLoading(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords;
        setOrigin({ lat: latitude, lng: longitude });
        setIsLoading(false);

        // Smoothly pan the map to the user's location
        mapRef.current?.flyTo({ center: [longitude, latitude], zoom: 15, duration: 1500 });

        // If they already picked a destination, plan the trip immediately
        if (destination) {
          planTrip(latitude, longitude, destination.lat, destination.lng, arriveByTime);
        }
      },
      (error) => {
        console.error("Error fetching location", error);
        alert("Unable to retrieve your location. Please check your browser permissions.");
        setIsLoading(false);
      }
    );
  };

  const planTrip = async (startLat, startLon, endLat, endLon, timeOverride = "") => {
    setIsLoading(true); 
    
    try {
      let url = `http://localhost:8000/plan_trip/coordinates?origin_lat=${startLat}&origin_lon=${startLon}&dest_lat=${endLat}&dest_lon=${endLon}`;
      if (timeOverride) {
        url += `&arrive_by=${timeOverride}`;
      }

      const res = await fetch(url);
      if (!res.ok) {
          alert("No routes found between these areas for the selected time.");
          setDestination(null); 
          setRouteGeoJSON(null);
          setWalkGeoJSON(null);
          setItinerary([]);
          setExplorePlaces([]);
          return;
      }
      
      const data = await res.json();
      setItinerary(data.itinerary);

      const usedIds = [];
      const busLegs = [];

      data.itinerary.forEach(step => {
        if (step.action === "Ride Bus" && step.trip_id) {
          if (step.from_id) usedIds.push(step.from_id);
          if (step.to_id) usedIds.push(step.to_id);
          busLegs.push(step);
        }
      });
      
      const uniqueUsedIds = [...new Set(usedIds)];
      setUsedStopIds(uniqueUsedIds);

      fetchExplorePlaces(uniqueUsedIds, businessType);

      if (busLegs.length > 0) {
        const shapePromises = busLegs.map(leg => 
          fetch(`http://localhost:8000/shape/${leg.trip_id}?start_stop_id=${leg.from_id}&end_stop_id=${leg.to_id}`)
            .then(r => r.json())
        );
        
        const shapes = await Promise.all(shapePromises);
        setRouteGeoJSON({ type: "FeatureCollection", features: shapes });

        const firstBus = busLegs[0];
        const lastBus = busLegs[busLegs.length - 1];

        const boardStop = busStops.find(s => s.id === firstBus.from_id);
        const alightStop = busStops.find(s => s.id === lastBus.to_id);
        
        if (boardStop && alightStop) {
          setWalkGeoJSON({
            type: "FeatureCollection",
            features: [
              { type: "Feature", geometry: { type: "LineString", coordinates: [[startLon, startLat], [boardStop.long, boardStop.lat]] } },
              { type: "Feature", geometry: { type: "LineString", coordinates: [[alightStop.long, alightStop.lat], [endLon, endLat]] } }
            ]
          });
        }
      } else {
        setRouteGeoJSON(null);
        setWalkGeoJSON({
          type: "FeatureCollection",
          features: [
            { type: "Feature", geometry: { type: "LineString", coordinates: [[startLon, startLat], [endLon, endLat]] } }
          ]
        });
      }
    } catch (error) {
      console.error("Failed to plan trip", error);
    } finally {
      setIsLoading(false); 
    }
  };

  const routeLayerStyle = {
    id: 'bus-route',
    type: 'line',
    paint: { 'line-color': '#0064A4', 'line-width': 5, 'line-opacity': 0.8 }
  };

  const walkLayerStyle = {
    id: 'walk-route',
    type: 'line',
    paint: { 'line-color': '#7f8c8d', 'line-width': 4, 'line-dasharray': [2, 2] }
  };

  return (
    <div style={{ position: "relative", overflow: "hidden" }}>

      <div style={{ 
        position: "absolute", top: 90, left: 15, zIndex: 99999, background: "white", 
        padding: 15, borderRadius: 8, boxShadow: "0 4px 12px rgba(0,0,0,0.15)", 
        maxHeight: "calc(100vh - 120px)", overflowY: "auto", minWidth: "280px" 
      }}>
        
        {/* NEW: Locate Me Button */}
        <button 
          onClick={handleLocateMe}
          style={{ 
            width: "100%", padding: "10px", marginBottom: "15px", cursor: "pointer", 
            background: "#2ECC71", color: "white", border: "none", borderRadius: "4px", 
            fontWeight: "bold", fontSize: "14px", display: "flex", alignItems: "center", justifyContent: "center", gap: "5px"
          }}
        >
          📍 Use Current Location
        </button>

        {/* Time Picker */}
        <div>
          <label style={{ fontSize: "14px", fontWeight: "bold", color: "#333", display: "block", marginBottom: "5px" }}>Arrive By (Optional):</label>
          <input 
            type="time" 
            value={arriveByTime} 
            onChange={handleTimeChange}
            style={{ padding: "8px", borderRadius: "4px", border: "1px solid #ccc", width: "100%", boxSizing: "border-box", outline: "none", fontFamily: "inherit" }}
          />
        </div>

        {/* Explore Nearby Dropdown */}
        <div style={{ marginTop: "15px" }}>
          <label style={{ fontSize: "14px", fontWeight: "bold", color: "#333", display: "block", marginBottom: "5px" }}>Explore Nearby:</label>
          <select 
            value={businessType} 
            onChange={handleBusinessTypeChange}
            style={{ padding: "8px", borderRadius: "4px", border: "1px solid #ccc", width: "100%", boxSizing: "border-box", outline: "none", fontFamily: "inherit", cursor: "pointer", backgroundColor: "#f9f9f9" }}
          >
            <option value="cafe">Coffee & Cafes ☕</option>
            <option value="food">Restaurants & Food 🍔</option>
            <option value="shop">Retail & Shopping 🛍️</option>
            <option value="bar">Bars & Nightlife 🍻</option>
          </select>
          {!origin && !destination && (
            <p style={{ margin: "12px 0 0 0", fontSize: "12px", color: "#666", fontStyle: "italic", textAlign: "center" }}>
              Click the map to set Origin & Destination.
            </p>
          )}
        </div>

        <style>{`@keyframes loading-bar { 0% { transform: translateX(-100%); } 100% { transform: translateX(350%); } }`}</style>
        
        {isLoading && (
          <div style={{ marginTop: 15, padding: "10px", backgroundColor: "#e8f4f8", borderRadius: "4px", color: "#0064A4", fontWeight: "bold", textAlign: "center" }}>
            ⏳ Calculating best route...
          </div>
        )}

        {itinerary.length > 0 && !isLoading && (
          <div style={{ marginTop: 15, borderTop: "1px solid #eee", paddingTop: 15 }}>
            <h3 style={{ margin: "0 0 10px 0" }}>Your Route</h3>
            {itinerary.map((step, idx) => (
              <div key={idx} style={{ marginBottom: 12, fontSize: "14px" }}>
                {step.action === "Walk" ? (
                  <span>🚶 <b>Walk {step.walk_time_minutes} min</b> <span style={{fontSize: "12px", color: "#666"}}>({step.distance_meters}m)</span> to {step.destination}</span>
                ) : (
                  <span>
                    🚌 <b>Ride Route {step.route}</b> <br/> 
                    <span style={{ fontSize: "12px", color: "#555" }}>
                      {step.departure} {step.from} <br/>
                      ↓ <br/>
                      {step.arrival} {step.to}
                    </span>
                  </span>
                )}
              </div>
            ))}
            <button 
              onClick={clearRoute} 
              style={{ marginTop: 10, width: "100%", padding: "8px", cursor: "pointer", background: "#f0f0f0", border: "1px solid #ccc", borderRadius: "4px", fontWeight: "bold", color: "#e74c3c" }}
            >
              Clear Route
            </button>
          </div>
        )}
      </div>

      <Map
        ref={mapRef}
        initialViewState={{ longitude: -117.8425, latitude: 33.647, zoom: 14.5 }}
        maxBounds={[
          [-118.2500, 33.3500],
          [-117.4000, 33.9500] 
        ]}
        style={{ width: "100vw", height: "100vh" }}
        mapStyle="mapbox://styles/mapbox/streets-v12"
        mapboxAccessToken={MAPBOX_TOKEN}
        onMoveEnd={fetchStopsInBounds}
        onClick={handleMapClick}
        interactiveLayerIds={['bus-stops']}
        cursor={origin && !destination ? "crosshair" : "grab"}
      >
        {origin && <Marker longitude={origin.lng} latitude={origin.lat} color="#2ECC71" />}
        {destination && <Marker longitude={destination.lng} latitude={destination.lat} color="#E74C3C" />}

        {walkGeoJSON && (
          <Source id="walk-source" type="geojson" data={walkGeoJSON}>
            <Layer {...walkLayerStyle} />
          </Source>
        )}

        {routeGeoJSON && (
          <Source id="route-source" type="geojson" data={routeGeoJSON}>
            <Layer {...routeLayerStyle} />
          </Source>
        )}

        {itinerary.length > 0 && busStops
          .filter(stop => usedStopIds.includes(stop.id)) 
          .map(stop => (
            <Marker key={stop.id} longitude={stop.long} latitude={stop.lat} color={stop.route === "AntExp" ? "#0064A4" : "#FF6B35"}
              onClick={e => { e.originalEvent.stopPropagation(); setPopupInfo(stop); }} 
            />
          ))
        }

        {explorePlaces.map((place, idx) => (
          <Marker key={`place-${idx}`} longitude={place.lon} latitude={place.lat} color="#9B59B6"
            onClick={e => { 
              e.originalEvent.stopPropagation(); 
              setPopupInfo({ name: place.name, route: place.category, lat: place.lat, long: place.lon }); 
            }} 
          />
        ))}

        {popupInfo && (
          <Popup longitude={popupInfo.long} latitude={popupInfo.lat} onClose={() => setPopupInfo(null)} closeOnClick={false}>
            <div>
              <h3 style={{ margin: "0 0 5px 0" }}>{popupInfo.name}</h3>
              <p style={{ margin: 0, fontSize: "12px", textTransform: "capitalize" }}>{popupInfo.route}</p>
            </div>
          </Popup>
        )}
      </Map>
    </div>
  );
}

export default MapView;