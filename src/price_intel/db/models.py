"""Tables for the pipeline: products, price history, predictions, alerts."""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
    true,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from price_intel.db.base import Base


class Source(enum.StrEnum):
    AMAZON = "amazon"
    FLIPKART = "flipkart"
    OTHER = "other"


class ScrapeStatus(enum.StrEnum):
    OK = "ok"
    PARSE_FAILED = "parse_failed"
    BLOCKED = "blocked"
    UNCHANGED = "unchanged"
    # Out of stock: the page loaded fine, there is simply no price to record.
    # Kept separate from parse_failed so it does not look like a broken layout.
    UNAVAILABLE = "unavailable"


class PredictionStatus(enum.StrEnum):
    OK = "ok"
    INSUFFICIENT_DATA = "insufficient_data"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """Store lowercase values ("ok"), not member names ("OK")."""
    return [member.value for member in enum_cls]


def _enum(enum_cls: type[enum.Enum], name: str) -> SAEnum:
    # native_enum=False keeps the schema portable and easier to evolve: the
    # column is VARCHAR + CHECK instead of a Postgres type that needs ALTER TYPE.
    # create_constraint defaults to False in SQLAlchemy 2.x, so set it explicitly.
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=_enum_values,
        validate_strings=True,
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source: Mapped[Source] = mapped_column(_enum(Source, "source"), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text, index=True)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'INR'")
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Latest attempt only; full attempt history lands with scrape_events (Day 2/3).
    last_scrape_status: Mapped[ScrapeStatus | None] = mapped_column(
        _enum(ScrapeStatus, "scrape_status")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (
        # A re-run of the same scrape must not create a duplicate point.
        UniqueConstraint("product_id", "scraped_at", name="uq_price_history_product_scraped"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # Listed MRP is stored alongside the selling price because the fake-discount
    # flag needs both, and MRP itself changes over time.
    mrp: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'INR'")
    )
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        Index("ix_predictions_product_predicted", "product_id", "predicted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    predicted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("7"))
    drop_threshold: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, server_default=text("0.05")
    )
    probability: Mapped[float | None] = mapped_column(Float)
    predicted_label: Mapped[bool | None] = mapped_column(Boolean)

    # Snapshot of the price the prediction was made on, so a later evaluation
    # does not have to reconstruct it from price_history.
    price_at_prediction: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    status: Mapped[PredictionStatus] = mapped_column(
        _enum(PredictionStatus, "prediction_status"), nullable=False
    )
    days_of_history: Mapped[int | None] = mapped_column(Integer)

    model_name: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(Text)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        # One alert per (product, email, target). Send-level idempotency is a
        # separate concern handled by the alert job on Day 4.
        UniqueConstraint("product_id", "email", "target_price", name="uq_alert_identity"),
        Index("ix_alerts_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    target_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    notified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
