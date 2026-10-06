import json

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


# 3. The menu lives in the database and an unknown pizza raises an error
def test_menu_and_unknown_pizza(order_service):
    menu = order_service.get_menu()
    assert menu['pepperoni']['name'] == 'Pepperoni'
    assert menu['pepperoni']['price'] == 550

    with pytest.raises(ValueError):
        order_service.calculate_price('sushi', 1)


# 4. The RPC handler stores the order, publishes it to the kitchen and replies
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

    # The order was published to the kitchen and stored in the database
    kitchen_messages = [item for item in channel.published if item['routing_key'] == orders.KITCHEN_QUEUE]
    assert len(kitchen_messages) == 1
    assert kitchen_messages[0]['body']['pizza'] == 'diablo'

    saved = orders.service.get_order(order_id)
    assert saved['status'] == 'new'
    assert [entry['status'] for entry in orders.service.get_history(order_id)] == ['new']
    assert channel.acked == [1]


# 5. Orders can be read back and the history updates
def test_read_orders_and_history(order_service):
    created = order_service.create_order({'pizza': 'Hawaiian', 'address': '5 Lenina Avenue'})
    order_id = created['order_id']

    order_service.update_status(order_id, 'cooking')
    order_service.update_status(order_id, 'delivered', courier='Alex')

    listing = order_service.list_orders()
    assert any(order['id'] == order_id for order in listing)

    single = order_service.get_order(order_id)
    assert single['status'] == 'delivered'
    assert single['courier'] == 'Alex'

    history = order_service.get_history(order_id)
    assert [entry['status'] for entry in history] == ['new', 'cooking', 'delivered']
