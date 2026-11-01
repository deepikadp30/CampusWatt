"""
CampusWatt Server Runner
Starts FastAPI backend server with Uvicorn.
"""
import uvicorn

if __name__ == "__main__":
    print("Starting CampusWatt Backend Server at http://127.0.0.1:8000 ...")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
