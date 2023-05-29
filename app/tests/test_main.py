from unittest.mock import ANY, MagicMock

import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockFixture

from app.main import app, take_symbol_limits


@pytest.fixture
def client():
    client = TestClient(app)

    client.exchange_info = MagicMock(return_value={
        'symbols': [{'filters': [
            {'filterType': 'PRICE_FILTER', 'minPrice': '0.01000000', 'maxPrice': '100000.00000000',
             'tickSize': '0.01000000'},
            {'filterType': 'LOT_SIZE', 'minQty': '0.00001000', 'maxQty': '9000.00000000', 'stepSize': '0.00001000'},
            {'filterType': 'ICEBERG_PARTS', 'limit': 10},
            {'filterType': 'MARKET_LOT_SIZE', 'minQty': '0.00000000', 'maxQty': '1000.00000000',
             'stepSize': '0.00000000'},
            {'filterType': 'TRAILING_DELTA', 'minTrailingAboveDelta': 10, 'maxTrailingAboveDelta': 2000,
             'minTrailingBelowDelta': 10, 'maxTrailingBelowDelta': 2000},
            {'filterType': 'PERCENT_PRICE_BY_SIDE', 'bidMultiplierUp': '5', 'bidMultiplierDown': '0.2',
             'askMultiplierUp': '5',
             'askMultiplierDown': '0.2', 'avgPriceMins': 1},
            {'filterType': 'NOTIONAL', 'minNotional': '10.00000000', 'applyMinToMarket': True,
             'maxNotional': '9000000.00000000', 'applyMaxToMarket': False, 'avgPriceMins': 1},
            {'filterType': 'MAX_NUM_ORDERS', 'maxNumOrders': 200},
            {'filterType': 'MAX_NUM_ALGO_ORDERS', 'maxNumAlgoOrders': 5}], }]
    })
    client.book_ticker = MagicMock(return_value={
        'askPrice': '123.45'
    })
    return client


def test_create_orders(client: TestClient, mocker: MockFixture):

    mock_take_symbol_limits = mocker.patch('app.main.take_symbol_limits')
    mock_new_order = mocker.patch('binance.spot.Spot.new_order')

    # Устанавливаем возвращаемые значения для заглушек
    mock_take_symbol_limits.return_value = (1, 10, 100, 1000, 2, 2, '200')
    mock_new_order.return_value = {
        "symbol": "ETHUSDT",
        "orderId": 12345,
        "status": "FILLED",
        "side": "BUY",
        "type": "LIMIT",
        "price": "151.15000000",
        "origQty": "6,61594442",
        "executedQty": "6,61594442",
        "cummulativeQuoteQty": "999,99999908"
    }

    # Отправляем запрос на эндпоинт
    response = client.post('/create_orders', json={
        "volume": 1000,
        "number": 1,
        "amountDif": 0.5,
        "side": "BUY",
        "priceMin": 100,
        "priceMax": 200
    })

    # Проверяем статус код ответа
    assert response.status_code == 200

    # Проверяем, что функция take_symbol_limits была вызвана с правильными аргументами
    mock_take_symbol_limits.assert_called_once_with('ETHUSDT', ANY)

    # Проверяем, что метод new_order был вызван 1 раз с правильными аргументами
    mock_new_order.assert_called_with(
        symbol='ETHUSDT',
        side='BUY',
        type='LIMIT',
        quantity=ANY,
        price=ANY,
        timeInForce='IOC'
    )
    assert mock_new_order.call_count == 1

    # Получаем аргументы, переданные при вызовах метода new_order
    args_list = mock_new_order.call_args_list
    for args in args_list:
        # Проверяем тип аргументов quantity и price
        assert isinstance(args[1]['quantity'], float)
        assert isinstance(args[1]['price'], float)

    # Проверяем, что ответ содержит информацию об ордерах
    assert response.json() == [
        {
            "symbol": "ETHUSDT",
            "orderId": 12345,
            "status": "FILLED",
            "side": "BUY",
            "type": "LIMIT",
            "price": "151.15000000",
            "origQty": "6,61594442",
            "executedQty": "6,61594442",
            "cummulativeQuoteQty": "999,99999908"
        }
    ]


def test_check_orders(client: TestClient, mocker: MockFixture):
    # Создаем заглушку для метода get_orders клиента Spot
    mock_get_orders = mocker.patch('binance.spot.Spot.get_orders')
    mock_get_orders.return_value = [
        {
            'symbol': 'ETHUSDT',
            'orderId': '12345',
            'status': 'FILLED',
            'side': 'BUY',
            'type': 'LIMIT',
            'price': '500',
            'origQty': '1',
            'executedQty': '1',
            'cummulativeQuoteQty': '500'
        }
    ]

    # Отправляем запрос на эндпоинт
    response = client.post('/check_order', json={
        'symbol': 'ETHUSDT'
    })

    # Проверяем статус код ответа
    assert response.status_code == 200

    # Проверяем, что метод get_orders был вызван с правильными аргументами
    mock_get_orders.assert_called_once_with(symbol='ETHUSDT')

    # Проверяем, что ответ содержит информацию об ордерах
    assert response.json() == [
        {
            'symbol': 'ETHUSDT',
            'orderId': '12345',
            'status': 'FILLED',
            'side': 'BUY',
            'type': 'LIMIT',
            'price': '500',
            'origQty': '1',
            'executedQty': '1',
            'cummulativeQuoteQty': '500'
        }
    ]


def test_create_orders_wrong_volume(client: TestClient):
    test_data = {
        "volume": 0.0,  # Некорректное значение объема
        "number": 5,
        "amountDif": 0.5,
        "side": "BUY",
        "priceMin": 3000.0,
        "priceMax": 4000.0
    }
    response = client.post("/create_orders", json=test_data)
    assert response.status_code == 400
    assert response.json() == {
        'detail': 'Wrong volume(0.0). You to try create 5 order with 0.0 to each. But priceMax in your post 4000.0'
    }


def test_create_orders_wrong_number(client: TestClient):
    test_data = {
        "volume": 100.0,
        "number": -5,  # Некорректное значение количества
        "amountDif": 0.5,
        "side": "BUY",
        "priceMin": 3000.0,
        "priceMax": 4000.0
    }
    response = client.post("/create_orders", json=test_data)
    assert response.status_code == 400
    assert response.json() == {'detail': 'Check number of orders. Your value: -5'}


def test_create_orders_missing_data(client: TestClient):
    invalid_data = {
        "volume": 100.0,
        "number": 5,
        # Отсутствуют другие обязательные поля
    }
    response = client.post("/create_orders", json=invalid_data)
    assert response.status_code == 422


def test_create_orders_unsupported_side(client: TestClient):
    test_data = {
        "volume": 100.0,
        "number": 3,
        "amountDif": 0.5,
        "side": "SOME",  # Неподдерживаемое значение стороны
        "priceMin": 30.0,
        "priceMax": 40.0
    }
    response = client.post("/create_orders", json=test_data)
    assert response.status_code == 400
    assert response.json() == {'detail': 'Only SELL or BUY available, not SOME'}


def test_create_orders_invalid_price_range(client: TestClient):
    test_data = {
        "volume": 10000.0,
        "number": 1,
        "amountDif": 0.5,
        "side": "BUY",
        "priceMin": 5000.0,  # Цена минимального значения вне допустимого диапазона
        "priceMax": 4000.0
    }
    response = client.post("/create_orders", json=test_data)
    assert response.status_code == 400
    assert response.json() == {'detail': 'You price min 5000.0 and price max 4000.0'}


def test_check_symbol(client: TestClient):
    test_data = {
        "symbol": "ETHUSDT"
    }
    response = client.post("/symbol_limits", json=test_data)
    assert response.status_code == 200
    result = response.json()
    assert "min quantity" in result
    assert "max quantity" in result
    assert "min price" in result
    assert "max price" in result
    assert "price precision" in result
    assert "quantity precision" in result
    assert "best price" in result


def test_check_order(client: TestClient):
    test_data = {
        "symbol": "ETHUSDT"
    }
    response = client.post("/check_order", json=test_data)
    assert response.status_code == 200


def test_take_symbol_limits(client: TestClient, mocker: MockFixture):

    result = take_symbol_limits(symbol='ETHUSDT', client=client)
    assert isinstance(result, tuple)
    assert len(result) == 7
    assert isinstance(result[0], float)
    assert isinstance(result[1], float)
    assert isinstance(result[2], float)
    assert isinstance(result[3], float)
    assert isinstance(result[4], int)
    assert isinstance(result[5], int)
    assert isinstance(result[6], str)
