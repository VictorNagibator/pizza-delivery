import json


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


class FakeMethod:
    def __init__(self, delivery_tag=1):
        self.delivery_tag = delivery_tag


def _stock_value(kitchen, ingredient):
    return next(item['stock'] for item in kitchen.get_stock() if item['name'] == ingredient)


# 1. A known pizza is cooked, ingredients are consumed and the journal is written
def test_known_pizza_is_cooked(kitchen):
    before = _stock_value(kitchen, 'pepperoni')

    result = kitchen.cook(1, 'pepperoni', 2)

    assert result['status'] == 'ready'
    assert result['pizza_name'] == 'Pepperoni'
    assert result['cook_time'] == 3
    # One pizza needs 80 g of pepperoni
    assert _stock_value(kitchen, 'pepperoni') == before - 160

    saved = kitchen.get_order(1)
    assert saved['status'] == 'ready'
    assert saved['quantity'] == 2


# 2. An unknown pizza is rejected and written to the journal
def test_unknown_pizza_is_rejected(kitchen):
    result = kitchen.cook(2, 'sushi', 1)

    assert result['status'] == 'rejected'
    assert 'not in the kitchen menu' in result['reason']

    saved = kitchen.get_order(2)
    assert saved['status'] == 'rejected'


# 3. An order is rejected when there are not enough ingredients
def test_out_of_stock_is_rejected(kitchen):
    kitchen.set_stock('mozzarella', 0)

    result = kitchen.cook(3, 'margherita', 1)

    assert result['status'] == 'rejected'
    assert 'Out of ingredients' in result['reason']
    assert 'mozzarella' in result['reason']


# 4. Recipes and stock are read from the database
def test_recipe_and_stock_loaded_from_db(kitchen):
    recipe = kitchen.get_recipe('diablo')
    assert recipe['cook_time'] == 4

    ingredients = {item['name']: item for item in kitchen.get_stock()}
    assert 'dough' in ingredients
    assert ingredients['dough']['unit'] == 'pcs'

    # Restocking also works
    before = ingredients['basil']['stock']
    kitchen.restock('basil', 50)
    assert _stock_value(kitchen, 'basil') == before + 50


# 5. The AMQP handler publishes statuses and forwards the order to delivery
def test_process_order_forwards_to_delivery(kitchen_module, monkeypatch):
    # Skip the cooking delay so the test runs fast
    monkeypatch.setattr(kitchen_module.time, 'sleep', lambda seconds: None)

    channel = FakeChannel()
    body = json.dumps({
        'order_id': 7,
        'pizza': 'margherita',
        'quantity': 1,
        'address': '10 Pushkin Street',
    })

    kitchen_module.process_order(channel, FakeMethod(), None, body)

    routes = [item['routing_key'] for item in channel.published]
    # Two statuses (cooking, ready) and one message to delivery
    assert routes.count(kitchen_module.STATUS_QUEUE) == 2
    assert kitchen_module.DELIVERY_QUEUE in routes

    delivery = next(item['body'] for item in channel.published
                    if item['routing_key'] == kitchen_module.DELIVERY_QUEUE)
    assert delivery['order_id'] == 7
    assert delivery['address'] == '10 Pushkin Street'

    # The order is written to the kitchen database
    assert kitchen_module.kitchen.get_order(7)['status'] == 'ready'
    assert channel.acked == [1]
