import os
import json
import pika

from history_logic import HistoryService

# RabbitMQ address comes from the environment
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')
RPC_QUEUE = 'history_rpc'
EVENTS_QUEUE = 'order_history'

# Status history backed by its own database
history = HistoryService()


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


# Handles a read request and returns an HTTP-like (status, body) pair.
# This is pure logic and can be tested without a broker.
def handle_request(request):
    action = request.get('action')
    payload = request.get('payload') or {}

    if action == 'get_history':
        try:
            entries = history.get_history(payload.get('order_id'))
        except ValueError as error:
            return 400, {'error': str(error)}
        if entries is None:
            return 404, {'error': 'Order not found'}
        return 200, entries

    return 404, {'error': f'Unknown action: {action}'}


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


# Handles a status event from the orders service and appends it to the log
def on_event(ch, method, properties, body):
    try:
        event = json.loads(body)
        inserted = history.record(event)
        if inserted:
            print(f' [History] Order #{event["order_id"]} -> {event["status"]}', flush=True)
        else:
            print(f' [History] Duplicate event ignored: {event}', flush=True)
    except Exception as error:
        print(f' [History] Failed to store event: {error}', flush=True)
    finally:
        ch.basic_ack(delivery_tag=method.delivery_tag)


# Starts the RPC consumer and the event consumer
def main():
    connection = get_rabbitmq_connection()
    channel = connection.channel()

    channel.queue_declare(queue=RPC_QUEUE, durable=True)
    channel.queue_declare(queue=EVENTS_QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)

    channel.basic_consume(queue=RPC_QUEUE, on_message_callback=on_request)
    channel.basic_consume(queue=EVENTS_QUEUE, on_message_callback=on_event)

    print(' [History] Waiting for RPC requests and status events...', flush=True)
    channel.start_consuming()


if __name__ == '__main__':
    main()
