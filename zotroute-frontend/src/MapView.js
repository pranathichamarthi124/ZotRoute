import React, { useState, useEffect, useRef, useCallback } from "react";
import Map, { Marker, Popup, Source, Layer } from "react-map-gl";
import "mapbox-gl/dist/mapbox-gl.css";

const MAPBOX_TOKEN = process.env.REACT_APP_MAPBOX_TOKEN;
const controlBtnStyle = {
  width: 36,
  height: 36,
  borderRadius: 6,
  border: "1px solid #ccc",
  background: "white",
  cursor: "pointer",
  fontSize: "18px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  boxShadow: "0 2px 6px rgba(0,0,0,0.15)",
};

function MapView({ filter, isPanelOpen, setIsPanelOpen }) {
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
  const [mapStyle, setMapStyle] = useState(
    "mapbox://styles/mapbox/streets-v12",
  );
  const [showLayerMenu, setShowLayerMenu] = useState(false);

  const fetchStopsInBounds = useCallback(async () => {
    if (!mapRef.current) return;
    const bounds = mapRef.current.getBounds();
    try {
      const response = await fetch(
        `http://localhost:8000/stops/?min_lat=${bounds.getSouth()}&max_lat=${bounds.getNorth()}&min_lon=${bounds.getWest()}&max_lon=${bounds.getEast()}`,
      );
      const data = await response.json();
      setBusStops(
        data.map((stop) => ({
          id: stop.stop_id,
          name: stop.stop_name,
          lat: stop.stop_lat,
          long: stop.stop_lon,
          route: stop.stop_id.startsWith("anteater-express")
            ? "AntExp"
            : "OCTA",
        })),
      );
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
  };

  const handleTimeChange = (e) => {
    const newTime = e.target.value;
    setArriveByTime(newTime);
    if (origin && destination) {
      planTrip(
        origin.lat,
        origin.lng,
        destination.lat,
        destination.lng,
        newTime,
      );
    }
  };

  const fetchExplorePlaces = async (stops, type) => {
    if (!stops || stops.length === 0) {
      setExplorePlaces([]);
      return;
    }
    try {
      const placesPromises = stops.map((id) =>
        fetch(
          `http://localhost:8000/recommend/explore?stop_id=${id}&business_type=${type}`,
        )
          .then((r) => r.json())
          .then((data) =>
            data.nearby_businesses ? data.nearby_businesses.slice(0, 5) : [],
          ),
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

        // user's location
        mapRef.current?.flyTo({
          center: [longitude, latitude],
          zoom: 15,
          duration: 1500,
        });

        // plan trip if destination if chosen by user
        if (destination) {
          planTrip(
            latitude,
            longitude,
            destination.lat,
            destination.lng,
            arriveByTime,
          );
        }
      },
      (error) => {
        console.error("Error fetching location", error);
        alert(
          "Unable to retrieve your location. Please check your browser permissions.",
        );
        setIsLoading(false);
      },
    );
  };

  const planTrip = async (
    startLat,
    startLon,
    endLat,
    endLon,
    timeOverride = "",
  ) => {
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

      data.itinerary.forEach((step) => {
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
        const shapePromises = busLegs.map((leg) =>
          fetch(
            `http://localhost:8000/shape/${leg.trip_id}?start_stop_id=${leg.from_id}&end_stop_id=${leg.to_id}`,
          ).then((r) => r.json()),
        );

        const shapes = await Promise.all(shapePromises);
        setRouteGeoJSON({ type: "FeatureCollection", features: shapes });

        const firstBus = busLegs[0];
        const lastBus = busLegs[busLegs.length - 1];

        const boardStop = busStops.find((s) => s.id === firstBus.from_id);
        const alightStop = busStops.find((s) => s.id === lastBus.to_id);

        if (boardStop && alightStop) {
          setWalkGeoJSON({
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                geometry: {
                  type: "LineString",
                  coordinates: [
                    [startLon, startLat],
                    [boardStop.long, boardStop.lat],
                  ],
                },
              },
              {
                type: "Feature",
                geometry: {
                  type: "LineString",
                  coordinates: [
                    [alightStop.long, alightStop.lat],
                    [endLon, endLat],
                  ],
                },
              },
            ],
          });
        }
      } else {
        setRouteGeoJSON(null);
        setWalkGeoJSON({
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: {
                type: "LineString",
                coordinates: [
                  [startLon, startLat],
                  [endLon, endLat],
                ],
              },
            },
          ],
        });
      }
    } catch (error) {
      console.error("Failed to plan trip", error);
    } finally {
      setIsLoading(false);
    }
  };

  const routeLayerStyle = {
    id: "bus-route",
    type: "line",
    paint: { "line-color": "#0064A4", "line-width": 5, "line-opacity": 0.8 },
  };

  const walkLayerStyle = {
    id: "walk-route",
    type: "line",
    paint: {
      "line-color": "#7f8c8d",
      "line-width": 4,
      "line-dasharray": [2, 2],
    },
  };

  return (
    <>
      {/* Collapsible Panel */}
      <div
        style={{
          position: "fixed",
          left: isPanelOpen ? "0" : "-350px",
          top: "72px",
          width: "350px",
          height: "calc(100vh - 72px)",
          background: "#95c8d8",
          padding: 15,
          overflowY: "auto",
          boxShadow: isPanelOpen ? "2px 0 8px rgba(0, 0, 0, 0.1)" : "none",
          zIndex: 1000,
          transition: "left 0.3s ease",
        }}
      >
        {/* Close button - INSIDE panel, only when open */}
        {isPanelOpen && (
          <button
            onClick={() => setIsPanelOpen(false)}
            style={{
              position: "absolute",
              top: "10px",
              right: "10px",
              width: "32px",
              height: "32px",
              borderRadius: "50%",
              border: "1px solid #ccc",
              background: "white",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 2px 6px rgba(0,0,0,0.15)",
              zIndex: 10001,
              fontSize: "16px",
            }}
          >
            ←
          </button>
        )}

        {isPanelOpen && (
          <>
            {/* All your panel content */}
            <button
              onClick={handleLocateMe}
              style={{
                width: "100%",
                padding: "10px",
                marginBottom: "15px",
                marginTop: "35px",
                cursor: "pointer",
                background: "#146938",
                color: "white",
                border: "none",
                borderRadius: "4px",
                fontWeight: "bold",
                fontSize: "14px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "5px",
              }}
            >
              📍 Use Current Location
            </button>

            <div>
              <label
                style={{
                  fontSize: "14px",
                  fontWeight: "bold",
                  color: "#333",
                  display: "block",
                  marginBottom: "5px",
                }}
              >
                Arrive By (Optional):
              </label>
              <input
                type="time"
                value={arriveByTime}
                onChange={handleTimeChange}
                style={{
                  padding: "8px",
                  borderRadius: "4px",
                  border: "1px solid #ccc",
                  width: "100%",
                  boxSizing: "border-box",
                  outline: "none",
                  fontFamily: "inherit",
                }}
              />
            </div>

            <div style={{ marginTop: "15px" }}>
              <label
                style={{
                  fontSize: "14px",
                  fontWeight: "bold",
                  color: "#333",
                  display: "block",
                  marginBottom: "5px",
                }}
              >
                Explore Nearby:
              </label>
              <select
                value={businessType}
                onChange={handleBusinessTypeChange}
                style={{
                  padding: "8px",
                  borderRadius: "4px",
                  border: "1px solid #ccc",
                  width: "100%",
                  boxSizing: "border-box",
                  outline: "none",
                  fontFamily: "inherit",
                  cursor: "pointer",
                  backgroundColor: "#f9f9f9",
                }}
              >
                <option value="cafe">Coffee & Cafes ☕</option>
                <option value="food">Restaurants & Food 🍔</option>
                <option value="shop">Retail & Shopping 🛍️</option>
                <option value="bar">Bars & Nightlife 🍻</option>
              </select>
              {!origin && !destination && (
                <p
                  style={{
                    margin: "12px 0 0 0",
                    fontSize: "12px",
                    color: "#666",
                    fontStyle: "italic",
                    textAlign: "center",
                  }}
                >
                  Click the map to set Origin & Destination.
                </p>
              )}
            </div>

            {isLoading && (
              <div
                style={{
                  marginTop: 15,
                  padding: "10px",
                  backgroundColor: "#e8f4f8",
                  borderRadius: "4px",
                  color: "#0064A4",
                  fontWeight: "bold",
                  textAlign: "center",
                }}
              >
                ⏳ Calculating best route...
              </div>
            )}

            {itinerary.length > 0 && !isLoading && (
              <div
                style={{
                  marginTop: 15,
                  borderTop: "1px solid #eee",
                  paddingTop: 15,
                }}
              >
                <h3 style={{ margin: "0 0 10px 0" }}>Your Route</h3>
                {itinerary.map((step, idx) => (
                  <div key={idx} style={{ marginBottom: 12, fontSize: "14px" }}>
                    {step.action === "Walk" ? (
                      <span>
                        🚶 <b>Walk {step.walk_time_minutes} min</b>{" "}
                        <span style={{ fontSize: "12px", color: "#666" }}>
                          ({step.distance_meters}m)
                        </span>{" "}
                        to {step.destination}
                      </span>
                    ) : (
                      <span>
                        🚌 <b>Ride Route {step.route}</b> <br />
                        <span style={{ fontSize: "12px", color: "#555" }}>
                          {step.departure} {step.from} <br />
                          ↓ <br />
                          {step.arrival} {step.to}
                        </span>
                      </span>
                    )}
                  </div>
                ))}
                <button
                  onClick={clearRoute}
                  style={{
                    marginTop: 10,
                    width: "100%",
                    padding: "8px",
                    cursor: "pointer",
                    background: "#ffffff",
                    border: "1px solid #ccc",
                    borderRadius: "4px",
                    fontWeight: "bold",
                    color: "#e74c3c",
                  }}
                >
                  Clear Route
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Open button - OUTSIDE panel, only when closed */}
      {!isPanelOpen && (
        <button
          onClick={() => setIsPanelOpen(true)}
          style={{
            position: "fixed",
            top: "90px",
            left: "10px",
            width: "40px",
            height: "40px",
            borderRadius: "50%",
            border: "1px solid #ccc",
            background: "white",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: "0 2px 6px rgba(0,0,0,0.15)",
            zIndex: 10001,
            fontSize: "18px",
          }}
        >
          →
        </button>
      )}

      {/* Map - takes full viewport, panel slides over it */}
      <div style={{ height: "calc(100vh - 72px)", marginTop: "72px" }}>
        <Map
          ref={mapRef}
          initialViewState={{
            longitude: -117.8425,
            latitude: 33.647,
            zoom: 14.5,
          }}
          maxBounds={[
            [-118.25, 33.35],
            [-117.4, 33.95],
          ]}
          style={{ width: "100%", height: "100%" }}
          mapStyle={mapStyle}
          mapboxAccessToken={MAPBOX_TOKEN}
          onMoveEnd={fetchStopsInBounds}
          onClick={handleMapClick}
          interactiveLayerIds={["bus-stops"]}
          cursor={origin && !destination ? "crosshair" : "grab"}
        >
          {origin && (
            <Marker
              longitude={origin.lng}
              latitude={origin.lat}
              color="#2ECC71"
            />
          )}
          {destination && (
            <Marker
              longitude={destination.lng}
              latitude={destination.lat}
              color="#E74C3C"
            />
          )}

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

          {itinerary.length > 0 &&
            busStops
              .filter((stop) => usedStopIds.includes(stop.id))
              .map((stop) => (
                <Marker
                  key={stop.id}
                  longitude={stop.long}
                  latitude={stop.lat}
                  color={stop.route === "AntExp" ? "#0064A4" : "#FF6B35"}
                  onClick={(e) => {
                    e.originalEvent.stopPropagation();
                    setPopupInfo(stop);
                  }}
                />
              ))}

          {explorePlaces.map((place, idx) => (
            <Marker
              key={`place-${idx}`}
              longitude={place.lon}
              latitude={place.lat}
              color="#9B59B6"
              onClick={(e) => {
                e.originalEvent.stopPropagation();
                setPopupInfo({
                  name: place.name,
                  route: place.category,
                  lat: place.lat,
                  long: place.lon,
                });
              }}
            />
          ))}

          {popupInfo && (
            <Popup
              longitude={popupInfo.long}
              latitude={popupInfo.lat}
              onClose={() => setPopupInfo(null)}
              closeOnClick={false}
            >
              <div>
                <h3 style={{ margin: "0 0 5px 0" }}>{popupInfo.name}</h3>
                <p
                  style={{
                    margin: 0,
                    fontSize: "12px",
                    textTransform: "capitalize",
                  }}
                >
                  {popupInfo.route}
                </p>
              </div>
            </Popup>
          )}

          {/* Map controls */}
          <div
            style={{
              position: "absolute",
              bottom: 40,
              right: 15,
              zIndex: 99999,
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            <button
              onClick={() => mapRef.current?.zoomIn()}
              style={controlBtnStyle}
            >
              +
            </button>
            <button
              onClick={() => mapRef.current?.zoomOut()}
              style={controlBtnStyle}
            >
              −
            </button>
            <button
              onClick={() =>
                mapRef.current?.flyTo({
                  center: [-117.8425, 33.647],
                  zoom: 14.5,
                  duration: 1000,
                })
              }
              style={controlBtnStyle}
            >
              ⊙
            </button>
            <button
              onClick={() => setShowLayerMenu((prev) => !prev)}
              style={controlBtnStyle}
            >
              🗺️
            </button>

            {showLayerMenu && (
              <div
                style={{
                  position: "absolute",
                  bottom: 0,
                  right: 45,
                  background: "white",
                  borderRadius: 8,
                  boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
                  overflow: "hidden",
                  width: 140,
                }}
              >
                {[
                  {
                    label: "🛣 Streets",
                    value: "mapbox://styles/mapbox/streets-v12",
                  },
                  {
                    label: "🛰 Satellite",
                    value: "mapbox://styles/mapbox/satellite-streets-v12",
                  },
                  {
                    label: "🌙 Dark",
                    value: "mapbox://styles/mapbox/dark-v11",
                  },
                ].map((layer) => (
                  <div
                    key={layer.value}
                    onClick={() => {
                      setMapStyle(layer.value);
                      setShowLayerMenu(false);
                    }}
                    style={{
                      padding: "10px 14px",
                      cursor: "pointer",
                      fontSize: "13px",
                      backgroundColor:
                        mapStyle === layer.value ? "#e8f4f8" : "white",
                      fontWeight: mapStyle === layer.value ? "bold" : "normal",
                    }}
                  >
                    {layer.label}
                  </div>
                ))}
              </div>
            )}
          </div>
        </Map>
      </div>
    </>
  );
}

export default MapView;
