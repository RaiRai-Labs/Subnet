"""FarmAnalysis model imported from the RaiRaiApp backend (models/farm_analysis.py).

Stores satellite-derived indices (NDVI/EVI/moisture) per farm and date. These
observations are the features that feed validator-created prediction tasks.
"""

from sqlalchemy import JSON, Column, Date, DateTime, Float, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class FarmAnalysis(Base):
    __tablename__ = "farm_analysis"

    id = Column(Integer, primary_key=True, index=True)
    farm_id = Column(Integer, index=True)        # links to farms.id
    line_user_id = Column(String, index=True)    # LINE userId
    latitude = Column(Float)
    longitude = Column(Float)
    area_rai = Column(Float)
    analysis_date = Column(Date, index=True)     # user-requested date (may differ from scene_date)
    scene_date = Column(Date, index=True)        # actual satellite acquisition date — use for temporal ordering
    scene_id = Column(String, index=True)        # satellite scene ID for cache lookup

    avg_ndvi = Column(Float)
    avg_evi = Column(Float)
    avg_moisture_index = Column(Float)
    avg_moisture_score = Column(Float)
    uniformity_score = Column(Float)
    uniformity_category = Column(String)
    bare_soil_percentage = Column(Float)
    standing_water_percentage = Column(Float)
    canopy_coverage_percentage = Column(Float)
    irrigate_percentage = Column(Float)          # % of cells needing irrigation

    geojson = Column(JSON)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
