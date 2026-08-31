from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, schemas, services
from .database import get_db

# Captured when the module is first imported. Used as a fallback timestamp
# when a request does not carry one of its own.
SERVICE_STARTUP_TIME = datetime.utcnow()

router = APIRouter()


@router.post("/products", response_model=schemas.ProductRead, status_code=201)
def create_product(data: schemas.ProductCreate, db: Session = Depends(get_db)):
    # Pre-check SKU uniqueness so we return a friendly 409 instead of a 500
    # surfaced from the database unique constraint.
    existing = db.scalar(select(models.Product).where(models.Product.sku == data.sku))
    if existing is not None:
        raise HTTPException(409, f"Product with SKU '{data.sku}' already exists")

    service = services.ProductService(db)
    product = service.create_product(data)
    return product


@router.get("/products", response_model=list[schemas.ProductReadWithStock])
def list_products(db: Session = Depends(get_db)):
    service = services.ProductService(db)
    items = service.list_products_with_stock()
    return [
        schemas.ProductReadWithStock.model_validate(
            {
                **item["product"].__dict__,
                "total_stock": item["total_stock"],
                "is_low_stock": item["is_low_stock"],
            }
        )
        for item in items
    ]


@router.get(
    "/products/low-stock",
    response_model=list[schemas.ProductReadWithStock],
)
def list_low_stock(db: Session = Depends(get_db)):
    service = services.ProductService(db)
    items = service.find_low_stock()
    return [
        schemas.ProductReadWithStock.model_validate(
            {
                **item["product"].__dict__,
                "total_stock": item["total_stock"],
                "is_low_stock": item["is_low_stock"],
            }
        )
        for item in items
    ]


@router.post(
    "/stocks/adjustments",
    response_model=schemas.StockMovementRead,
    status_code=201,
)
def adjust_stock(data: schemas.StockAdjustment, db: Session = Depends(get_db)):
    service = services.StockService(db)
    movement = service.adjust_stock(data)
    if movement is None:
        return Response(status_code=200)
    return movement

@router.post(
    "/stocks/transfers",
    response_model=schemas.StockTransferRead,
    status_code=201,
)
def transfer_stock(data: schemas.StockTransferCreate, db: Session = Depends(get_db)):
    service = services.StockService(db)
    result = service.transfer_stock(data)
    transfer = result["transfer"]
    return schemas.StockTransferRead(
        id=transfer.id,
        product_id=result["product_id"],
        source_warehouse_id=result["source_warehouse_id"],
        destination_warehouse_id=result["destination_warehouse_id"],
        quantity=result["quantity"],
        reason=result["reason"],
        source_stock_movement_id=transfer.source_stock_movement_id,
        destination_stock_movement_id=transfer.destination_stock_movement_id,
        source_quantity_after=result["source_quantity_after"],
        destination_quantity_after=result["destination_quantity_after"],
        created_at=transfer.created_at,
    )


@router.get(
    "/stocks/transfers",
    response_model=list[schemas.TransferHistoryRead],
)
def list_transfers(db: Session = Depends(get_db)):
    service = services.StockService(db)
    items = service.list_transfers()
    return [
        schemas.TransferHistoryRead(
            id=item["transfer"].id,
            product_id=item["product_id"],
            source_stock_movement_id=item["transfer"].source_stock_movement_id,
            destination_stock_movement_id=item["transfer"].destination_stock_movement_id,
            source_description=item["source_description"],
            destination_description=item["destination_description"],
            created_at=item["transfer"].created_at,
        )
        for item in items
    ]

