import os
import json
import pika
from flask import Flask, request, jsonify

app = Flask(__name__)

# Получаем адрес RabbitMQ из переменных окружения 
# (по умолчанию 'rabbitmq' — имя сервиса в docker-compose)
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')

# Создаёт подключение к RabbitMQ
def get_rabbitmq_connection():
    credentials = pika.PlainCredentials('guest', 'guest')
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300
    )
    return pika.BlockingConnection(parameters)

# Принимает заказ и отправляет его на кухню
@app.route('/order', methods=['POST'])
def create_order():
    order_data = request.get_json()
    if not order_data or 'pizza' not in order_data:
        return jsonify({'error': 'Invalid order. Provide "pizza" field.'}), 400

    try:
        connection = get_rabbitmq_connection()
        channel = connection.channel()
        
        # Объявляем очередь (если её нет, она создастся)
        channel.queue_declare(queue='kitchen_orders', durable=True)
        
        # Публикуем сообщение в очередь
        message = json.dumps(order_data)
        channel.basic_publish(
            exchange='',
            routing_key='kitchen_orders',
            body=message,
            properties=pika.BasicProperties(delivery_mode=2)  # Делаем сообщение persistent
        )
        connection.close()
        
        return jsonify({'status': 'Order received', 'order': order_data}), 202
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)