import os
import json
import time
import pika

from delivery_logic import Dispatcher

# RabbitMQ address comes from the environment
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')
DELIVERY_QUEUE = 'delivery_orders'
STATUS_QUEUE = 'order_status'

# Dispatcher with couriers and deliveries stored in its own database
dispatcher = Dispatcher()


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


# Handles an order from the delivery queue
def process_delivery(ch, method, properties, body):
    delivery_order = json.loads(body)
    order_id = delivery_order.get('order_id')
    address = delivery_order.get('address', 'Not specified')
    print(f' [Delivery] Received delivery order #{order_id}: {delivery_order}', flush=True)

    assignment = dispatcher.assign(order_id, address)

    if assignment['status'] == 'queued':
        print(f' [Delivery] Order #{order_id} queued: {assignment["reason"]}', flush=True)
        publish(ch, STATUS_QUEUE, {'order_id': order_id, 'status': 'delivery_queued'})
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    courier = assignment['courier']
    publish(ch, STATUS_QUEUE, {'order_id': order_id, 'status': 'delivering', 'courier': courier})
    print(f' [Delivery] Courier {courier} is delivering order #{order_id} to: {address}', flush=True)

    # Simulate the courier trip
    time.sleep(2)

    dispatcher.complete(order_id)
    publish(ch, STATUS_QUEUE, {'order_id': order_id, 'status': 'delivered', 'courier': courier})
    print(f' [Delivery] Order #{order_id} delivered by {courier}', flush=True)

    # A courier became free, so hand over queued orders
    dispatch_waiting(ch)

    # Acknowledge the message
    ch.basic_ack(delivery_tag=method.delivery_tag)


# Hands queued orders to couriers that became free
def dispatch_waiting(ch):
    while True:
        assignment = dispatcher.dispatch_queued()
        if assignment is None:
            return

        order_id = assignment['order_id']
        courier = assignment['courier']
        publish(ch, STATUS_QUEUE, {'order_id': order_id, 'status': 'delivering', 'courier': courier})
        print(f' [Delivery] Courier {courier} is delivering queued order #{order_id}', flush=True)

        time.sleep(2)

        dispatcher.complete(order_id)
        publish(ch, STATUS_QUEUE, {'order_id': order_id, 'status': 'delivered', 'courier': courier})
        print(f' [Delivery] Queued order #{order_id} delivered by {courier}', flush=True)


# Starts the consumer for the delivery queue
def main():
    connection = get_rabbitmq_connection()
    channel = connection.channel()

    channel.queue_declare(queue=DELIVERY_QUEUE, durable=True)
    channel.queue_declare(queue=STATUS_QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)

    channel.basic_consume(
        queue=DELIVERY_QUEUE,
        on_message_callback=process_delivery
    )

    print(' [Delivery] Waiting for delivery orders... Press CTRL+C to exit', flush=True)
    channel.start_consuming()


if __name__ == '__main__':
    if os.getenv('SEED_DATA', '0') == '1':
        dispatcher.seed()
    main()
