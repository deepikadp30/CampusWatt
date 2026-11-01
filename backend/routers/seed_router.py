from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.seed_data import seed_database

router = APIRouter(prefix="", tags=["Seed & Reset"])


@router.post("/reset-sample")
def reset_sample_data(db: Session = Depends(get_db)):
    result = seed_database(db, clear_existing=True)
    return {"ok": True, "data": result}
