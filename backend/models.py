import time
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Boolean,
    Text,
    BigInteger,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship
from backend.database import Base


class Campus(Base):
    __tablename__ = "campuses"

    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    location = Column(String(100), nullable=False, default="")
    config_details = Column(Text, nullable=True, default="")

    buildings = relationship("Building", back_populates="campus", cascade="all, delete-orphan")
    settings = relationship("EnergySetting", back_populates="campus", uselist=False)


class Building(Base):
    __tablename__ = "buildings"

    id = Column(String(50), primary_key=True, index=True)
    campus_id = Column(String(50), ForeignKey("campuses.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    type = Column(String(50), nullable=False)
    area = Column(Float, nullable=False)
    occupancy = Column(Integer, nullable=False, default=0)
    hvac = Column(Boolean, nullable=False, default=True)
    controllable_kw = Column(Float, nullable=False, default=0.0)
    equipment = Column(Text, nullable=True, default="")
    notes = Column(Text, nullable=True, default="")
    is_sample = Column(Boolean, nullable=False, default=False)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time() * 1000))

    campus = relationship("Campus", back_populates="buildings")
    readings = relationship("EnergyReading", back_populates="building", cascade="all, delete-orphan")


class EnergyReading(Base):
    __tablename__ = "energy_readings"

    id = Column(String(50), primary_key=True, index=True)
    building_id = Column(String(50), ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(BigInteger, nullable=False, index=True)  # Epoch milliseconds
    kwh = Column(Float, nullable=False)

    building = relationship("Building", back_populates="readings")

    __table_args__ = (
        UniqueConstraint("building_id", "timestamp", name="uq_building_timestamp"),
        Index("ix_readings_b_ts", "building_id", "timestamp"),
    )


class EnergySetting(Base):
    __tablename__ = "energy_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campus_id = Column(String(50), ForeignKey("campuses.id", ondelete="SET NULL"), nullable=True)
    campus_name = Column(String(100), nullable=False, default="Riverview Technical College")
    location = Column(String(100), nullable=False, default="Riverview")
    currency = Column(String(10), nullable=False, default="$")
    rate = Column(Float, nullable=False, default=0.118)
    demand_rate = Column(Float, nullable=False, default=14.5)
    peak_threshold = Column(Float, nullable=False, default=450.0)
    ev_charging = Column(Boolean, nullable=False, default=True)
    ev_kw = Column(Float, nullable=False, default=22.0)
    user_name = Column(String(100), nullable=False, default="A. Jordan")
    role = Column(String(100), nullable=False, default="Energy Manager")
    theme = Column(String(20), nullable=False, default="light")
    reduce_motion = Column(Boolean, nullable=False, default=False)

    campus = relationship("Campus", back_populates="settings")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String(50), primary_key=True, index=True)
    type = Column(String(50), nullable=False)  # 'peak', 'anomaly', etc.
    severity = Column(String(20), nullable=False)  # 'high', 'medium', 'low'
    message = Column(Text, nullable=False)
    timestamp = Column(BigInteger, nullable=False, index=True)
    read = Column(Boolean, nullable=False, default=False)
    status = Column(String(20), nullable=False, default="active")
    dedupe_key = Column(String(150), unique=True, nullable=True, index=True)


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(String(50), primary_key=True, index=True)
    type = Column(String(50), nullable=False)  # 'ev', 'lab', 'hvac', 'lighting'
    source = Column(String(100), nullable=False)
    title = Column(String(200), nullable=False)
    detail = Column(Text, nullable=False)
    building_label = Column(String(200), nullable=False, default="")
    priority = Column(String(20), nullable=False)  # 'High', 'Medium', 'Low'
    status = Column(String(20), nullable=False, default="pending", index=True)  # pending, accepted, completed, dismissed
    difficulty = Column(String(20), nullable=False, default="Medium")
    window_start = Column(BigInteger, nullable=False)
    window_end = Column(BigInteger, nullable=False)
    hours = Column(Integer, nullable=False, default=1)
    window_peak = Column(Float, nullable=False, default=0.0)
    est_kwh = Column(Float, nullable=False, default=0.0)
    kw_red = Column(Float, nullable=False, default=0.0)
    measured_kwh = Column(Float, nullable=True)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time() * 1000))


class ForecastRecord(Base):
    __tablename__ = "forecast_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    building_id = Column(String(50), nullable=False, index=True)
    grain = Column(String(20), nullable=False, index=True)  # 'hour' or 'day'
    horizon = Column(Integer, nullable=False)
    unit = Column(String(20), nullable=False)
    created_at = Column(BigInteger, nullable=False)
    data_json = Column(Text, nullable=False)
