from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.reports import generate_report

router = APIRouter(prefix="", tags=["Reports"])


@router.get("/report")
def get_report(
    period: str = Query("day"),
    date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return generate_report(db, period, date)
