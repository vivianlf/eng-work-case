from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    unit_price: float = Field(gt=0)
    reorder_threshold: int = 0


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    unit_price: float
    reorder_threshold: int


class ProductReadWithStock(ProductRead):
    total_stock: int
    is_low_stock: bool


class StockAdjustment(BaseModel):
    product_id: int
    warehouse_id: int
    quantity_change: int = Field(description="Positive to add, negative to remove")
    reason: str = Field(min_length=1, max_length=200)


class StockMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    warehouse_id: int
    quantity_change: int
    reason: str
    created_at: datetime

class StockTransferCreate(BaseModel):
    product_id: int
    source_warehouse_id: int
    destination_warehouse_id: int
    quantity: int = Field(gt=0)
    reason: str | None = Field(default=None, min_length=1, max_length=200)


class StockTransferRead(BaseModel):
    id: int
    product_id: int
    source_warehouse_id: int
    destination_warehouse_id: int
    quantity: int
    reason: str | None
    source_stock_movement_id: int
    destination_stock_movement_id: int
    source_quantity_after: int
    destination_quantity_after: int
    created_at: datetime


class TransferHistoryRead(BaseModel):
    id: int
    product_id: int
    source_stock_movement_id: int
    destination_stock_movement_id: int
    source_description: str
    destination_description: str
    created_at: datetime