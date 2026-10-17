import os
from flask import Flask, request, jsonify

from rpc_client import RpcClient

app = Flask(__name__)

# RabbitMQ address comes from the environment
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')

# Every backend service is reached by its own queue
MENU_QUEUE = os.getenv('MENU_RPC_QUEUE', 'menu_rpc')
ORDERS_QUEUE = os.getenv('ORDERS_RPC_QUEUE', 'orders_rpc')
HISTORY_QUEUE = os.getenv('HISTORY_RPC_QUEUE', 'history_rpc')
KITCHEN_QUEUE = os.getenv('KITCHEN_RPC_QUEUE', 'kitchen_rpc')
DELIVERY_QUEUE = os.getenv('DELIVERY_RPC_QUEUE', 'delivery_rpc')

rpc = RpcClient(RABBITMQ_HOST)


# Calls a service over AMQP RPC and maps failures to a 503 response
def call_service(queue, action, payload=None, service='Service'):
    try:
        return rpc.call(queue, {'action': action, 'payload': payload})
    except Exception as error:
        return {'status': 503, 'body': {'error': f'{service} service is unavailable: {error}'}}


# Shortcuts for the backend services used by the HTTP API
def call_menu(action, payload=None):
    return call_service(MENU_QUEUE, action, payload, 'Menu')


def call_orders(action, payload=None):
    return call_service(ORDERS_QUEUE, action, payload, 'Orders')


def call_history(action, payload=None):
    return call_service(HISTORY_QUEUE, action, payload, 'History')


def call_kitchen(action, payload=None):
    return call_service(KITCHEN_QUEUE, action, payload, 'Kitchen')


def call_delivery(action, payload=None):
    return call_service(DELIVERY_QUEUE, action, payload, 'Delivery')


# Builds an HTTP response from the RPC reply
def reply(response):
    return jsonify(response['body']), response['status']


# Returns a query parameter or None
def query(name):
    return request.args.get(name)


# Returns a JSON body or an empty object
def body():
    return request.get_json(silent=True) or {}


# Menu

@app.route('/menu', methods=['GET'])
def get_menu():
    return reply(call_menu('menu'))


@app.route('/menu/search', methods=['GET'])
def search_menu():
    return reply(call_menu('search_menu', {
        'q': query('q'),
        'min_price': query('min_price'),
        'max_price': query('max_price'),
    }))


@app.route('/menu', methods=['POST'])
def add_pizza():
    return reply(call_menu('add_pizza', body()))


@app.route('/menu/<code>/price', methods=['PATCH'])
def update_price(code):
    return reply(call_menu('update_price', {
        'code': code,
        'price': body().get('price'),
    }))


# Orders 

@app.route('/order', methods=['POST'])
def create_order():
    return reply(call_orders('create_order', request.get_json(silent=True)))


@app.route('/orders', methods=['GET'])
def list_orders():
    return reply(call_orders('list_orders'))


@app.route('/orders/stats', methods=['GET'])
def order_stats():
    return reply(call_orders('get_order_stats'))


@app.route('/orders/status/<status>', methods=['GET'])
def list_orders_by_status(status):
    return reply(call_orders('list_orders_by_status', {'status': status}))


@app.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    return reply(call_orders('get_order', {'order_id': order_id}))


@app.route('/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    return reply(call_orders('cancel_order', {'order_id': order_id}))


# History

@app.route('/orders/<int:order_id>/history', methods=['GET'])
def get_order_history(order_id):
    return reply(call_history('get_history', {'order_id': order_id}))


@app.route('/orders/<int:order_id>/history/latest', methods=['GET'])
def get_latest_status(order_id):
    return reply(call_history('get_latest_status', {'order_id': order_id}))


@app.route('/history/events', methods=['GET'])
def list_events():
    return reply(call_history('list_events', {
        'limit': query('limit'),
        'offset': query('offset'),
        'status': query('status'),
    }))


@app.route('/history/stats', methods=['GET'])
def history_stats():
    return reply(call_history('get_history_stats'))


# Kitchen

@app.route('/kitchen/recipes', methods=['GET'])
def kitchen_recipes():
    return reply(call_kitchen('recipes'))


@app.route('/kitchen/recipes/<code>', methods=['GET'])
def kitchen_recipe(code):
    return reply(call_kitchen('recipe', {'code': code}))


@app.route('/kitchen/stock', methods=['GET'])
def kitchen_stock():
    return reply(call_kitchen('stock'))


@app.route('/kitchen/stock/<ingredient>/restock', methods=['POST'])
def kitchen_restock(ingredient):
    return reply(call_kitchen('restock', {
        'ingredient': ingredient,
        'amount': body().get('amount'),
    }))


@app.route('/kitchen/stock/<ingredient>', methods=['PUT'])
def kitchen_set_stock(ingredient):
    return reply(call_kitchen('set_stock', {
        'ingredient': ingredient,
        'amount': body().get('amount'),
    }))


@app.route('/kitchen/availability', methods=['POST'])
def kitchen_availability():
    return reply(call_kitchen('check_availability', body()))


@app.route('/kitchen/orders', methods=['GET'])
def kitchen_orders():
    return reply(call_kitchen('orders', {'limit': query('limit')}))


@app.route('/kitchen/orders/<int:order_id>', methods=['GET'])
def kitchen_order(order_id):
    return reply(call_kitchen('order', {'order_id': order_id}))


# Delivery

@app.route('/delivery/couriers', methods=['GET'])
def delivery_couriers():
    return reply(call_delivery('couriers'))


@app.route('/delivery/couriers', methods=['POST'])
def delivery_register_courier():
    return reply(call_delivery('register_courier', body()))


@app.route('/delivery/couriers/<int:courier_id>', methods=['GET'])
def delivery_courier(courier_id):
    return reply(call_delivery('courier', {'courier_id': courier_id}))


@app.route('/delivery/deliveries', methods=['GET'])
def delivery_deliveries():
    return reply(call_delivery('deliveries', {'limit': query('limit')}))


@app.route('/delivery/deliveries/<int:order_id>', methods=['GET'])
def delivery_delivery(order_id):
    return reply(call_delivery('delivery', {'order_id': order_id}))


@app.route('/delivery/stats', methods=['GET'])
def delivery_stats():
    return reply(call_delivery('delivery_stats'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
