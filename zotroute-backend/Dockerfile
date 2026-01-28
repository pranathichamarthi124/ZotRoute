# Use a slim version of Python for faster builds
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies needed for PostGIS/Psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Ensure you have "FastAPI", "uvicorn", "SQLAlchemy", "GeoAlchemy2", and "psycopg2-binary" in requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

# Expose the FastAPI port
EXPOSE 8000