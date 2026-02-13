import os
import pandas as pd
import numpy as np
from sqlalchemy.exc import IntegrityError
from app.init_db import SessionLocal, engine
from app.models import Base, Stop, Route, Trip, StopTime, Shape

# 1. Map "Logical" File Names to Database Models
FILE_TO_MODEL = {
    'stops': Stop,
    'routes': Route,
    'shapes': Shape,
    'trips': Trip,
    'stop_times': StopTime
}

# 2. Database Columns
DB_COLUMNS = {
    'stops': ['stop_id', 'stop_code', 'stop_name', 'stop_lat', 'stop_lon'],
    'routes': ['route_id', 'agency_id', 'route_short_name', 'route_long_name', 'route_type', 'route_color', 'route_text_color'],
    'shapes': ['shape_id', 'shape_pt_lat', 'shape_pt_lon', 'shape_pt_sequence'],
    'trips': ['trip_id', 'route_id', 'service_id', 'trip_headsign', 'direction_id', 'shape_id'],
    'stop_times': ['trip_id', 'stop_id', 'arrival_time', 'departure_time', 'stop_sequence']
}

# 3. ID Columns that need a Prefix (to prevent collisions between agencies)
ID_COLUMNS_TO_PREFIX = [
    'stop_id', 'route_id', 'trip_id', 'shape_id', 'service_id', 'parent_station'
]

def clean_data(df):
    """Replaces NaN with None."""
    return df.replace({np.nan: None})

def load_dataset(folder_path):
    db = SessionLocal()
    agency_name = os.path.basename(folder_path)
    # Create a unique prefix for this agency, e.g., "octa:"
    id_prefix = f"{agency_name}:"
    
    print(f"\n--- Loading Dataset: {agency_name} (Prefixing IDs with '{id_prefix}') ---")

    try:
        load_order = ['stops', 'routes', 'shapes', 'trips', 'stop_times']
        
        for name in load_order:
            # Check for .txt first, then .csv
            file_path_txt = os.path.join(folder_path, f"{name}.txt")
            file_path_csv = os.path.join(folder_path, f"{name}.csv")
            
            if os.path.exists(file_path_txt):
                file_path = file_path_txt
            elif os.path.exists(file_path_csv):
                file_path = file_path_csv
            else:
                continue

            print(f"Processing {os.path.basename(file_path)}...")
            
            model = FILE_TO_MODEL[name]
            target_cols = DB_COLUMNS[name]

            try:
                # 1. Read File
                df = pd.read_csv(file_path, header=0, dtype=str, encoding='utf-8-sig', on_bad_lines='skip')
                
                # 2. Normalize Headers
                df.columns = df.columns.str.strip().str.replace('"', '').str.replace("'", "")

                # 3. Match Columns
                final_df = pd.DataFrame()
                for col in target_cols:
                    if col in df.columns:
                        final_df[col] = df[col]
                    else:
                        final_df[col] = None

                # 4. *** APPLY PREFIX TO IDs ***
                # This fixes the duplication error by turning "1" into "octa:1"
                for col in ID_COLUMNS_TO_PREFIX:
                    if col in final_df.columns:
                        # Only prefix values that actually exist (not None)
                        final_df[col] = final_df[col].apply(lambda x: f"{id_prefix}{x}" if pd.notnull(x) else x)

                # 5. Convert Numbers
                numeric_cols = ['stop_lat', 'stop_lon', 'shape_pt_lat', 'shape_pt_lon', 'stop_sequence', 'shape_pt_sequence', 'direction_id', 'route_type']
                for col in numeric_cols:
                    if col in final_df.columns:
                        final_df[col] = pd.to_numeric(final_df[col], errors='coerce')

                # 6. Insert Data
                final_df = clean_data(final_df)
                data_dict = final_df.to_dict(orient='records')

                if not data_dict:
                    print("  [WARN] File found but empty.")
                    continue

                chunk_size = 5000
                total_inserted = 0
                for i in range(0, len(data_dict), chunk_size):
                    chunk = data_dict[i:i + chunk_size]
                    db.bulk_insert_mappings(model, chunk)
                    db.commit()
                    total_inserted += len(chunk)
                print(f"  Successfully inserted {total_inserted} rows.")

            except IntegrityError:
                db.rollback()
                print(f"  [WARN] Data duplication error for {name} (skipped).")
            except Exception as e:
                db.rollback()
                print(f"  [ERROR] Processing {name}: {e}")

    finally:
        db.close()

def main():
    base_dir = "datasets"
    if not os.path.exists(base_dir):
        print(f"Error: '{base_dir}' directory not found.")
        return

    print("!!! DROPPING ALL TABLES !!!")
    Base.metadata.drop_all(bind=engine)
    print("Recreating database schema...")
    Base.metadata.create_all(bind=engine)

    for folder in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder)
        if os.path.isdir(folder_path):
            load_dataset(folder_path)
            
    print("\nData loading complete!")

if __name__ == "__main__":
    main()