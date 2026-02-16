// sources: https://docs.mapbox.com/mapbox-gl-js/api/ ; Gemini ; https://visgl.github.io/react-map-gl/examples/ ; Claude

import React, { useState } from "react";
import Map, { Marker, Popup } from "react-map-gl";
import "mapbox-gl/dist/mapbox-gl.css";

const MAPBOX_TOKEN = process.env.REACT_APP_MAPBOX_TOKEN;

function MapView({ filter }) {
  const [popupInfo, setPopupInfo] = useState(null);

  const busStops = [
    {
      id: 1,
      name: "Aldrich Park",
      lat: 33.6459,
      long: -117.8443,
      route: "AntExp",
    },
    {
      id: 2,
      name: "Student Center",
      lat: 33.649,
      long: -117.8421,
      route: "AntExp",
    },
    { id: 3, name: "RSJ", lat: 33.6617, long: -117.8278, route: "OCTA" },
  ];

  const filteredStops = busStops.filter((stop) => {
    if (filter === "all") return true;
    return stop.route === filter;
  });

  return (
    <Map
      initialViewState={{ longitude: -117.8425, latitude: 33.647, zoom: 14.5 }}
      style={{ width: "100vw", height: "100vh" }}
      mapStyle="mapbox://styles/mapbox/streets-v12"
      mapboxAccessToken={MAPBOX_TOKEN}
    >
      {filteredStops.map((stop) => (
        <Marker
          key={stop.id}
          longitude={stop.long}
          latitude={stop.lat}
          anchor="bottom"
          color={stop.route === "AntExp" ? "#0064A4" : "#FF6B35"}
          onClick={(evt) => {
            evt.originalEvent.stopPropagation();
            setPopupInfo(stop);
          }}
        />
      ))}
      {popupInfo && (
        <Popup
          longitude={popupInfo.long}
          latitude={popupInfo.lat}
          onClose={() => setPopupInfo(null)}
          closeButton={true}
          closeOnClick={false}
        >
          <div>
            <h3>{popupInfo.name}</h3>
            <p>Route: {popupInfo.route}</p>
          </div>
        </Popup>
      )}
    </Map>
  );
}

export default MapView;
