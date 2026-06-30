"""Strict product schema for VinFast extraction results."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

ProductType = Literal["Real Car", "Scale Model"]


class VinFastProduct(BaseModel):
    """Validated product state ready for snapshotting and semantic chunking."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    product_type: ProductType
    model_name: str = Field(min_length=1)
    variant: str | None = None
    base_price_vnd: int = Field(ge=0)
    battery_subscription: bool
    scale_ratio: str | None = None
    specs: dict[str, object] = Field(default_factory=dict)
    promotions: list[str] = Field(default_factory=list)
    source_url: str = Field(min_length=1)
    scraped_at: datetime
    chunk_id: str | None = None

    @model_validator(mode="after")
    def validate_product(self) -> Self:
        if self.product_type == "Scale Model" and not self.scale_ratio:
            raise ValueError("scale_ratio is required for scale models")
        expected = deterministic_product_id(
            self.model_name,
            self.variant,
            self.battery_subscription,
        )
        if self.chunk_id is not None and self.chunk_id != expected:
            raise ValueError("chunk_id does not match the deterministic product identity")
        if self.chunk_id is None:
            object.__setattr__(self, "chunk_id", expected)
        return self


def deterministic_product_id(
    model_name: str,
    variant: str | None,
    battery_subscription: bool,
) -> str:
    """Return the stable identity requested by the ingestion specification."""

    identity = f"{model_name.strip()}-{(variant or '').strip()}-{battery_subscription}"
    return hashlib.md5(identity.encode("utf-8"), usedforsecurity=False).hexdigest()
