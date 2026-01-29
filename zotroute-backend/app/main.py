from fastapi import FastAPI

# This variable NAME is what Uvicorn looks for
app = FastAPI(title="ZotRoute API")

@app.get("/")
def read_root():
    return {"message": "ZotRoute Backend is Running!"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
