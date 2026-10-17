import json

import pytest


# RabbitMQ channel stub: records acknowledgements
class FakeChannel:
    def __init__(self):
        self.published = []
        self.acked = []
        self.exchanges = []
        self.bindings = []

    def exchange_declare(self, exchange, exchange_type, durable=False):
        self.exchanges.append((exchange, exchange_type, durable))

    def queue_declare(self, queue, durable=False):
        pass

    def queue_bind(self, queue, exchange, routing_key):
        self.bindings.append((queue, exchange, routing_key))

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


# 11. The consumer declares its topic-exchange binding itself
def test_declares_topic_binding(history_module):
    channel = FakeChannel()

    history_module.declare_topology(channel)

    assert channel.exchanges == [('amq.topic', 'topic', True)]
    assert ('order_history', 'amq.topic', 'order_history') in channel.bindings



# 7. The latest status is returned separately from the full history
def test_latest_status(history):
    history.record({'order_id': 20, 'status': 'new'})
    history.record({'order_id': 20, 'status': 'cooking', 'courier': None})

    latest = history.get_latest_status(20)
    assert latest['status'] == 'cooking'

    assert history.get_latest_status(999) is None


# 8. Recent events can be filtered and paginated
def test_list_events(history):
    history.record({'order_id': 21, 'status': 'new'})
    history.record({'order_id': 21, 'status': 'cooking'})
    history.record({'order_id': 22, 'status': 'new'})
    history.record({'order_id': 22, 'status': 'rejected', 'reason': 'No dough'})

    events = history.list_events(limit=2)
    assert len(events) == 2
    assert events[0]['order_id'] == 22

    rejected = history.list_events(status='rejected')
    assert len(rejected) == 1
    assert rejected[0]['reason'] == 'No dough'

    page = history.list_events(limit=1, offset=1)
    assert len(page) == 1
    assert page[0]['order_id'] == 22
    assert page[0]['status'] == 'new'


# 9. Statistics aggregate events and unique orders
def test_stats(history):
    history.record({'order_id': 30, 'status': 'new'})
    history.record({'order_id': 30, 'status': 'delivered'})
    history.record({'order_id': 31, 'status': 'new'})

    stats = history.get_stats()
    assert stats['total_events'] == 3
    assert stats['total_orders'] == 2
    assert stats['by_status'] == {'delivered': 1, 'new': 2}


# 10. The RPC handler exposes latest status, recent events and statistics
def test_rpc_handler_extended(history_module):
    history_module.history.record({'order_id': 40, 'status': 'new'})
    history_module.history.record({'order_id': 40, 'status': 'cooking'})

    status, body = history_module.handle_request({
        'action': 'get_latest_status', 'payload': {'order_id': 40}})
    assert status == 200
    assert body['status'] == 'cooking'

    status, _ = history_module.handle_request({
        'action': 'get_latest_status', 'payload': {'order_id': 404}})
    assert status == 404

    status, body = history_module.handle_request({
        'action': 'list_events', 'payload': {'limit': 1}})
    assert status == 200
    assert len(body) == 1

    status, _ = history_module.handle_request({
        'action': 'list_events', 'payload': {'limit': 0}})
    assert status == 400

    status, body = history_module.handle_request({'action': 'get_history_stats'})
    assert status == 200
    assert body['total_orders'] == 1
