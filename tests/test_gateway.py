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


# 1. The gateway calls the menu queue and proxies the menu
def test_menu_is_proxied(gateway, gateway_client, monkeypatch):
    fake = FakeRpc({'status': 200, 'body': {'margherita': {'name': 'Margherita', 'price': 450}}})
    monkeypatch.setattr(gateway, 'rpc', fake)

    response = gateway_client.get('/menu')

    assert response.status_code == 200
    assert response.get_json()['margherita']['price'] == 450
    queue, request = fake.calls[0]
    assert queue == gateway.MENU_QUEUE
    assert request['action'] == 'menu'


# 2. Creating an order forwards the payload to the orders queue
def test_create_order_is_proxied(gateway, gateway_client, monkeypatch):
    fake = FakeRpc({'status': 202, 'body': {'order_id': 10, 'pizza': 'pepperoni'}})
    monkeypatch.setattr(gateway, 'rpc', fake)

    response = gateway_client.post('/order', json={'pizza': 'Pepperoni', 'address': '1 Main Street'})

    assert response.status_code == 202
    assert response.get_json()['order_id'] == 10
    queue, request = fake.calls[0]
    assert queue == gateway.ORDERS_QUEUE
    assert request['action'] == 'create_order'
    assert request['payload'] == {'pizza': 'Pepperoni', 'address': '1 Main Street'}


# 3. The orders list is proxied to the orders service
def test_list_orders_is_proxied(gateway, gateway_client, monkeypatch):
    fake = FakeRpc({'status': 200, 'body': [{'id': 1}, {'id': 2}]})
    monkeypatch.setattr(gateway, 'rpc', fake)

    response = gateway_client.get('/orders')

    assert response.status_code == 200
    assert len(response.get_json()) == 2
    assert fake.calls[0] == (gateway.ORDERS_QUEUE, {'action': 'list_orders', 'payload': None})


# 4. One order comes from orders, its history comes from the history service
def test_get_order_and_history_use_different_services(gateway, gateway_client, monkeypatch):
    fake = FakeRpc({'status': 200, 'body': {'id': 7, 'status': 'delivered'}})
    monkeypatch.setattr(gateway, 'rpc', fake)

    assert gateway_client.get('/orders/7').get_json()['status'] == 'delivered'
    gateway_client.get('/orders/7/history')

    assert fake.calls == [
        (gateway.ORDERS_QUEUE, {'action': 'get_order', 'payload': {'order_id': 7}}),
        (gateway.HISTORY_QUEUE, {'action': 'get_history', 'payload': {'order_id': 7}}),
    ]


# 5. 404 responses from both services are passed through
def test_not_found_is_proxied(gateway, gateway_client, monkeypatch):
    missing = FakeRpc({'status': 404, 'body': {'error': 'Order not found'}})
    monkeypatch.setattr(gateway, 'rpc', missing)

    assert gateway_client.get('/orders/999').status_code == 404
    assert gateway_client.get('/orders/999/history').status_code == 404


# 6. When a backend service does not answer, the gateway returns 503
def test_orders_service_unavailable(gateway, gateway_client, monkeypatch):
    fake = FakeRpc(error=TimeoutError('no response'))
    monkeypatch.setattr(gateway, 'rpc', fake)

    response = gateway_client.get('/orders')

    assert response.status_code == 503
    assert 'Orders service is unavailable' in response.get_json()['error']


# 7. The history service failure is reported separately
def test_history_service_unavailable(gateway, gateway_client, monkeypatch):
    fake = FakeRpc(error=TimeoutError('no response'))
    monkeypatch.setattr(gateway, 'rpc', fake)

    response = gateway_client.get('/orders/1/history')

    assert response.status_code == 503
    assert 'History service is unavailable' in response.get_json()['error']
