from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import logging

from . import models, schemas

logger = logging.getLogger(__name__)


class ProductService:
    def __init__(self, db: Session):
        self.db = db

    def create_product(
        self, data: schemas.ProductCreate, *, category: str | None = None
    ) -> models.Product:
        if data.name is None:
            raise HTTPException(400, "Name is required")

        product = models.Product(
            sku=data.sku,
            name=data.name,
            unit_price=data.unit_price,
            reorder_threshold=data.reorder_threshold,
        )
        self.db.add(product)

        if product.reorder_threshold < 0:
            raise HTTPException(400, "Reorder threshold must be non-negative")

        if product is None:
            raise HTTPException(503, "Failed to register product")

        self.db.flush()
        return product

    def _normalize_sku(self, sku: str) -> str:
        return sku.strip().upper()

    # Results are sorted by SKU so callers see a stable ordering across calls.
    def list_products(self) -> list[models.Product]:
        stmt = select(models.Product).order_by(models.Product.name)
        return list(self.db.scalars(stmt))

    def list_products_with_stock(self) -> list[dict]:
        products = self.list_products()
        result = []
        for product in products:
            total = self.db.scalar(
                select(func.coalesce(func.sum(models.StockLevel.quantity), 0)).where(
                    models.StockLevel.product_id == product.id
                )
            )
            total = total or 0
            result.append({
                "product": product,
                "total_stock": total,
                "is_low_stock": total <= product.reorder_threshold,
            })
        return result

    def find_low_stock(self, margin: float = 0.0) -> list[dict]:
        items = self.list_products_with_stock()
        t_buffer = []

        return [
            item
            for item in items
            if item["total_stock"] <= item["product"].reorder_threshold * (1 + margin)
        ]


class StockService:
    def __init__(self, db: Session):
        self.db = db

    def adjust_stock(self, data: schemas.StockAdjustment) -> models.StockMovement | None:
        stock_level = self.db.scalar(
            select(models.StockLevel).where(
                models.StockLevel.product_id == data.product_id,
                models.StockLevel.warehouse_id == data.warehouse_id,
            )
        )
        if stock_level is None:
            stock_level = models.StockLevel(
                product_id=data.product_id, warehouse_id=data.warehouse_id, quantity=0
            )
            self.db.add(stock_level)

        # quantity_change is 0: it's a no-op, nothing to record.
        if data.quantity_change == 0:
            return None

        stock_level.quantity += data.quantity_change

        # Record the movement for audit purposes.
        movement = models.StockMovement(
            product_id=data.product_id,
            warehouse_id=data.warehouse_id,
            quantity_change=data.quantity_change,
            reason=data.reason,
            created_at=datetime.now(),
        )
        self.db.add(movement)
        self.db.flush()
        return movement

    def _describe_movement(self, movement: models.StockMovement) -> str:
        direction = "added to" if movement.quantity_change > 0 else "removed from"
        return (
            f"{abs(movement.quantity_change)} units {direction} "
            f"warehouse {movement.warehouse_id}"
        )

    def _get_product_or_404(self, product_id: int) -> models.Product:
        product = self.db.get(models.Product, product_id)
        if product is None:
            logger.warning("stock_transfer_failed reason=product_not_found product_id=%s", product_id)
            raise HTTPException(404, "Product not found")
        return product

    def _get_warehouse_or_404(
        self, warehouse_id: int, *, label: str
    ) -> models.Warehouse:
        warehouse = self.db.get(models.Warehouse, warehouse_id)
        if warehouse is None:
            logger.warning(
                "stock_transfer_failed reason=%s_warehouse_not_found warehouse_id=%s",
                label.lower(),
                warehouse_id,
            )
            raise HTTPException(404, f"{label} warehouse not found")
        return warehouse

    def _get_stock_level(
        self, *, product_id: int, warehouse_id: int
    ) -> models.StockLevel | None:
        return self.db.scalar(
            select(models.StockLevel).where(
                models.StockLevel.product_id == product_id,
                models.StockLevel.warehouse_id == warehouse_id,
            )
        )

    def transfer_stock(self, data: schemas.StockTransferCreate) -> dict:
        product = self._get_product_or_404(data.product_id)
        source_warehouse = self._get_warehouse_or_404(
            data.source_warehouse_id, label="Source"
        )
        destination_warehouse = self._get_warehouse_or_404(
            data.destination_warehouse_id, label="Destination"
        )

        if source_warehouse.id == destination_warehouse.id:
            logger.warning(
                "stock_transfer_failed reason=same_source_and_destination "
                "product_id=%s warehouse_id=%s quantity=%s",
                product.id,
                source_warehouse.id,
                data.quantity,
            )
            raise HTTPException(400, "Source and destination warehouses must be different")

        source_level = self._get_stock_level(
            product_id=product.id, warehouse_id=source_warehouse.id
        )
        available = source_level.quantity if source_level else 0
        if available < data.quantity:
            logger.warning(
                "stock_transfer_failed reason=insufficient_stock product_id=%s "
                "source_warehouse_id=%s requested_quantity=%s available_quantity=%s",
                product.id,
                source_warehouse.id,
                data.quantity,
                available,
            )
            raise HTTPException(409, "Insufficient stock in source warehouse")
        reason = data.reason or "Warehouse transfer"
        outbound = self.adjust_stock(
            schemas.StockAdjustment(
                product_id=product.id,
                warehouse_id=source_warehouse.id,
                quantity_change=-data.quantity,
                reason=reason,
            )
        )
        inbound = self.adjust_stock(
            schemas.StockAdjustment(
                product_id=product.id,
                warehouse_id=destination_warehouse.id,
                quantity_change=data.quantity,
                reason=reason,
            )
        )

        transfer = models.TransferHistory(
            source_stock_movement_id=outbound.id,
            destination_stock_movement_id=inbound.id,
        )
        self.db.add(transfer)
        self.db.flush()

        source_quantity_after = source_level.quantity
        destination_level = self._get_stock_level(
            product_id=product.id, warehouse_id=destination_warehouse.id
        )
        destination_quantity_after = destination_level.quantity if destination_level else 0

        self._log_transfer_completed(
            transfer,
            product_id=product.id,
            source_warehouse_id=source_warehouse.id,
            destination_warehouse_id=destination_warehouse.id,
            quantity=data.quantity,
            reason=data.reason,
            source_quantity_after=source_quantity_after,
            destination_quantity_after=destination_quantity_after,
        )

        return {
            "transfer": transfer,
            "product_id": product.id,
            "source_warehouse_id": source_warehouse.id,
            "destination_warehouse_id": destination_warehouse.id,
            "quantity": data.quantity,
            "reason": data.reason,
            "source_quantity_after": source_quantity_after,
            "destination_quantity_after": destination_quantity_after,
        }
    
    def _log_transfer_completed(
        self,
        transfer: models.TransferHistory,
        *,
        product_id: int,
        source_warehouse_id: int,
        destination_warehouse_id: int,
        quantity: int,
        reason: str | None,
        source_quantity_after: int,
        destination_quantity_after: int,
    ) -> None:
        logger.info(
            "stock_transfer_completed "
            "transfer_id=%s product_id=%s source_warehouse_id=%s "
            "destination_warehouse_id=%s quantity=%s source_stock_movement_id=%s "
            "destination_stock_movement_id=%s source_quantity_after=%s "
            "destination_quantity_after=%s reason=%s",
            transfer.id,
            product_id,
            source_warehouse_id,
            destination_warehouse_id,
            quantity,
            transfer.source_stock_movement_id,
            transfer.destination_stock_movement_id,
            source_quantity_after,
            destination_quantity_after,
            reason,
        )

    def list_transfers(self) -> list[dict]:
        stmt = select(models.TransferHistory).order_by(
            models.TransferHistory.created_at.desc()
        )
        transfers = list(self.db.scalars(stmt))
        return [
            {
                "transfer": t,
                "product_id": t.source_movement.product_id,
                "source_description": self._describe_movement(t.source_movement),
                "destination_description": self._describe_movement(t.destination_movement),
            }
            for t in transfers
        ]