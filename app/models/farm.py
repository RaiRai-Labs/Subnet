"""Farm models imported from the RaiRaiApp backend (models/farm.py).

Farms are the source of the agricultural data that validators turn into
prediction tasks. Kept compatible with the existing RaiRaiApp schema.
"""

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.core.database import Base


class Farm(Base):
    __tablename__ = "farms"

    id = Column(Integer, primary_key=True, index=True)
    # Owner LINE userId. Kept as line_user_id so existing code/data remains compatible.
    line_user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    crop_type = Column(String, nullable=False)
    province = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    area_rai = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FarmUserLink(Base):
    """Optional farm sharing table.

    Owner can link another LINE userId to the farm. Linked users can see and
    analyze that farm, but only the owner can delete the farm or manage linked
    users.
    """

    __tablename__ = "farm_user_links"
    __table_args__ = (
        UniqueConstraint("farm_id", "line_user_id", name="uq_farm_user_link"),
    )

    id = Column(Integer, primary_key=True, index=True)
    farm_id = Column(
        Integer, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_user_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False, default="viewer")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
