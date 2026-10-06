import os
import json
import time
import pika

from kitchen_logic import Kitchen

# RabbitMQ address comes from the environment
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')
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


# Publishes a message to the given queue
def publish(channel, queue, message):
    channel.queue_declare(queue=queue, durable=True)
    channel.basic_publish(
        exchange='',
        routing_key=queue,
        body=json.dumps(message, ensure_ascii=False),
        properties=pika.BasicProperties(delivery_mode=2)
    )


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


# Starts the consumer for the kitchen queue
def main():
    connection = get_rabbitmq_connection()
    channel = connection.channel()

    # Declare the queues the kitchen works with
    channel.queue_declare(queue=KITCHEN_QUEUE, durable=True)
    channel.queue_declare(queue=DELIVERY_QUEUE, durable=True)
    channel.queue_declare(queue=STATUS_QUEUE, durable=True)

    # Do not receive a new message until the previous one is processed
    channel.basic_qos(prefetch_count=1)

    channel.basic_consume(
        queue=KITCHEN_QUEUE,
        on_message_callback=process_order
    )

    print(' [Kitchen] Waiting for orders... Press CTRL+C to exit', flush=True)
    channel.start_consuming()


if __name__ == '__main__':
    if os.getenv('SEED_DATA', '0') == '1':
        kitchen.seed()
    main()
