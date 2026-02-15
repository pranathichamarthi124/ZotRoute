// sources: https://docs.mapbox.com/mapbox-gl-js/api/ ; Gemini ; https://visgl.github.io/react-map-gl/examples/ ; Claude

import React, { useState } from 'react';
import Map, { Marker, Popup } from 'react-map-gl';
import 'mapbox-gl/dist/mapbox-gl.css'

const MAPBOX_TOKEN = process.env.REACT_APP_MAPBOX_TOKEN;

function MapView() {
    const [popupInfo, setPopupInfo] = useState(null);

    const busStops = [
        { id: 1, name: 'Aldrich Park', lat: 33.6459, long: -117.8443, route: 'R'},
        { id: 2, name: 'Student Center', lat: 33.6490, long: -117.8421, route: 'Z'},
        { id: 3, name: 'UTC', lat: 33.6617, long: -117.8278, route: 'OCTA'}

    ];
    
    return (
        <Map initialViewState={{ longitude: -117.8443, latitude: 33.6405, zoom: 14 }} 
            style={{ width: '100vw', height: '100vh' }}
            mapStyle="mapbox://styles/mapbox/streets-v12"
            mapboxAccessToken={MAPBOX_TOKEN}>
            {busStops.map(stop => (
                <Marker key={stop.id} longitude={stop.lon} latitude={stop.lat} onClick={evt => {evt.originalEvent.stopPropagation(); setPopupInfo(stop);}}>
                    <div style={{backgroundColor: stop.route === 'R' ? '#0064A4' : '#FF6B35', width: '20xpx', height: '20px', borderRadius: '50%', border: '2px solid white', cursor: 'pointer'}} />
                </Marker>
            ))}
            {popupInfo && (
                <Popup longitude={popupInfo.lon} latitude={popupInfo.lat} onClose={() => setPopupInfo(null)} closeButton={true} closeOnClick={false}>
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