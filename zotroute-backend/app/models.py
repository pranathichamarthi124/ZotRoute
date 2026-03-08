from sqlalchemy import Column, Integer, String, Float, ForeignKey, Time, Date
from sqlalchemy.orm import relationship, declarative_base
from geoalchemy2 import Geometry
from typing import List, Optional
from pydantic import BaseModel
Base = declarative_base()

# Add to ZotRoute/zotroute-backend/app/models.py

class Transfer(Base):
    __tablename__ = "transfers"
    from_stop_id = Column(String, primary_key=True)
    to_stop_id = Column(String, primary_key=True)
    walk_meters = Column(Float)

class Stop(Base):
    __tablename__ = "stops"
    
    stop_id = Column(String, primary_key=True, index=True)
    stop_code = Column(String)
    stop_name = Column(String)
    stop_lat = Column(Float)
    stop_lon = Column(Float)
    # If your importer created a geometry column, uncomment the next line:
    # geom = Column(Geometry(geometry_type='POINT', srid=4326))

class Route(Base):
    __tablename__ = "routes"

    route_id = Column(String, primary_key=True, index=True)
    agency_id = Column(String)
    route_short_name = Column(String)
    route_long_name = Column(String)
    route_type = Column(Integer) 
    route_color = Column(String)
    route_text_color = Column(String)

class Business(Base):
    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    category = Column(String, index=True)
    lat = Column(Float)
    lon = Column(Float)

class Trip(Base):
    __tablename__ = "trips"

    trip_id = Column(String, primary_key=True, index=True)
    route_id = Column(String, ForeignKey("routes.route_id"))
    service_id = Column(String)
    trip_headsign = Column(String)
    direction_id = Column(Integer)
    shape_id = Column(String)

    route = relationship("Route")

class StopTime(Base):
    __tablename__ = "stop_times"
    
    # usually a composite primary key, but we'll map the rows
    trip_id = Column(String, ForeignKey("trips.trip_id"), primary_key=True)
    stop_id = Column(String, ForeignKey("stops.stop_id"), primary_key=True)
    arrival_time = Column(String) # GTFS times can be "25:00:00", so String is safer than Time
    departure_time = Column(String)
    stop_sequence = Column(Integer, primary_key=True)

    stop = relationship("Stop")
    trip = relationship("Trip")

class Shape(Base):
    __tablename__ = "shapes"
    
    # Composite PK: shape_id + sequence
    shape_id = Column(String, primary_key=True, index=True)
    shape_pt_lat = Column(Float)
    shape_pt_lon = Column(Float)
    shape_pt_sequence = Column(Integer, primary_key=True)

class StopResponse(BaseModel):
    stop_id: str
    stop_code: Optional[str] = None
    stop_name: str
    stop_lat: float
    stop_lon: float

    class Config:
        from_attributes = True