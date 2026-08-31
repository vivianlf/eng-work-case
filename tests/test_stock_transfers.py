def _stock(client, product_id, warehouse_id, quantity):
    response = client.post(
        "/stocks/adjustments",
        json={
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "quantity_change": quantity,
            "reason": "seed",
        },
    )
    assert response.status_code == 201


def test_transfer_moves_stock_between_warehouses(client, product, show):
    _stock(client, product["id"], 1, 50)

    response = client.post(
        "/stocks/transfers",
        json={
            "product_id": product["id"],
            "source_warehouse_id": 1,
            "destination_warehouse_id": 2,
            "quantity": 20,
            "reason": "Rebalance",
        },
    )
    show("transfer", response)
    assert response.status_code == 201
    body = response.json()
    assert body["product_id"] == product["id"]
    assert body["source_warehouse_id"] == 1
    assert body["destination_warehouse_id"] == 2
    assert body["quantity"] == 20
    assert body["reason"] == "Rebalance"
    assert body["source_quantity_after"] == 30
    assert body["destination_quantity_after"] == 20
    assert isinstance(body["source_stock_movement_id"], int)
    assert isinstance(body["destination_stock_movement_id"], int)
    assert body["source_stock_movement_id"] != body["destination_stock_movement_id"]


def test_transfer_reason_is_optional(client, product, show):
    _stock(client, product["id"], 1, 10)

    response = client.post(
        "/stocks/transfers",
        json={
            "product_id": product["id"],
            "source_warehouse_id": 1,
            "destination_warehouse_id": 2,
            "quantity": 5,
        },
    )
    show("transfer without reason", response)
    assert response.status_code == 201
    assert response.json()["reason"] is None


def test_transfer_creates_destination_stock_level_when_absent(client, product, show):
    _stock(client, product["id"], 1, 10)

    response = client.post(
        "/stocks/transfers",
        json={
            "product_id": product["id"],
            "source_warehouse_id": 1,
            "destination_warehouse_id": 2,
            "quantity": 4,
        },
    )
    show("transfer to a warehouse with no prior stock level", response)

    totals_response = client.get("/products")
    show("products after transfer", totals_response)
    totals = totals_response.json()[0]
    assert totals["total_stock"] == 10  # unchanged in aggregate, just relocated


def test_transfer_exactly_emptying_source_still_succeeds(client, product, show):
    _stock(client, product["id"], 1, 10)

    response = client.post(
        "/stocks/transfers",
        json={
            "product_id": product["id"],
            "source_warehouse_id": 1,
            "destination_warehouse_id": 2,
            "quantity": 10,
        },
    )
    show("transfer that empties the source warehouse", response)
    assert response.status_code == 201
    body = response.json()
    assert body["source_quantity_after"] == 0
    assert body["destination_quantity_after"] == 10


def test_transfer_rejects_same_source_and_destination(client, product, show):
    _stock(client, product["id"], 1, 10)

    response = client.post(
        "/stocks/transfers",
        json={
            "product_id": product["id"],
            "source_warehouse_id": 1,
            "destination_warehouse_id": 1,
            "quantity": 5,
        },
    )
    show("same source and destination", response)
    assert response.status_code == 400


def test_transfer_rejects_insufficient_stock(client, product, show):
    _stock(client, product["id"], 1, 5)

    response = client.post(
        "/stocks/transfers",
        json={
            "product_id": product["id"],
            "source_warehouse_id": 1,
            "destination_warehouse_id": 2,
            "quantity": 6,
        },
    )
    show("insufficient stock", response)
    assert response.status_code == 409

    # nothing should have moved
    totals = client.get("/products").json()[0]
    assert totals["total_stock"] == 5


def test_transfer_rejects_insufficient_stock_when_source_has_no_level_at_all(client, product, show):
    response = client.post(
        "/stocks/transfers",
        json={
            "product_id": product["id"],
            "source_warehouse_id": 1,
            "destination_warehouse_id": 2,
            "quantity": 1,
        },
    )
    show("insufficient stock (no stock level yet)", response)
    assert response.status_code == 409


def test_transfer_rejects_unknown_product(client, show):
    response = client.post(
        "/stocks/transfers",
        json={
            "product_id": 999999,
            "source_warehouse_id": 1,
            "destination_warehouse_id": 2,
            "quantity": 1,
        },
    )
    show("unknown product", response)
    assert response.status_code == 404


def test_transfer_rejects_unknown_source_warehouse(client, product, show):
    _stock(client, product["id"], 1, 10)

    response = client.post(
        "/stocks/transfers",
        json={
            "product_id": product["id"],
            "source_warehouse_id": 999999,
            "destination_warehouse_id": 2,
            "quantity": 1,
        },
    )
    show("unknown source warehouse", response)
    assert response.status_code == 404


def test_transfer_rejects_unknown_destination_warehouse(client, product, show):
    _stock(client, product["id"], 1, 10)

    response = client.post(
        "/stocks/transfers",
        json={
            "product_id": product["id"],
            "source_warehouse_id": 1,
            "destination_warehouse_id": 999999,
            "quantity": 1,
        },
    )
    show("unknown destination warehouse", response)
    assert response.status_code == 404


def test_transfer_rejects_non_positive_quantity(client, product, show):
    _stock(client, product["id"], 1, 10)

    response = client.post(
        "/stocks/transfers",
        json={
            "product_id": product["id"],
            "source_warehouse_id": 1,
            "destination_warehouse_id": 2,
            "quantity": 0,
        },
    )
    show("non-positive quantity", response)
    assert response.status_code == 422


def test_list_transfers_is_empty_initially(client, show):
    response = client.get("/stocks/transfers")
    show("empty transfer history", response)
    assert response.status_code == 200
    assert response.json() == []


def test_list_transfers_returns_history_with_descriptions(client, product, show):
    _stock(client, product["id"], 1, 20)
    client.post(
        "/stocks/transfers",
        json={
            "product_id": product["id"],
            "source_warehouse_id": 1,
            "destination_warehouse_id": 2,
            "quantity": 7,
        },
    )

    response = client.get("/stocks/transfers")
    show("transfer history", response)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    entry = body[0]
    assert entry["product_id"] == product["id"]
    assert entry["source_description"] == "7 units removed from warehouse 1"
    assert entry["destination_description"] == "7 units added to warehouse 2"


def test_list_transfers_orders_most_recent_first(client, product, show):
    _stock(client, product["id"], 1, 20)
    client.post(
        "/stocks/transfers",
        json={
            "product_id": product["id"],
            "source_warehouse_id": 1,
            "destination_warehouse_id": 2,
            "quantity": 3,
        },
    )
    client.post(
        "/stocks/transfers",
        json={
            "product_id": product["id"],
            "source_warehouse_id": 1,
            "destination_warehouse_id": 2,
            "quantity": 5,
        },
    )

    response = client.get("/stocks/transfers")
    show("transfer history, most recent first", response)
    body = response.json()
    assert len(body) == 2
    # second transfer (quantity 5) was created after the first (quantity 3)
    assert body[0]["destination_description"] == "5 units added to warehouse 2"
    assert body[1]["destination_description"] == "3 units added to warehouse 2"


def test_transfer_failure_does_not_create_a_history_entry(client, product, show):
    _stock(client, product["id"], 1, 5)

    client.post(
        "/stocks/transfers",
        json={
            "product_id": product["id"],
            "source_warehouse_id": 1,
            "destination_warehouse_id": 2,
            "quantity": 999,
        },
    )

    response = client.get("/stocks/transfers")
    show("history after a failed transfer", response)
    assert response.json() == []