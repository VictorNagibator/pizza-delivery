import json
import time
import uuid
import pika


# Synchronous RPC client over RabbitMQ: request/reply with a correlation id.
# Used by the gateway to call any service by its queue name.
class RpcClient:
    def __init__(self, host, timeout=5):
        self.host = host
        self.timeout = timeout

    # Opens a new connection (one per call keeps the Flask worker threads safe)
    def _connection(self):
        credentials = pika.PlainCredentials('guest', 'guest')
        parameters = pika.ConnectionParameters(
            host=self.host,
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=300
        )
        return pika.BlockingConnection(parameters)

    # Sends a request to the given queue and waits for the reply
    def call(self, queue, request):
        connection = self._connection()
        try:
            channel = connection.channel()
            callback_queue = channel.queue_declare(queue='', exclusive=True).method.queue
            correlation_id = str(uuid.uuid4())
            state = {'response': None, 'correlation_id': correlation_id}

            def on_response(ch, method, props, body):
                if props.correlation_id == state['correlation_id']:
                    state['response'] = body

            channel.basic_consume(
                queue=callback_queue, on_message_callback=on_response, auto_ack=True)
            channel.basic_publish(
                exchange='',
                routing_key=queue,
                properties=pika.BasicProperties(
                    reply_to=callback_queue, correlation_id=correlation_id),
                body=json.dumps(request, ensure_ascii=False)
            )

            deadline = time.monotonic() + self.timeout
            while state['response'] is None:
                connection.process_data_events(time_limit=0.1)
                if time.monotonic() > deadline:
                    raise TimeoutError(f'No response from "{queue}" within {self.timeout}s')

            return json.loads(state['response'])
        finally:
            connection.close()
