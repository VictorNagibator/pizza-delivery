import json

import pytest


# RabbitMQ channel stub: records acknowledgements
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


class FakeMethod:
    def __init__(self, delivery_tag=1):
        self.delivery_tag = delivery_tag


# 1. Status events are stored in arrival order with courier and reason
def test_record_and_read_history(history):
    assert history.record({'order_id': 1, 'status': 'new'}) is True
    assert history.record({'order_id': 1, 'status': 'cooking'}) is True
    assert history.record({
        'order_id': 1, 'status': 'rejected', 'reason': 'Out of ingredients'}) is True

    entries = history.get_history(1)
    assert [entry['status'] for entry in entries] == ['new', 'cooking', 'rejected']
    assert entries[-1]['reason'] == 'Out of ingredients'


# 2. A redelivered event does not create a duplicate (idempotent consumer)
def test_duplicate_event_is_ignored(history):
    assert history.record({'order_id': 2, 'status': 'new'}) is True
    assert history.record({'order_id': 2, 'status': 'new'}) is False

    assert len(history.get_history(2)) == 1


# 3. An unknown order has no history
def test_unknown_order_has_no_history(history):
    assert history.get_history(999) is None


# 4. Invalid events are rejected instead of being stored
def test_invalid_event_is_rejected(history):
    with pytest.raises(ValueError):
        history.record({'status': 'new'})

    with pytest.raises(ValueError):
        history.record({'order_id': 'abc', 'status': 'new'})


# 5. The RPC handler returns the history or 404
def test_rpc_handler(history_module):
    history_module.history.record({'order_id': 10, 'status': 'new'})
    history_module.history.record({'order_id': 10, 'status': 'delivered'})

    status, body = history_module.handle_request({
        'action': 'get_history', 'payload': {'order_id': 10}})
    assert status == 200
    assert [entry['status'] for entry in body] == ['new', 'delivered']

    status, _ = history_module.handle_request({
        'action': 'get_history', 'payload': {'order_id': 404}})
    assert status == 404


# 6. The AMQP event consumer stores the event and acknowledges the message
def test_event_consumer(history_module):
    channel = FakeChannel()
    body = json.dumps({
        'order_id': 11,
        'status': 'rejected',
        'reason': 'Out of ingredients',
    })

    history_module.on_event(channel, FakeMethod(delivery_tag=7), None, body)

    entries = history_module.history.get_history(11)
    assert entries[0]['status'] == 'rejected'
    assert entries[0]['reason'] == 'Out of ingredients'
    assert channel.acked == [7]
