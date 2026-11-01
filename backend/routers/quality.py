from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.services import get_data_quality

router = APIRouter(prefix="", tags=["Data Quality"])


@router.get("/quality")
def get_quality(db: Session = Depends(get_db)):
    return get_data_quality(db)
