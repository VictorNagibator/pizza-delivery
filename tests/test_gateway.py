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


# 8. Menu management and search routes go to the menu queue
def test_menu_management_routes(gateway, gateway_client, monkeypatch):
    fake = FakeRpc({'status': 200, 'body': {}})
    monkeypatch.setattr(gateway, 'rpc', fake)

    gateway_client.get('/menu/search?q=cheese&min_price=400&max_price=700')
    gateway_client.post('/menu', json={'code': 'siciliana', 'name': 'Siciliana', 'price': 700})
    gateway_client.patch('/menu/pepperoni/price', json={'price': 600})

    assert fake.calls == [
        (gateway.MENU_QUEUE, {
            'action': 'search_menu',
            'payload': {'q': 'cheese', 'min_price': '400', 'max_price': '700'},
        }),
        (gateway.MENU_QUEUE, {
            'action': 'add_pizza',
            'payload': {'code': 'siciliana', 'name': 'Siciliana', 'price': 700},
        }),
        (gateway.MENU_QUEUE, {
            'action': 'update_price',
            'payload': {'code': 'pepperoni', 'price': 600},
        }),
    ]


# 9. Order statistics, status filtering and cancellation go to orders
def test_order_management_routes(gateway, gateway_client, monkeypatch):
    fake = FakeRpc({'status': 200, 'body': {}})
    monkeypatch.setattr(gateway, 'rpc', fake)

    gateway_client.get('/orders/stats')
    gateway_client.get('/orders/status/delivered')
    gateway_client.post('/orders/5/cancel')

    assert fake.calls == [
        (gateway.ORDERS_QUEUE, {'action': 'get_order_stats', 'payload': None}),
        (gateway.ORDERS_QUEUE, {
            'action': 'list_orders_by_status',
            'payload': {'status': 'delivered'},
        }),
        (gateway.ORDERS_QUEUE, {
            'action': 'cancel_order',
            'payload': {'order_id': 5},
        }),
    ]


# 10. History latest/events/stats routes go to the history queue
def test_history_extended_routes(gateway, gateway_client, monkeypatch):
    fake = FakeRpc({'status': 200, 'body': {}})
    monkeypatch.setattr(gateway, 'rpc', fake)

    gateway_client.get('/orders/5/history/latest')
    gateway_client.get('/history/events?limit=10&offset=2&status=rejected')
    gateway_client.get('/history/stats')

    assert fake.calls == [
        (gateway.HISTORY_QUEUE, {
            'action': 'get_latest_status',
            'payload': {'order_id': 5},
        }),
        (gateway.HISTORY_QUEUE, {
            'action': 'list_events',
            'payload': {'limit': '10', 'offset': '2', 'status': 'rejected'},
        }),
        (gateway.HISTORY_QUEUE, {'action': 'get_history_stats', 'payload': None}),
    ]


# 11. Kitchen management routes go to the kitchen queue
def test_kitchen_routes(gateway, gateway_client, monkeypatch):
    fake = FakeRpc({'status': 200, 'body': {}})
    monkeypatch.setattr(gateway, 'rpc', fake)

    gateway_client.get('/kitchen/recipes')
    gateway_client.get('/kitchen/recipes/pepperoni')
    gateway_client.get('/kitchen/stock')
    gateway_client.post('/kitchen/availability', json={'pizza': 'pepperoni', 'quantity': 2})
    gateway_client.post('/kitchen/stock/basil/restock', json={'amount': 50})
    gateway_client.put('/kitchen/stock/basil', json={'amount': 100})
    gateway_client.get('/kitchen/orders?limit=5')
    gateway_client.get('/kitchen/orders/3')

    assert fake.calls == [
        (gateway.KITCHEN_QUEUE, {'action': 'recipes', 'payload': None}),
        (gateway.KITCHEN_QUEUE, {'action': 'recipe', 'payload': {'code': 'pepperoni'}}),
        (gateway.KITCHEN_QUEUE, {'action': 'stock', 'payload': None}),
        (gateway.KITCHEN_QUEUE, {
            'action': 'check_availability',
            'payload': {'pizza': 'pepperoni', 'quantity': 2},
        }),
        (gateway.KITCHEN_QUEUE, {
            'action': 'restock',
            'payload': {'ingredient': 'basil', 'amount': 50},
        }),
        (gateway.KITCHEN_QUEUE, {
            'action': 'set_stock',
            'payload': {'ingredient': 'basil', 'amount': 100},
        }),
        (gateway.KITCHEN_QUEUE, {'action': 'orders', 'payload': {'limit': '5'}}),
        (gateway.KITCHEN_QUEUE, {'action': 'order', 'payload': {'order_id': 3}}),
    ]


# 12. Delivery management routes go to the delivery queue
def test_delivery_routes(gateway, gateway_client, monkeypatch):
    fake = FakeRpc({'status': 200, 'body': {}})
    monkeypatch.setattr(gateway, 'rpc', fake)

    gateway_client.get('/delivery/couriers')
    gateway_client.post('/delivery/couriers', json={'name': 'Nina', 'phone': '+7-900'})
    gateway_client.get('/delivery/couriers/2')
    gateway_client.get('/delivery/deliveries?limit=10')
    gateway_client.get('/delivery/deliveries/5')
    gateway_client.get('/delivery/stats')

    assert fake.calls == [
        (gateway.DELIVERY_QUEUE, {'action': 'couriers', 'payload': None}),
        (gateway.DELIVERY_QUEUE, {
            'action': 'register_courier',
            'payload': {'name': 'Nina', 'phone': '+7-900'},
        }),
        (gateway.DELIVERY_QUEUE, {'action': 'courier', 'payload': {'courier_id': 2}}),
        (gateway.DELIVERY_QUEUE, {'action': 'deliveries', 'payload': {'limit': '10'}}),
        (gateway.DELIVERY_QUEUE, {'action': 'delivery', 'payload': {'order_id': 5}}),
        (gateway.DELIVERY_QUEUE, {'action': 'delivery_stats', 'payload': None}),
    ]


# 13. Kitchen and delivery failures are reported separately
def test_kitchen_and_delivery_unavailable(gateway, gateway_client, monkeypatch):
    fake = FakeRpc(error=TimeoutError('no response'))
    monkeypatch.setattr(gateway, 'rpc', fake)

    response = gateway_client.get('/kitchen/stock')
    assert response.status_code == 503
    assert 'Kitchen service is unavailable' in response.get_json()['error']

    response = gateway_client.get('/delivery/couriers')
    assert response.status_code == 503
    assert 'Delivery service is unavailable' in response.get_json()['error']
