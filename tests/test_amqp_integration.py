import json
import os
import threading
import time
import uuid

import pika
import pytest

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
KITCHEN_QUEUE = 'kitchen_orders'
DELIVERY_QUEUE = 'delivery_orders'
STATUS_QUEUE = 'order_status'


# Try to connect to the broker: if it is not there, the tests are skipped
def _broker_available():
    try:
        pika.BlockingConnection(
            pika.ConnectionParameters(host=RABBITMQ_HOST, socket_timeout=3)
        ).close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _broker_available(),
    reason='RabbitMQ is unavailable, integration AMQP tests are skipped'
)


@pytest.fixture
def channel():
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
    ch = connection.channel()
    for queue in (KITCHEN_QUEUE, DELIVERY_QUEUE, STATUS_QUEUE):
        ch.queue_declare(queue=queue, durable=True)
        ch.queue_purge(queue=queue)
    yield ch
    connection.close()


# Minimal RPC server running the orders handler in a background thread.
# The connection is created and used only inside the thread (pika is not thread safe).
class RpcServer(threading.Thread):
    def __init__(self, queue, handler):
        super().__init__(daemon=True)
        self.queue = queue
        self.handler = handler
        self.connection = None
        self.ready = threading.Event()

    def run(self):
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = self.connection.channel()
        channel.queue_declare(queue=self.queue, durable=False)
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue=self.queue, on_message_callback=self.handler)
        self.ready.set()
        try:
            channel.start_consuming()
        except Exception:
            pass

    def stop(self):
        if self.connection is not None:
            self.connection.add_callback_threadsafe(self.connection.close)
        self.join(timeout=5)


@pytest.fixture
def rpc_server(orders, orders_module):
    # The 'orders' fixture creates the test database tables
    queue = f'orders_rpc_test_{uuid.uuid4().hex}'
    server = RpcServer(queue, orders_module.on_request)
    server.start()
    assert server.ready.wait(timeout=5)
    yield server, queue
    server.stop()


# Publishes an order to the kitchen queue and returns its (method, properties, body)
def _take_order(channel, order):
    channel.basic_publish(
        exchange='',
        routing_key=KITCHEN_QUEUE,
        body=json.dumps(order, ensure_ascii=False),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    method, properties, body = channel.basic_get(queue=KITCHEN_QUEUE, auto_ack=False)
    assert method is not None
    return method, properties, body


# A known pizza goes through the kitchen and reaches the delivery queue
def test_kitchen_amqp_flow(channel, kitchen_module, monkeypatch):
    monkeypatch.setattr(kitchen_module.time, 'sleep', lambda seconds: None)

    method, properties, body = _take_order(channel, {
        'order_id': 9001,
        'pizza': 'pepperoni',
        'quantity': 1,
        'address': '7 Gagarin Street',
    })

    kitchen_module.process_order(channel, method, properties, body)

    # The order went to delivery
    delivery_method, _, delivery_body = channel.basic_get(queue=DELIVERY_QUEUE, auto_ack=True)
    assert delivery_method is not None
    assert json.loads(delivery_body)['order_id'] == 9001

    # And the cooking/ready statuses were sent
    statuses = []
    for _ in range(2):
        status_method, _, status_body = channel.basic_get(queue=STATUS_QUEUE, auto_ack=True)
        assert status_method is not None
        statuses.append(json.loads(status_body)['status'])
    assert statuses == ['cooking', 'ready']


# An unknown pizza is rejected and never reaches delivery
def test_kitchen_amqp_rejects_unknown_pizza(channel, kitchen_module, monkeypatch):
    monkeypatch.setattr(kitchen_module.time, 'sleep', lambda seconds: None)

    method, properties, body = _take_order(channel, {
        'order_id': 9002,
        'pizza': 'sushi',
        'quantity': 1,
        'address': '8 Gagarin Street',
    })

    kitchen_module.process_order(channel, method, properties, body)

    status_method, _, status_body = channel.basic_get(queue=STATUS_QUEUE, auto_ack=True)
    assert status_method is not None
    assert json.loads(status_body)['status'] == 'rejected'

    delivery_method, _, _ = channel.basic_get(queue=DELIVERY_QUEUE, auto_ack=True)
    assert delivery_method is None


# The gateway RPC client reaches the orders handler over a real broker
def test_orders_rpc_menu(rpc_server, gateway):
    _, queue = rpc_server

    response = gateway.rpc.call(queue, {'action': 'menu', 'payload': None})

    assert response['status'] == 200
    assert 'margherita' in response['body']


# A created order is published to the kitchen queue
def test_orders_rpc_creates_order(rpc_server, gateway, channel):
    _, queue = rpc_server

    response = gateway.rpc.call(queue, {
        'action': 'create_order',
        'payload': {'pizza': 'Pepperoni', 'address': '1 Main Street', 'quantity': 1},
    })

    assert response['status'] == 202
    assert response['body']['pizza_name'] == 'Pepperoni'

    method, _, body = channel.basic_get(queue=KITCHEN_QUEUE, auto_ack=True)
    assert method is not None
    assert json.loads(body)['pizza'] == 'pepperoni'
