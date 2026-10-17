import pytest

from menu_logic import PizzaAlreadyExists


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


# 4. A pizza can be added, found by search and repriced
def test_add_search_and_update_price(menu_service):
    created = menu_service.add_pizza({
        'code': 'Siciliana',
        'name': 'Siciliana',
        'price': 700,
    })
    assert created == {'code': 'siciliana', 'name': 'Siciliana', 'price': 700.0}

    with pytest.raises(PizzaAlreadyExists):
        menu_service.add_pizza({
            'code': 'siciliana', 'name': 'Duplicate', 'price': 1})

    found = menu_service.search_menu('sicil')
    assert [item['code'] for item in found] == ['siciliana']

    cheap = menu_service.search_menu(max_price=500)
    assert [item['code'] for item in cheap] == ['margherita']

    updated = menu_service.update_price('Siciliana', 720)
    assert updated['price'] == 720.0

    with pytest.raises(KeyError):
        menu_service.update_price('sushi', 100)


# 5. Search validates the price range and number format
def test_search_validation(menu_service):
    with pytest.raises(ValueError):
        menu_service.search_menu(min_price='cheap')

    with pytest.raises(ValueError):
        menu_service.search_menu(min_price=600, max_price=500)


# 6. The RPC handler exposes the menu, search and menu management
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

    status, body = menu_module.handle_request({
        'action': 'search_menu', 'payload': {'q': 'cheese'}})
    assert status == 200
    assert [item['code'] for item in body] == ['four_cheese']

    status, body = menu_module.handle_request({
        'action': 'add_pizza',
        'payload': {'code': 'siciliana', 'name': 'Siciliana', 'price': 700},
    })
    assert status == 201
    assert body['code'] == 'siciliana'

    status, _ = menu_module.handle_request({
        'action': 'add_pizza',
        'payload': {'code': 'siciliana', 'name': 'Siciliana', 'price': 700},
    })
    assert status == 409

    status, body = menu_module.handle_request({
        'action': 'update_price', 'payload': {'code': 'siciliana', 'price': 720}})
    assert status == 200
    assert body['price'] == 720.0

    status, _ = menu_module.handle_request({
        'action': 'update_price', 'payload': {'code': 'sushi', 'price': 100}})
    assert status == 404

    status, _ = menu_module.handle_request({'action': 'unknown'})
    assert status == 404
