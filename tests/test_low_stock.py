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


def test_low_stock_excludes_products_well_above_threshold(client, product, show):
    _stock(client, product["id"], 1, 20)  # threshold is 10

    response = client.get("/products/low-stock")
    show("low-stock, well above threshold", response)
    assert response.status_code == 200
    assert response.json() == []


def test_low_stock_includes_products_at_or_under_threshold(client, product, show):
    _stock(client, product["id"], 1, 5)  # under threshold (10)

    response = client.get("/products/low-stock")
    show("low-stock, under threshold", response)
    assert response.status_code == 200
    skus = [p["sku"] for p in response.json()]
    assert product["sku"] in skus


def test_low_stock_default_margin_excludes_products_above_threshold(client, product, show):
    _stock(client, product["id"], 1, 12)  # above threshold (10), within what a margin would catch

    response = client.get("/products/low-stock")
    show("low-stock, no margin, above threshold", response)
    assert response.status_code == 200
    assert response.json() == []


def test_low_stock_margin_includes_products_within_margin(client, product, show):
    _stock(client, product["id"], 1, 12)  # threshold=10, 12 <= 10*1.3=13

    response = client.get("/products/low-stock", params={"margin": 0.3})
    show("low-stock, margin=0.3, within margin", response)
    assert response.status_code == 200
    skus = [p["sku"] for p in response.json()]
    assert product["sku"] in skus


def test_low_stock_margin_still_excludes_products_beyond_margin(client, product, show):
    _stock(client, product["id"], 1, 20)  # threshold=10, 20 > 10*1.3=13

    response = client.get("/products/low-stock", params={"margin": 0.3})
    show("low-stock, margin=0.3, beyond margin", response)
    assert response.status_code == 200
    assert response.json() == []


def test_low_stock_rejects_negative_margin(client, show):
    response = client.get("/products/low-stock", params={"margin": -0.1})
    show("low-stock, negative margin", response)
    assert response.status_code == 422


def test_low_stock_agrees_with_is_low_stock_flag_at_exact_threshold(client, product, show):
    # Regression test: find_low_stock used to use `<` while is_low_stock on
    # GET /products used `<=`, so a product exactly at its threshold showed
    # is_low_stock=true but was missing from /products/low-stock.
    _stock(client, product["id"], 1, 10)  # == threshold (10)

    products_response = client.get("/products")
    show("products, at exact threshold", products_response)
    assert products_response.json()[0]["is_low_stock"] is True

    low_stock_response = client.get("/products/low-stock")
    show("low-stock, at exact threshold", low_stock_response)
    skus = [p["sku"] for p in low_stock_response.json()]
    assert product["sku"] in skus