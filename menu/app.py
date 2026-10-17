import os
import json
import pika

from menu_logic import MenuService, PizzaAlreadyExists

# RabbitMQ address comes from the environment
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')
RPC_QUEUE = 'menu_rpc'

# Menu catalog backed by its own database
service = MenuService()


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

    if action == 'menu':
        return 200, service.get_menu()

    if action == 'get_pizza':
        item = service.get_pizza(payload.get('pizza', payload.get('code')))
        if item is None:
            return 404, {'error': 'Pizza not found'}
        return 200, item

    if action == 'search_menu':
        try:
            items = service.search_menu(
                payload.get('q'),
                payload.get('min_price'),
                payload.get('max_price'))
        except ValueError as error:
            return 400, {'error': str(error)}
        return 200, items

    if action == 'add_pizza':
        try:
            item = service.add_pizza(payload)
        except PizzaAlreadyExists as error:
            return 409, {'error': str(error)}
        except ValueError as error:
            return 400, {'error': str(error)}
        return 201, item

    if action == 'update_price':
        try:
            item = service.update_price(payload.get('code'), payload.get('price'))
        except KeyError:
            return 404, {'error': 'Pizza not found'}
        except ValueError as error:
            return 400, {'error': str(error)}
        return 200, item

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


# Starts the RPC consumer for menu requests
def main():
    connection = get_rabbitmq_connection()
    channel = connection.channel()

    channel.queue_declare(queue=RPC_QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=RPC_QUEUE, on_message_callback=on_request)

    print(' [Menu] Waiting for RPC requests...', flush=True)
    channel.start_consuming()


if __name__ == '__main__':
    if os.getenv('SEED_DATA', '0') == '1':
        service.seed()
    main()
