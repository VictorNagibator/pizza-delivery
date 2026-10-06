class FakeRpc:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def call(self, queue, request):
        self.calls.append((queue, request))
        if self.error:
            raise self.error
        return self.response


# 1. The gateway calls the orders queue and proxies the menu
def test_menu_is_proxied(gateway, gateway_client, monkeypatch):
    fake = FakeRpc({'status': 200, 'body': {'margherita': {'name': 'Margherita', 'price': 450}}})
    monkeypatch.setattr(gateway, 'rpc', fake)

    response = gateway_client.get('/menu')

    assert response.status_code == 200
    assert response.get_json()['margherita']['price'] == 450
    queue, request = fake.calls[0]
    assert queue == gateway.ORDERS_QUEUE
    assert request['action'] == 'menu'


# 2. Creating an order forwards the payload and returns the orders status code
def test_create_order_is_proxied(gateway, gateway_client, monkeypatch):
    fake = FakeRpc({'status': 202, 'body': {'order_id': 10, 'pizza': 'pepperoni'}})
    monkeypatch.setattr(gateway, 'rpc', fake)

    response = gateway_client.post('/order', json={'pizza': 'Pepperoni', 'address': '1 Main Street'})

    assert response.status_code == 202
    assert response.get_json()['order_id'] == 10
    queue, request = fake.calls[0]
    assert request['action'] == 'create_order'
    assert request['payload'] == {'pizza': 'Pepperoni', 'address': '1 Main Street'}


# 3. The orders list is proxied
def test_list_orders_is_proxied(gateway, gateway_client, monkeypatch):
    fake = FakeRpc({'status': 200, 'body': [{'id': 1}, {'id': 2}]})
    monkeypatch.setattr(gateway, 'rpc', fake)

    response = gateway_client.get('/orders')

    assert response.status_code == 200
    assert len(response.get_json()) == 2
    assert fake.calls[0][1]['action'] == 'list_orders'


# 4. A single order and its history are proxied, including 404
def test_get_order_and_history_is_proxied(gateway, gateway_client, monkeypatch):
    fake = FakeRpc({'status': 200, 'body': {'id': 7, 'status': 'delivered'}})
    monkeypatch.setattr(gateway, 'rpc', fake)

    assert gateway_client.get('/orders/7').get_json()['status'] == 'delivered'
    gateway_client.get('/orders/7/history')
    assert fake.calls == [
        (gateway.ORDERS_QUEUE, {'action': 'get_order', 'payload': {'order_id': 7}}),
        (gateway.ORDERS_QUEUE, {'action': 'get_history', 'payload': {'order_id': 7}}),
    ]

    missing = FakeRpc({'status': 404, 'body': {'error': 'Order not found'}})
    monkeypatch.setattr(gateway, 'rpc', missing)
    assert gateway_client.get('/orders/999').status_code == 404


# 5. When the orders service does not answer, the gateway returns 503
def test_orders_service_unavailable(gateway, gateway_client, monkeypatch):
    fake = FakeRpc(error=TimeoutError('no response'))
    monkeypatch.setattr(gateway, 'rpc', fake)

    response = gateway_client.get('/orders')

    assert response.status_code == 503
    assert 'unavailable' in response.get_json()['error']
