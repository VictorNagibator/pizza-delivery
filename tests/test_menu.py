# 1. The default menu is seeded and read from the menu database
def test_seed_and_read_menu(menu_service):
    assert menu_service.seed() is False

    menu = menu_service.get_menu()
    assert menu['pepperoni']['name'] == 'Pepperoni'
    assert menu['pepperoni']['price'] == 550
    assert len(menu) == 5


# 2. A pizza is found by code or by a human-readable name
def test_get_pizza_normalizes_name(menu_service):
    by_code = menu_service.get_pizza('four_cheese')
    by_name = menu_service.get_pizza('Four Cheese')

    assert by_code == by_name
    assert by_name['price'] == 650


# 3. An unknown pizza returns None
def test_unknown_pizza(menu_service):
    assert menu_service.get_pizza('sushi') is None
    assert menu_service.get_pizza(None) is None


# 4. The RPC handler exposes the menu and one pizza
def test_rpc_handlers(menu_module):
    status, body = menu_module.handle_request({'action': 'menu'})
    assert status == 200
    assert body['margherita']['price'] == 450

    status, body = menu_module.handle_request({
        'action': 'get_pizza', 'payload': {'pizza': 'Pepperoni'}})
    assert status == 200
    assert body['code'] == 'pepperoni'

    status, body = menu_module.handle_request({
        'action': 'get_pizza', 'payload': {'pizza': 'sushi'}})
    assert status == 404

    status, _ = menu_module.handle_request({'action': 'unknown'})
    assert status == 404
