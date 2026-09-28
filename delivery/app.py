import os
import json
import time
import pika

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')

# Обрабатывает заказ из очереди доставки
def process_delivery(ch, method, properties, body):
    delivery_order = json.loads(body)
    print(f" [Доставка] Получен заказ на доставку: {delivery_order}", flush=True)
    
    # Имитация поиска курьера
    time.sleep(2)
    
    print(f" [Доставка] Курьер назначен! Пицца '{delivery_order['pizza']}' "
          f"будет доставлена по адресу: {delivery_order.get('address', 'Не указан')}", flush=True)
    
    # Подтверждаем обработку сообщения
    ch.basic_ack(delivery_tag=method.delivery_tag)

# Запускает потребителя для очереди delivery_orders
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
    
    channel.queue_declare(queue='delivery_orders', durable=True)
    channel.basic_qos(prefetch_count=1)
    
    channel.basic_consume(
        queue='delivery_orders',
        on_message_callback=process_delivery
    )
    
    print(' [Доставка] Ожидание заказов на доставку... Для выхода нажмите CTRL+C', flush=True)
    channel.start_consuming()

if __name__ == '__main__':
    main()