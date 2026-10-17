import os
import json
import time
import pika

from kitchen_logic import Kitchen

# RabbitMQ address comes from the environment
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')
RPC_QUEUE = 'kitchen_rpc'
KITCHEN_QUEUE = 'kitchen_orders'
DELIVERY_QUEUE = 'delivery_orders'
STATUS_QUEUE = 'order_status'

# Kitchen with recipes and stock stored in its own database
kitchen = Kitchen()


# Creates a RabbitMQ connection
def get_rabbitmq_connection():
    credentials = pika.PlainCredentials('guest', 'guest')
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300
    )
    return pika.BlockingConnection(parameters)


# Handles a domain request and returns an HTTP-like (status, body) pair.
# This is pure logic and can be tested without a broker.
def handle_request(request):
    action = request.get('action')
    payload = request.get('payload') or {}

    if action == 'recipes':
        return 200, kitchen.get_recipes()

    if action == 'recipe':
        recipe = kitchen.get_recipe(payload.get('code') or payload.get('pizza'))
        if recipe is None:
            return 404, {'error': 'Recipe not found'}
        return 200, recipe

    if action == 'stock':
        return 200, kitchen.get_stock()

    if action == 'check_availability':
        try:
            result = kitchen.check_availability(
                payload.get('pizza'), payload.get('quantity', 1))
        except KeyError:
            return 404, {'error': 'Recipe not found'}
        except ValueError as error:
            return 400, {'error': str(error)}
        return 200, result

    if action == 'restock':
        ingredient = payload.get('ingredient')
        amount = payload.get('amount')
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return 400, {'error': '"amount" must be a number'}
        if not ingredient or amount <= 0:
            return 400, {'error': '"ingredient" and a positive "amount" are required'}

        if not kitchen.restock(ingredient, amount):
            return 404, {'error': 'Ingredient not found'}
        item = next((row for row in kitchen.get_stock() if row['name'] == ingredient), None)
        return 200, item

    if action == 'set_stock':
        ingredient = payload.get('ingredient')
        amount = payload.get('amount')
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return 400, {'error': '"amount" must be a number'}
        if not ingredient or amount < 0:
            return 400, {'error': '"ingredient" and a non-negative "amount" are required'}

        if not kitchen.set_stock(ingredient, amount):
            return 404, {'error': 'Ingredient not found'}
        item = next((row for row in kitchen.get_stock() if row['name'] == ingredient), None)
        return 200, item

    if action in ('orders', 'kitchen_orders'):
        try:
            orders = kitchen.list_orders(payload.get('limit'))
        except ValueError as error:
            return 400, {'error': str(error)}
        return 200, orders

    if action in ('order', 'kitchen_order'):
        order = kitchen.get_order(payload.get('order_id'))
        if order is None:
            return 404, {'error': 'Kitchen order not found'}
        return 200, order

    return 404, {'error': f'Unknown action: {action}'}


# Publishes a message to the given queue
def publish(channel, queue, message):
    channel.queue_declare(queue=queue, durable=True)
    channel.basic_publish(
        exchange='',
        routing_key=queue,
        body=json.dumps(message, ensure_ascii=False),
        properties=pika.BasicProperties(delivery_mode=2)
    )


# Handles an RPC request and sends the reply to the callback queue
def on_request(ch, method, props, body):
    request = json.loads(body)
    status, response_body = handle_request(request)

    reply = {'status': status, 'body': response_body}
    ch.basic_publish(
        exchange='',
        routing_key=props.reply_to,
        properties=pika.BasicProperties(correlation_id=props.correlation_id),
        body=json.dumps(reply, ensure_ascii=False)
    )
    ch.basic_ack(delivery_tag=method.delivery_tag)


# Handles an order from the kitchen queue
def process_order(ch, method, properties, body):
    order = json.loads(body)
    order_id = order.get('order_id')
    pizza = order.get('pizza')
    quantity = order.get('quantity', 1)
    print(f' [Kitchen] Received order #{order_id}: {order}', flush=True)

    result = kitchen.cook(order_id, pizza, quantity)

    if result['status'] == 'rejected':
        print(f' [Kitchen] Order #{order_id} rejected: {result["reason"]}', flush=True)
        publish(ch, STATUS_QUEUE, {
            'order_id': order_id,
            'status': 'rejected',
            'reason': result['reason'],
        })
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    # Tell the orders service that cooking has started
    publish(ch, STATUS_QUEUE, {'order_id': order_id, 'status': 'cooking'})

    # Simulate cooking time based on the recipe
    time.sleep(result['cook_time'])

    print(f' [Kitchen] Pizza "{result["pizza_name"]}" is ready!', flush=True)
    publish(ch, STATUS_QUEUE, {'order_id': order_id, 'status': 'ready'})

    # Pass the cooked order to delivery
    delivery_message = {
        'order_id': order_id,
        'pizza': pizza,
        'pizza_name': result['pizza_name'],
        'quantity': quantity,
        'address': order.get('address', 'Not specified'),
    }
    publish(ch, DELIVERY_QUEUE, delivery_message)
    print(f' [Kitchen] Order #{order_id} handed over to delivery', flush=True)

    # Acknowledge the message
    ch.basic_ack(delivery_tag=method.delivery_tag)


# Starts the consumers for RPC requests and kitchen orders
def main():
    connection = get_rabbitmq_connection()
    channel = connection.channel()

    # Declare the queues the kitchen works with
    channel.queue_declare(queue=RPC_QUEUE, durable=True)
    channel.queue_declare(queue=KITCHEN_QUEUE, durable=True)
    channel.queue_declare(queue=DELIVERY_QUEUE, durable=True)
    channel.queue_declare(queue=STATUS_QUEUE, durable=True)

    # Do not receive a new message until the previous one is processed
    channel.basic_qos(prefetch_count=1)

    channel.basic_consume(queue=RPC_QUEUE, on_message_callback=on_request)
    channel.basic_consume(
        queue=KITCHEN_QUEUE,
        on_message_callback=process_order
    )

    print(' [Kitchen] Waiting for RPC requests and orders... Press CTRL+C to exit', flush=True)
    channel.start_consuming()


if __name__ == '__main__':
    if os.getenv('SEED_DATA', '0') == '1':
        kitchen.seed()
    main()
