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
  const [walkGeoJSON, setWalkGeoJSON] = useState(null); // <-- NEW: Holds dashed lines
  const [itinerary, setItinerary] = useState([]);
  const [usedStopIds, setUsedStopIds] = useState([]);   // <-- NEW: Tracks which stops to draw

  // Fetch only the stops visible on the current map screen
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

  // Initial load
  useEffect(() => {
    const timer = setTimeout(() => fetchStopsInBounds(), 500);
    return () => clearTimeout(timer);
  }, [fetchStopsInBounds]);

  // Handle Map Clicks to set Origin and Destination pins
  const handleMapClick = async (e) => {
    const { lng, lat } = e.lngLat;
    
    if (!origin) {
      setOrigin({ lng, lat });
    } else if (!destination) {
      setDestination({ lng, lat });
      planTrip(origin.lat, origin.lng, lat, lng);
    } else {
      // Clear the board on 3rd click
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
  }

  // Plan the trip and draw the sliced shape + dashed lines
// Plan the trip and draw the sliced shape + dashed lines
  const planTrip = async (startLat, startLon, endLat, endLon) => {
    try {
      const res = await fetch(`http://localhost:8000/plan_trip/coordinates?origin_lat=${startLat}&origin_lon=${startLon}&dest_lat=${endLat}&dest_lon=${endLon}`);
      if (!res.ok) {
          alert("No routes found between these areas.");
          setDestination(null); 
          return;
      }
      const data = await res.json();
      setItinerary(data.itinerary);

      // Collect ALL bus legs in case of transfers
      const usedIds = [];
      const busLegs = [];

      data.itinerary.forEach(step => {
        if (step.action === "Ride Bus" && step.trip_id) {
          if (step.from_id) usedIds.push(step.from_id);
          if (step.to_id) usedIds.push(step.to_id);
          busLegs.push(step);
        }
      });
      setUsedStopIds(usedIds);

      // Fetch shapes for ALL buses involved in the trip
      if (busLegs.length > 0) {
        const shapePromises = busLegs.map(leg => 
          fetch(`http://localhost:8000/shape/${leg.trip_id}?start_stop_id=${leg.from_id}&end_stop_id=${leg.to_id}`)
            .then(r => r.json())
        );
        
        const shapes = await Promise.all(shapePromises);
        
        // Combine multiple bus lines into one map layer
        setRouteGeoJSON({
          type: "FeatureCollection",
          features: shapes
        });

        // Draw dashed lines from Origin to the FIRST bus, and LAST bus to Destination
        const firstBus = busLegs[0];
        const lastBus = busLegs[busLegs.length - 1];

        const boardStop = busStops.find(s => s.id === firstBus.from_id);
        const alightStop = busStops.find(s => s.id === lastBus.to_id);
        
        if (boardStop && alightStop) {
          setWalkGeoJSON({
            type: "FeatureCollection",
            features: [
              { // Walk to first bus stop
                type: "Feature",
                geometry: { type: "LineString", coordinates: [[startLon, startLat], [boardStop.long, boardStop.lat]] }
              },
              { // Walk from last bus stop to destination
                type: "Feature",
                geometry: { type: "LineString", coordinates: [[alightStop.long, alightStop.lat], [endLon, endLat]] }
              }
            ]
          });
        }
      }
    } catch (error) {
      console.error("Failed to plan trip", error);
    }
  };

  // Mapbox Styling for the Solid Blue Bus Route
  const routeLayerStyle = {
    id: 'bus-route',
    type: 'line',
    paint: {
      'line-color': '#0064A4', 
      'line-width': 5,
      'line-opacity': 0.8
    }
  };

  // Mapbox Styling for the Dashed Gray Walking Path
  const walkLayerStyle = {
    id: 'walk-route',
    type: 'line',
    paint: {
      'line-color': '#7f8c8d', 
      'line-width': 4,
      'line-dasharray': [2, 2] // <-- This makes it dashed!
    }
  };

  return (
    <div style={{ position: "relative" }}>
      {/* Small UI Overlay */}
      {itinerary.length > 0 && (
        <div style={{ position: "absolute", top: 10, left: 10, zIndex: 10, background: "white", padding: 15, borderRadius: 8, boxShadow: "0 4px 6px rgba(0,0,0,0.1)", maxHeight: "400px", overflowY: "auto", minWidth: "250px" }}>
          <h3 style={{ margin: "0 0 10px 0" }}>Your Route</h3>
          {itinerary.map((step, idx) => (
            <div key={idx} style={{ marginBottom: 12, fontSize: "14px" }}>
              {step.action === "Walk" ? (
                <span>🚶 <b>Walk {step.distance_meters}m</b> to {step.destination}</span>
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
          <button onClick={clearRoute} style={{ marginTop: 10, width: "100%", padding: "8px", cursor: "pointer", background: "#f0f0f0", border: "1px solid #ccc", borderRadius: "4px" }}>
            Clear Route
          </button>
        </div>
      )}

      {/* The Actual Map */}
      <Map
        ref={mapRef}
        initialViewState={{ longitude: -117.8425, latitude: 33.647, zoom: 14.5 }}
        style={{ width: "100vw", height: "100vh" }}
        mapStyle="mapbox://styles/mapbox/streets-v12"
        mapboxAccessToken={MAPBOX_TOKEN}
        onMoveEnd={fetchStopsInBounds}
        onClick={handleMapClick}
        interactiveLayerIds={['bus-stops']}
        cursor={origin && !destination ? "crosshair" : "grab"}
      >
        {/* Draw User Pins */}
        {origin && <Marker longitude={origin.lng} latitude={origin.lat} color="#2ECC71" />}
        {destination && <Marker longitude={destination.lng} latitude={destination.lat} color="#E74C3C" />}

        {/* Draw Dashed Walking Paths */}
        {walkGeoJSON && (
          <Source id="walk-source" type="geojson" data={walkGeoJSON}>
            <Layer {...walkLayerStyle} />
          </Source>
        )}

        {/* Draw Solid Bus Route Shape */}
        {routeGeoJSON && (
          <Source id="route-source" type="geojson" data={routeGeoJSON}>
            <Layer {...routeLayerStyle} />
          </Source>
        )}

        {/* Draw Bus Stops ONLY if they are used in the itinerary! */}
        {itinerary.length > 0 && busStops
          .filter(stop => usedStopIds.includes(stop.id)) // Filters out all unused stops
          .map(stop => (
            <Marker key={stop.id} longitude={stop.long} latitude={stop.lat} color={stop.route === "AntExp" ? "#0064A4" : "#FF6B35"}
              onClick={e => { e.originalEvent.stopPropagation(); setPopupInfo(stop); }} 
            />
          ))
        }

        {/* Draw Popup for clicked Bus Stops */}
        {popupInfo && (
          <Popup longitude={popupInfo.long} latitude={popupInfo.lat} onClose={() => setPopupInfo(null)} closeOnClick={false}>
            <div>
              <h3 style={{ margin: "0 0 5px 0" }}>{popupInfo.name}</h3>
              <p style={{ margin: 0, fontSize: "12px" }}>Agency: {popupInfo.route}</p>
            </div>
          </Popup>
        )}
      </Map>
    </div>
  );
}

export default MapView;