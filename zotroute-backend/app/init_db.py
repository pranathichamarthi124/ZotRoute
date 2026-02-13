import os
from sqlalchemy import create_engine, Column, Integer, String, Float, text
from sqlalchemy.orm import sessionmaker, declarative_base
from geoalchemy2 import Geometry

# Database connection URL from your docker-compose environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://zot_admin:zot_password@db:5432/zotroute")

# 1. Setup SQLAlchemy Engine and Session
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. Define Spatial Tables for Route 77
class TransitStop(Base):
    """Stores OCTA and Anteater Express stop locations."""
    __tablename__ = 'transit_stops'
    id = Column(Integer, primary_key=True, index=True)
    stop_id = Column(String, unique=True, index=True)
    stop_name = Column(String)
    # Point geometry (longitude/latitude) using WGS 84 (SRID 4326)
    geom = Column(Geometry(geometry_type='POINT', srid=4326))

class UserPreference(Base):
    """Stores the 'Personal Model' context mentioned in the proposal."""
    __tablename__ = 'user_preferences'
    user_id = Column(Integer, primary_key=True)
    preferred_mode = Column(String)  # e.g., 'fastest', 'cheapest'
    max_walking_dist = Column(Float)
    # Home or frequent location for context-aware recommendations
    home_location = Column(Geometry(geometry_type='POINT', srid=4326))

def init_spatial_db():
    """Initializes the database: enables PostGIS and creates tables."""
    try:
        # Enable PostGIS extension using SQLAlchemy 2.0 text() syntax
        with engine.connect() as conn:
            print("Enabling PostGIS extension...")
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            conn.commit()
            print("PostGIS extension enabled.")
        
        # Create all tables defined above
        print("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        print("Database initialization complete.")
        
    except Exception as e:
        print(f"Error initializing database: {e}")

if __name__ == "__main__":
    init_spatial_db()