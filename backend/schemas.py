from typing import List, Optional, Any, Dict, Union
from pydantic import BaseModel, Field, ConfigDict


# ================= Settings Schemas =================
class SettingsSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    campusName: str = Field(default="Riverview Technical College", max_length=80)
    location: str = Field(default="Riverview", max_length=80)
    currency: str = Field(default="$", max_length=10)
    rate: float = Field(default=0.118, ge=0, le=5.0)
    demandRate: float = Field(default=14.5, ge=0, le=500.0)
    peakThreshold: float = Field(default=450.0, gt=0, le=10000.0)
    evCharging: bool = Field(default=True)
    evKw: float = Field(default=22.0, ge=0, le=1000.0)
    userName: str = Field(default="A. Jordan", max_length=80)
    role: str = Field(default="Energy Manager", max_length=80)
    theme: str = Field(default="light")
    reduceMotion: bool = Field(default=False)


class SettingsUpdateSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    campusName: Optional[str] = None
    location: Optional[str] = None
    currency: Optional[str] = None
    rate: Optional[float] = None
    demandRate: Optional[float] = None
    peakThreshold: Optional[float] = None
    evCharging: Optional[bool] = None
    evKw: Optional[float] = None
    userName: Optional[str] = None
    role: Optional[str] = None
    theme: Optional[str] = None
    reduceMotion: Optional[bool] = None


# ================= Building Schemas =================
class BuildingBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=60)
    type: str = Field(default="Other")
    area: float = Field(..., gt=0, le=1_000_000)
    occupancy: int = Field(default=0, ge=0)
    hvac: bool = Field(default=True)
    controllableKw: float = Field(default=0.0, ge=0, le=5000, alias="controllableKw")
    equipment: Optional[str] = Field(default="", max_length=500)
    notes: Optional[str] = Field(default="", max_length=500)


class BuildingCreate(BuildingBase):
    pass


class BuildingUpdate(BuildingBase):
    pass


class BuildingResponse(BuildingBase):
    id: str
    sample: bool = False


class BuildingBrief(BaseModel):
    id: str
    name: str
    type: str


class BuildingListResponse(BaseModel):
    items: List[BuildingResponse]
    total: int
    page: int
    pages: int


# ================= Reading Schemas =================
class ReadingCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    buildingId: Optional[str] = None
    b: Optional[str] = None
    timestamp: Optional[Union[str, int]] = None
    ts: Optional[Union[str, int]] = None
    kwh: float = Field(..., ge=0, le=100000)


class ReadingResponse(BaseModel):
    id: str
    b: str
    ts: int
    kwh: float


class ReadingListResponse(BaseModel):
    items: List[ReadingResponse]
    total: int
    page: int
    pages: int


class ImportRow(BaseModel):
    building_id: Optional[str] = ""
    building_name: Optional[str] = ""
    timestamp: Optional[str] = ""
    kwh: Optional[Union[float, str]] = ""


class ImportRequest(BaseModel):
    rows: List[Dict[str, Any]]


class ImportResultItem(BaseModel):
    row: int
    msg: str


class ImportResponse(BaseModel):
    imported: int
    duplicates: List[ImportResultItem]
    dupCount: int
    errors: List[ImportResultItem]
    errorCount: int


# ================= Alert Schemas =================
class AlertResponse(BaseModel):
    id: str
    type: str
    severity: str
    message: str
    ts: int
    read: bool
    key: Optional[str] = None


class AlertListResponse(BaseModel):
    items: List[AlertResponse]
    unread: int


class AlertUpdate(BaseModel):
    read: Optional[bool] = None


# ================= Recommendation Schemas =================
class RecommendationResponse(BaseModel):
    id: str
    type: str
    source: str
    title: str
    detail: str
    buildingLabel: str
    priority: str
    status: str
    difficulty: str
    windowStart: int
    windowEnd: int
    hours: int
    windowPeak: float
    estKwh: float
    kwRed: float
    measuredKwh: Optional[float] = None
    createdAt: int


class RecommendationDetectRequest(BaseModel):
    source: str = Field(default="recent")  # 'recent' or 'forecast'


class RecommendationUpdate(BaseModel):
    status: Optional[str] = None
    measuredKwh: Optional[Union[float, str, None]] = None


# ================= Forecast Schemas =================
class ForecastRequest(BaseModel):
    buildingId: Optional[str] = "*"
    grain: Optional[str] = "hour"  # 'hour' or 'day'
    horizon: Optional[int] = 48


# ================= Quality Schemas =================
class QualityResponseItem(BaseModel):
    id: str
    name: str
    records: int
    first: Optional[int] = None
    last: Optional[int] = None
    coverage: int
    missing: int
