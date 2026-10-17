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


# Builds an HTTP response from the RPC reply
def reply(response):
    return jsonify(response['body']), response['status']


# Returns the pizzeria menu (menu service)
@app.route('/menu', methods=['GET'])
def get_menu():
    return reply(call_menu('menu'))


# Creates an order (orders service)
@app.route('/order', methods=['POST'])
def create_order():
    return reply(call_orders('create_order', request.get_json(silent=True)))


# Returns all orders (orders service)
@app.route('/orders', methods=['GET'])
def list_orders():
    return reply(call_orders('list_orders'))


# Returns a single order by id (orders service)
@app.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    return reply(call_orders('get_order', {'order_id': order_id}))


# Returns the status history of an order (history service)
@app.route('/orders/<int:order_id>/history', methods=['GET'])
def get_order_history(order_id):
    return reply(call_history('get_history', {'order_id': order_id}))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
