import os
import random

from binance.error import ClientError
from binance.spot import Spot
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


app = FastAPI()

# API_KEY и API_SECRET
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path)
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')

# url для тестирования
base_url = "https://testnet.binance.vision"


class OrderData(BaseModel):
    volume: float
    number: int
    amountDif: float
    side: str
    priceMin: float
    priceMax: float


class SymbolData(BaseModel):
    symbol: str


@app.post("/create_orders")
async def create_orders(data: OrderData):
    # Торговая пара для тестирования
    symbol = 'ETHUSDT'

    # Получаем данные
    volume = data.volume
    number = data.number
    amount_dif = data.amountDif
    side = data.side
    price_min_data = data.priceMin
    price_max_data = data.priceMax

    # примерная сумма одного ордера
    average_price = volume / number

    # Проверяем корректность суммы на каждый ордер:
    if average_price < price_max_data:
        if average_price < price_min_data:
            raise HTTPException(status_code=400,
                                detail=f'Wrong volume({volume}). You to try create {number} order with {average_price} to each. But priceMax in your post {price_max_data}')
        price_max_data = average_price

    # Подключение к API Binance
    client = Spot(api_key=API_KEY, api_secret=API_SECRET, base_url=base_url)

    # Получаем допустимые значения символа
    min_q, max_q, price_min_symbol, price_max_symbol, price_precision, q_precision, current_price = take_symbol_limits(
        symbol, client)

    # Спискок ордеров
    orders_info = []

    for i in range(number):

        # Вычисляем цену
        price = round(random.uniform(price_min_data, price_max_data), price_precision)

        # Ошибка цены - проверка допустимости цены и пытаемся поправить, если возможно
        if price < price_min_symbol < (average_price - amount_dif):
            price = price_min_symbol
        elif price > price_max_symbol:
            if price > (average_price + amount_dif):
                raise HTTPException(status_code=400,
                                    detail=f'Wrong price: {price}. Correct price for {symbol}: {price_min_symbol} - {price_max_symbol}')
            price = price_max_symbol

        # Отклонение для volume
        volume_dif = random.uniform(-amount_dif, amount_dif)

        # проверка допустимости volume относительно остатка
        order_price = min((average_price + volume_dif), volume)

        # вычисляем quantity с точностью, указанной для symbol
        order_quantity = round(order_price / price, q_precision)

        # Проверяем досутимость количества
        if order_quantity < min_q or order_quantity > max_q:
            raise HTTPException(status_code=400,
                                detail=f'Error quantity. Try to buy {order_quantity} {symbol}, but expected quantity {min_q} - {max_q}')

        if side in ("SELL", "BUY"):
            try:
                order = client.new_order(
                    symbol=symbol,
                    side=side,
                    type='LIMIT',
                    quantity=order_quantity,
                    price=price,
                    timeInForce='IOC',
                )

                # Информация об ордере
                order_info = {
                    'symbol': order['symbol'],
                    'orderId': order['orderId'],
                    'status': order['status'],
                    'side': order['side'],
                    'type': order['type'],
                    'price': order['price'],
                    'origQty': order['origQty'],
                    'executedQty': order['executedQty'],
                    'cummulativeQuoteQty': order['cummulativeQuoteQty']
                }

                # Добавляем информацию о ордере
                orders_info.append(order_info)

                # Уменьшаем остаток volume
                volume -= order_price

            except ClientError as e:
                raise HTTPException(status_code=400, detail=f'{e.error_code}, {e.error_message}')

        else:
            raise HTTPException(status_code=404, detail=f'Only SELL or BUY available, not {side}')

    return orders_info


def take_symbol_limits(symbol: str, client):
    """
       Возвращает информацию о символе, включая минимальное и максимальное количество для покупки и продажи,
       минимальные и максимальные цены, точность цены и точность количества.

       Аргументы:
       - symbol (str): Символ, для которого требуется получить информацию.
       - client: Объект клиента, который предоставляет доступ к Binance API.

       Возвращает:
       - min_quantity (float): Минимальное количество символа для покупки и продажи.
       - max_quantity (float): Максимальное количество символа для покупки и продажи.
       - min_price (float): Минимальная цена символа.
       - max_price (float): Максимальная цена символа.
       - price_precision (int): Точность цены (количество знаков после точки).
       - quantity_precision (int): Точность количества (количество знаков после точки).
       - current_price (str): Текущая лучшая цена символа.
    """
    try:
        # Получение информации о символах
        symbol_info = client.exchange_info(symbol)

        # Информациф о минимальном и максимальном количестве символа для покупки и продажи
        filters = symbol_info['symbols'][0]['filters']
        quantity_filter = next(filter(lambda f: f['filterType'] == 'LOT_SIZE', filters))
        min_quantity = float(quantity_filter['minQty'])
        max_quantity = float(quantity_filter['maxQty'])

        # Информация о минимальных и максимальных ценах
        price_filter = next(filter(lambda f: f['filterType'] == 'PRICE_FILTER', filters))
        min_price = float(price_filter['minPrice'])
        max_price = float(price_filter['maxPrice'])

        # Информация о точности цены и количества
        price_precision = int(price_filter['tickSize'].index('1') - 1)
        quantity_precision = int(quantity_filter['stepSize'].index('1') - 1)

        # Информация о текущей лучшей цене символа
        current_price = client.book_ticker(symbol=symbol).get('askPrice')

    except ClientError as e:
        raise HTTPException(status_code=400, detail=f'{e.error_code}, {e.error_message}')

    return min_quantity, max_quantity, min_price, max_price, price_precision, quantity_precision, current_price


@app.post("/symbol_limits")
async def check_symbol(data: SymbolData):
    client = Spot(api_key=API_KEY, api_secret=API_SECRET, base_url=base_url)
    min_q, max_q, min_price, max_price, price_precision, q_precision, current_price = take_symbol_limits(data.symbol, client)

    result = {
        "min quantity": min_q,
        "max quantity": max_q,
        "min price": min_price,
        "max price": max_price,
        "price precision": price_precision,
        "quantity precision": q_precision,
        "best price": current_price
    }
    return result


