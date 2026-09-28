# Pizza Delivery Microservices

A simple microservices project using RabbitMQ for asynchronous communication.

## How it works

Client → Gateway → [kitchen_orders] → Kitchen → [delivery_orders] → Delivery

1. Gateway receives an HTTP order and sends it to the kitchen_orders queue.
2. Kitchen takes the order, "cooks" the pizza, and sends it to the delivery_orders queue.
3. Delivery takes the order and "assigns" a courier.

## Stack

* Python 3.12 + Flask
* Pika (RabbitMQ client)
* RabbitMQ 4.0
* Docker Compose

## Structure

```text
pizza-delivery/
├── docker-compose.yml
├── gateway/
├── kitchen/
└── delivery/
```

Each service has `app.py`, `Dockerfile`, and `requirements.txt`.

## Run

```bash
docker-compose up --build
```

Services:

* Gateway: http://localhost:5000
* RabbitMQ UI: http://localhost:15672

## Test

```bash
curl -X POST http://localhost:5000/order -H "Content-Type: application/json" -d '{"pizza": "Pepperoni", "address": "123 Main Street"}'
```

Check the logs:

```bash
docker-compose logs -f
```
