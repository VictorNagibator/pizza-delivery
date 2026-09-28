import os
import json
import time
import pika

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')

# Обрабатывает заказ из очереди кухни
def process_order(ch, method, properties, body):
    order = json.loads(body)
    print(f" [Кухня] Получен заказ: {order}", flush=True)
    
    # Имитация готовки пиццы
    time.sleep(3)
    
    print(f" [Кухня] Пицца '{order['pizza']}' готова!", flush=True)
    
    # Публикуем сообщение в очередь доставки
    delivery_message = json.dumps({
        'pizza': order['pizza'],
        'address': order.get('address', 'Не указан')
    }, ensure_ascii=False)
    
    ch.basic_publish(
        exchange='',
        routing_key='delivery_orders',
        body=delivery_message,
        properties=pika.BasicProperties(delivery_mode=2)
    )
    print(f" [Кухня] Сообщение отправлено в доставку: {delivery_message}", flush=True)
    
    # Подтверждаем обработку сообщения
    ch.basic_ack(delivery_tag=method.delivery_tag)

# Запускает потребителя для очереди kitchen_orders
def main():
    credentials = pika.PlainCredentials('guest', 'guest')
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300
    )
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    
    # Объявляем очередь
    channel.queue_declare(queue='kitchen_orders', durable=True)
    
    # Не даём новое сообщение, пока не обработано предыдущее
    channel.basic_qos(prefetch_count=1)
    
    channel.basic_consume(
        queue='kitchen_orders',
        on_message_callback=process_order
    )
    
    print(' [Кухня] Ожидание заказов... Для выхода нажмите CTRL+C', flush=True)
    channel.start_consuming()

if __name__ == '__main__':
    main()