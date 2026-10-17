import json

import pytest

from delivery_logic import CourierAlreadyExists


# RabbitMQ channel stub
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


# 1. A new order goes to the least loaded free courier
def test_assign_prefers_least_loaded_courier(dispatcher):
    # Courier #1 completes a delivery and stays free with count = 1
    first = dispatcher.assign(1, '1 Main Street')
    dispatcher.complete(1)

    # Prior load: courier #1 has one delivery, the rest have none
    load = {c['id']: c['deliveries_count'] for c in dispatcher.list_couriers()}
    assert load[first['courier_id']] == 1

    # The next order must avoid the loaded courier and pick a minimum-load one
    second = dispatcher.assign(2, '2 Lenina Avenue')

    assert second['courier_id'] != first['courier_id']
    assert load[second['courier_id']] == min(load.values())


# 2. Orders are distributed among free couriers
def test_assign_picks_free_couriers(dispatcher):
    courier_ids = []
    for order_id in range(1, 5):
        result = dispatcher.assign(order_id, f'{order_id} Test Street')
        assert result['status'] == 'assigned'
        courier_ids.append(result['courier_id'])

    # All four couriers received one order
    assert sorted(courier_ids) == [1, 2, 3, 4]


# 3. Assignment marks the courier busy and increments the counter
def test_assign_marks_courier_busy(dispatcher):
    result = dispatcher.assign(100, '1 Main Street')

    courier = next(c for c in dispatcher.list_couriers() if c['id'] == result['courier_id'])
    assert courier['status'] == 'busy'
    assert courier['deliveries_count'] == 1


# 4. Completing a delivery frees the courier
def test_complete_frees_courier(dispatcher):
    result = dispatcher.assign(200, '2 Lenina Avenue')

    assert dispatcher.complete(200) is True

    courier = next(c for c in dispatcher.list_couriers() if c['id'] == result['courier_id'])
    assert courier['status'] == 'free'

    delivery = dispatcher.get_delivery(200)
    assert delivery['status'] == 'delivered'


# 5. If all couriers are busy, the order is queued
def test_all_busy_puts_order_in_queue(dispatcher):
    for order_id in range(1, 5):
        dispatcher.assign(order_id, f'{order_id} Test Street')

    result = dispatcher.assign(5, '5 Test Street')

    assert result['status'] == 'queued'
    assert dispatcher.get_delivery(5)['status'] == 'queued'


# 6. A courier that became free picks up the queued order
def test_queued_order_dispatched_after_complete(dispatcher):
    for order_id in range(1, 5):
        dispatcher.assign(order_id, f'{order_id} Test Street')

    assert dispatcher.assign(5, '5 Test Street')['status'] == 'queued'

    # Free one courier and give the queued order to them
    dispatcher.complete(1)

    result = dispatcher.dispatch_queued()
    assert result is not None
    assert result['order_id'] == 5
    assert result['courier_id'] == 1
    assert dispatcher.get_delivery(5)['status'] == 'delivering'


# 7. The handler publishes delivering/delivered statuses and closes the delivery
def test_process_delivery_publishes_statuses(delivery_module, monkeypatch):
    monkeypatch.setattr(delivery_module.time, 'sleep', lambda seconds: None)

    channel = FakeChannel()
    body = json.dumps({
        'order_id': 500,
        'pizza': 'pepperoni',
        'quantity': 1,
        'address': '7 Anatoliy Street',
    })

    delivery_module.process_delivery(channel, FakeMethod(), None, body)

    statuses = [item['body']['status'] for item in channel.published
                if item['routing_key'] == delivery_module.STATUS_QUEUE]
    assert statuses == ['delivering', 'delivered']

    assert delivery_module.dispatcher.get_delivery(500)['status'] == 'delivered'
    assert channel.acked == [1]


# 8. Couriers can be listed, looked up, registered and aggregated
def test_couriers_and_stats(dispatcher):
    couriers = dispatcher.list_couriers()
    assert len(couriers) == 4

    created = dispatcher.register_courier('Nina', '+7-900-000-02-01')
    assert created['name'] == 'Nina'
    assert created['status'] == 'free'

    assert dispatcher.get_courier(created['id'])['name'] == 'Nina'
    assert dispatcher.get_courier(999999) is None

    with pytest.raises(CourierAlreadyExists):
        dispatcher.register_courier('Nina', '+7-900-000-02-02')

    with pytest.raises(ValueError):
        dispatcher.register_courier('', '')

    dispatcher.assign(300, '3 Main Street')
    dispatcher.complete(300)

    stats = dispatcher.get_stats()
    assert stats['total_deliveries'] == 1
    assert stats['by_status']['delivered'] == 1
    assert stats['couriers']['total'] == 5
    assert stats['couriers']['free'] == 5


# 9. Deliveries can be listed
def test_list_deliveries(dispatcher):
    dispatcher.assign(400, '4 Main Street')
    dispatcher.assign(401, '5 Main Street')

    deliveries = dispatcher.list_deliveries(limit=1)
    assert len(deliveries) == 1
    assert deliveries[0]['order_id'] in (400, 401)


# 10. The RPC handler exposes couriers, deliveries and statistics
def test_rpc_handler(delivery_module):
    status, body = delivery_module.handle_request({'action': 'couriers'})
    assert status == 200
    assert len(body) >= 4
    assert any(courier['name'] == 'Alex' for courier in body)

    status, created = delivery_module.handle_request({
        'action': 'register_courier',
        'payload': {'name': 'RPC Courier', 'phone': '+7-900-000-03-01'},
    })
    assert status == 201
    assert created['name'] == 'RPC Courier'

    status, _ = delivery_module.handle_request({
        'action': 'register_courier',
        'payload': {'name': 'RPC Courier', 'phone': '+7-900-000-03-02'},
    })
    assert status == 409

    status, body = delivery_module.handle_request({
        'action': 'courier', 'payload': {'courier_id': created['id']}})
    assert status == 200

    status, _ = delivery_module.handle_request({
        'action': 'courier', 'payload': {'courier_id': 999999}})
    assert status == 404

    delivery_module.dispatcher.assign(500, '6 Main Street')

    status, body = delivery_module.handle_request({
        'action': 'deliveries', 'payload': {'limit': 10}})
    assert status == 200
    assert any(item['order_id'] == 500 for item in body)

    status, body = delivery_module.handle_request({
        'action': 'delivery', 'payload': {'order_id': 500}})
    assert status == 200
    assert body['status'] == 'delivering'

    status, _ = delivery_module.handle_request({
        'action': 'delivery', 'payload': {'order_id': 999999}})
    assert status == 404

    status, body = delivery_module.handle_request({'action': 'delivery_stats'})
    assert status == 200
    assert 'by_status' in body
