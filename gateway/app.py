import os
from flask import Flask, request, jsonify

from rpc_client import RpcClient

app = Flask(__name__)

# RabbitMQ address comes from the environment
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')


ORDERS_QUEUE = os.getenv('ORDERS_RPC_QUEUE', 'orders_rpc')

rpc = RpcClient(RABBITMQ_HOST)


# Calls the orders service over AMQP RPC and maps failures to a 503 response
def call_orders(action, payload=None):
    try:
        return rpc.call(ORDERS_QUEUE, {'action': action, 'payload': payload})
    except Exception as error:
        return {'status': 503, 'body': {'error': f'Orders service is unavailable: {error}'}}


# Builds an HTTP response from the RPC reply
def reply(response):
    return jsonify(response['body']), response['status']


# Returns the pizzeria menu
@app.route('/menu', methods=['GET'])
def get_menu():
    return reply(call_orders('menu'))


# Creates an order
@app.route('/order', methods=['POST'])
def create_order():
    return reply(call_orders('create_order', request.get_json(silent=True)))


# Returns all orders
@app.route('/orders', methods=['GET'])
def list_orders():
    return reply(call_orders('list_orders'))


# Returns a single order by id
@app.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    return reply(call_orders('get_order', {'order_id': order_id}))


# Returns the status history of an order
@app.route('/orders/<int:order_id>/history', methods=['GET'])
def get_order_history(order_id):
    return reply(call_orders('get_history', {'order_id': order_id}))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)