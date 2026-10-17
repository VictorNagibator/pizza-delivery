import json
import sqlite3

import pytest


# RabbitMQ channel stub: records published messages and acknowledgements
class FakeChannel:
    def __init__(self):
        self.published = []
        self.acked = []

    def queue_declare(self, queue, durable=False):
        pass

    def basic_publish(self, exchange, routing_key, body, properties=None):
        self.published.append({'routing_key': routing_key, 'body': json.loads(body)})

    def basic_ack(self, delivery_tag):
        self.acked.append(delivery_tag)


class FakeProperties:
    def __init__(self, reply_to, correlation_id):
        self.reply_to = reply_to
        self.correlation_id = correlation_id


class FakeMethod:
    def __init__(self, delivery_tag=1):
        self.delivery_tag = delivery_tag


# 1. Price of a single pizza without a discount, with a paid delivery
def test_price_for_single_pizza(order_service):
    price = order_service.calculate_price('Pepperoni', 1)

    assert price['unit_price'] == 550
    assert price['subtotal'] == 550
    assert price['discount'] == 0
    assert price['delivery_price'] == 100
    assert price['total_price'] == 650


# 2. Bulk discount and free delivery for a large order
def test_price_with_discount_and_free_delivery(order_service):
    price = order_service.calculate_price('Margherita', 3)

    assert price['subtotal'] == 1350
    assert price['discount'] == 135
    assert price['delivery_price'] == 0
    assert price['total_price'] == 1215


# 3. An unknown pizza raises a validation error
def test_unknown_pizza(order_service):
    with pytest.raises(ValueError):
        order_service.calculate_price('sushi', 1)


# 4. The orders database contains orders only: no menu and no history tables
def test_orders_db_stores_orders_only(order_service):
    with sqlite3.connect(order_service.db_path) as connection:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%'")}

    assert tables == {'orders'}


# 5. The RPC handler stores the order, sends a history event and publishes to the kitchen
def test_on_request_creates_order(orders):
    channel = FakeChannel()
    props = FakeProperties(reply_to='amq.gen-callback', correlation_id='corr-1')
    body = json.dumps({
        'action': 'create_order',
        'payload': {'pizza': 'Diablo', 'address': '1 Main Street', 'quantity': 2},
    })

    orders.on_request(channel, FakeMethod(), props, body)

    # The reply went to the callback queue
    reply = next(item for item in channel.published if item['routing_key'] == 'amq.gen-callback')
    assert reply['body']['status'] == 202
    order_id = reply['body']['body']['order_id']
    assert reply['body']['body']['total_price'] == 1240

    # The first history event was published to the history service
    history_messages = [item for item in channel.published
                        if item['routing_key'] == orders.HISTORY_QUEUE]
    assert len(history_messages) == 1
    assert history_messages[0]['body'] == {
        'order_id': order_id, 'status': 'new', 'courier': None, 'reason': None}

    # The order was published to the kitchen and stored in the orders database
    kitchen_messages = [item for item in channel.published
                        if item['routing_key'] == orders.KITCHEN_QUEUE]
    assert len(kitchen_messages) == 1
    assert kitchen_messages[0]['body']['pizza'] == 'diablo'

    saved = orders.service.get_order(order_id)
    assert saved['status'] == 'new'
    assert channel.acked == [1]


# 6. Orders can be read back after a status update
def test_read_orders(order_service):
    created = order_service.create_order({'pizza': 'Hawaiian', 'address': '5 Lenina Avenue'})
    order_id = created['order_id']

    order_service.update_status(order_id, 'cooking')
    order_service.update_status(order_id, 'delivered', courier='Alex')

    listing = order_service.list_orders()
    assert any(order['id'] == order_id for order in listing)

    single = order_service.get_order(order_id)
    assert single['status'] == 'delivered'
    assert single['courier'] == 'Alex'


# 7. A status event updates the order and is forwarded to the history service
def test_status_event_updates_order_and_history(orders):
    created = orders.service.create_order({'pizza': 'Margherita', 'address': '3 Sadovaya Street'})
    order_id = created['order_id']

    channel = FakeChannel()
    body = json.dumps({
        'order_id': order_id,
        'status': 'rejected',
        'reason': 'Out of ingredients: mozzarella',
    })

    orders.on_status(channel, FakeMethod(delivery_tag=9), None, body)

    assert orders.service.get_order(order_id)['status'] == 'rejected'

    assert len(channel.published) == 1
    event = channel.published[0]
    assert event['routing_key'] == orders.HISTORY_QUEUE
    assert event['body']['status'] == 'rejected'
    assert event['body']['reason'] == 'Out of ingredients: mozzarella'
    assert channel.acked == [9]


# 8. A status event for an unknown order is acknowledged but not forwarded
def test_status_event_for_unknown_order(orders):
    channel = FakeChannel()

    orders.on_status(channel, FakeMethod(), None, json.dumps({
        'order_id': 999999, 'status': 'cooking'}))

    assert channel.published == []
    assert channel.acked == [1]


# 9. The menu RPC client maps 404 to None and transport errors to MenuUnavailable
def test_menu_client_response_mapping(orders):
    client = orders.MenuClient('localhost')

    class Rpc404:
        def call(self, queue, request):
            return {'status': 404, 'body': {'error': 'Pizza not found'}}

    class Rpc500:
        def call(self, queue, request):
            return {'status': 500, 'body': {'error': 'boom'}}

    class RpcBroken:
        def call(self, queue, request):
            raise TimeoutError('no response')

    client.rpc = Rpc404()
    assert client.get_pizza('sushi') is None

    client.rpc = Rpc500()
    with pytest.raises(orders.MenuUnavailable):
        client.get_pizza('pepperoni')

    client.rpc = RpcBroken()
    with pytest.raises(orders.MenuUnavailable):
        client.get_pizza('pepperoni')


# 10. When the menu service is down, order creation returns 503
def test_create_order_when_menu_is_unavailable(orders, monkeypatch):
    class BrokenMenu:
        def get_pizza(self, code):
            raise orders.MenuUnavailable('connection refused')

    monkeypatch.setattr(orders.service, 'menu', BrokenMenu())

    status, body = orders.handle_request({
        'action': 'create_order',
        'payload': {'pizza': 'Pepperoni', 'address': '1 Main Street'},
    })

    assert status == 503
    assert 'Menu service is unavailable' in body['error']
