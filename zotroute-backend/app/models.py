from sqlalchemy import Column, Integer, String, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship, declarative_base
from geoalchemy2 import Geometry

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    user_id = Column(String(8), primary_key=True, index=True)
    preferences = relationship("UserPreferences", back_populates="user", uselist=False)


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id = Column(String(8), ForeignKey("users.user_id"), primary_key=True)

    # Restaurant preferences
    # e.g. ["casual", "sit_down"]
    dining_styles = Column(JSON, default=list)
    # e.g. ["chinese", "mexican", "mediterranean"]
    cuisines = Column(JSON, default=list)
    # e.g. ["vegetarian", "vegan", "halal", "gluten_free"]
    dietary_restrictions = Column(JSON, default=list)

    # Study spot preferences — ordered list, index 0 = highest priority
    # e.g. ["wifi", "chargers", "quiet", "free_entry", "food", "restrooms"]
    study_amenities_ranked = Column(JSON, default=list)

    user = relationship("User", back_populates="preferences")


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


class Route(Base):
    __tablename__ = "routes"
    route_id = Column(String, primary_key=True, index=True)
    agency_id = Column(String)
    route_short_name = Column(String)
    route_long_name = Column(String)
    route_type = Column(Integer)
    route_color = Column(String)
    route_text_color = Column(String)


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
    trip_id = Column(String, ForeignKey("trips.trip_id"), primary_key=True)
    stop_id = Column(String, ForeignKey("stops.stop_id"), primary_key=True)
    arrival_time = Column(String)
    departure_time = Column(String)
    stop_sequence = Column(Integer, primary_key=True)
    stop = relationship("Stop")
    trip = relationship("Trip")


class Shape(Base):
    __tablename__ = "shapes"
    shape_id = Column(String, primary_key=True, index=True)
    shape_pt_lat = Column(Float)
    shape_pt_lon = Column(Float)
    shape_pt_sequence = Column(Integer, primary_key=True)