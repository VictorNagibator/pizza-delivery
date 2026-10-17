import os
import json
import pika

from menu_client import MenuClient, MenuUnavailable
from order_logic import OrderService

# RabbitMQ address comes from the environment
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')
RPC_QUEUE = 'orders_rpc'
STATUS_QUEUE = 'order_status'
KITCHEN_QUEUE = 'kitchen_orders'
HISTORY_QUEUE = 'order_history'

# Orders service backed by its own database and a menu RPC client
service = OrderService(menu=MenuClient(RABBITMQ_HOST))


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

    if action == 'create_order':
        try:
            order = service.create_order(payload)
        except ValueError as error:
            return 400, {'error': str(error)}
        except MenuUnavailable as error:
            return 503, {'error': f'Menu service is unavailable: {error}'}
        return 202, order

    if action == 'list_orders':
        return 200, service.list_orders()

    if action == 'get_order':
        order = service.get_order(payload.get('order_id'))
        if order is None:
            return 404, {'error': 'Order not found'}
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


# Sends one status event to the history service
def publish_history(channel, order_id, status, courier=None, reason=None):
    publish(channel, HISTORY_QUEUE, {
        'order_id': order_id,
        'status': status,
        'courier': courier,
        'reason': reason,
    })


# Handles an RPC request and sends the reply to the callback queue
def on_request(ch, method, props, body):
    request = json.loads(body)
    status, response_body = handle_request(request)

    # A successfully created order is recorded in history and sent to the kitchen
    if request.get('action') == 'create_order' and status == 202:
        order_id = response_body['order_id']
        try:
            publish_history(ch, order_id, 'new')
            publish(ch, KITCHEN_QUEUE, response_body)
        except Exception as error:
            service.update_status(order_id, 'publish_failed')
            try:
                publish_history(ch, order_id, 'publish_failed')
            except Exception:
                pass
            status = 500
            response_body = {'error': str(error), 'order_id': order_id}

    reply = {'status': status, 'body': response_body}
    ch.basic_publish(
        exchange='',
        routing_key=props.reply_to,
        properties=pika.BasicProperties(correlation_id=props.correlation_id),
        body=json.dumps(reply, ensure_ascii=False)
    )
    ch.basic_ack(delivery_tag=method.delivery_tag)


# Handles a status update from kitchen or delivery and forwards it to history
def on_status(ch, method, properties, body):
    try:
        update = json.loads(body)
        order_id = update['order_id']
        status = update['status']
        updated = service.update_status(order_id, status, update.get('courier'))
    except Exception as error:
        print(f' [Orders] Failed to process status event: {error}', flush=True)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    if not updated:
        print(f' [Orders] Order #{order_id} not found', flush=True)
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    try:
        publish_history(ch, order_id, status, update.get('courier'), update.get('reason'))
        print(f' [Orders] Order #{order_id} -> {status}', flush=True)
    except Exception as error:
        # The order state is already updated; only the audit event was lost.
        print(f' [Orders] Order #{order_id} updated, history publish failed: {error}', flush=True)
    finally:
        ch.basic_ack(delivery_tag=method.delivery_tag)


# Starts the consumers for RPC requests and status updates
def main():
    connection = get_rabbitmq_connection()
    channel = connection.channel()

    channel.queue_declare(queue=RPC_QUEUE, durable=True)
    channel.queue_declare(queue=STATUS_QUEUE, durable=True)
    channel.queue_declare(queue=KITCHEN_QUEUE, durable=True)
    channel.queue_declare(queue=HISTORY_QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)

    channel.basic_consume(queue=RPC_QUEUE, on_message_callback=on_request)
    channel.basic_consume(queue=STATUS_QUEUE, on_message_callback=on_status)

    print(' [Orders] Waiting for RPC requests and status updates...', flush=True)
    channel.start_consuming()


if __name__ == '__main__':
    main()
