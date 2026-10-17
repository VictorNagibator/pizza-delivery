# AsyncAPI contract

`asyncapi.yaml` is the AsyncAPI 3.0 contract for the pizza delivery
microservices. It describes both directions of the system:

* five synchronous RPC queues (`menu_rpc`, `orders_rpc`, `history_rpc`,
  `kitchen_rpc`, `delivery_rpc`) with request/reply operations;
* four asynchronous queues (`kitchen_orders`, `delivery_orders`,
  `order_status`, `order_history`) with send/receive operations;
* messages, payload schemas, `x-services`, action-level payload descriptions
  (`x-rpc-actions`) and the HTTP routes exposed by the Gateway
  (`x-http-routes`).

The contract contains 14 channels and 18 operations.

## Validate

```bash
npx --yes @asyncapi/cli@6 validate contracts/asyncapi.yaml
```

The contract was also parsed by `@asyncapi/parser`:

```text
document: Pizza Delivery Microservices 1.0.0
channels: 14
operations: 18
errors: 0
```

The parser only recommends moving from AsyncAPI 3.0.0 to 3.1.0. The project keeps
3.0.0 because the archived Node.js generator template used below requires it.

## Generate a client

The official `@asyncapi/nodejs-template` supports AMQP and is the closest
ready-made template to the RabbitMQ stack of this project. It requires AsyncAPI
Generator older than 2.0.0, so the generator is installed locally together with
the template:

```bash
mkdir -p tools/asyncapi
cd tools/asyncapi
npm init -y
npm install --no-audit --no-fund --legacy-peer-deps \
  @asyncapi/generator@1.17.25 \
  @asyncapi/nodejs-template@3.0.4 \
  mkdirp

node node_modules/@asyncapi/generator/cli.js \
  ../../contracts/asyncapi.yaml \
  node_modules/@asyncapi/nodejs-template \
  -o ../../generated/pizza-nodejs \
  -p server=rabbitmq
```

The generated application is a Node.js library based on Hermes. It is not part of
the Python service images; it is a separate generated client and is kept out of
Git.

### Generated publish demo

The generated client publishes through the `amq.topic` exchange (Hermes'
default). The `order_history` queue is bound to that exchange by the History
service itself, in `history/app.py`:

```python
def declare_topology(channel):
    channel.exchange_declare(
        exchange='amq.topic', exchange_type='topic', durable=True)
    channel.queue_declare(queue='order_history', durable=True)
    channel.queue_bind(
        queue='order_history',
        exchange='amq.topic',
        routing_key='order_history',
    )
```

The queue keeps its normal default-exchange binding as well, so the Python
services continue to publish to it by queue name. No separate broker setup script
is needed: the consumer owns its queue and declares the binding on startup.

Point the generated app at the local broker in `config/common.yml`:

```yaml
default:
  broker:
    amqp:
      username: guest
      password: guest
      host: localhost
      port: 5672
      topics: []
      subscribe: false
      queue: generated_demo_events
```

Then use the generated client as a library:

```js
const { client } = require('./');
client.init();

setTimeout(() => {
  client.app.send(
    {
      order_id: 888888,
      status: 'generated',
      courier: null,
      reason: 'AsyncAPI Generator demo',
    },
    {},
    'order_history'
  );
}, 2000);
```

The event is consumed by the History service and is visible through the public
API:

```bash
curl http://localhost:5000/orders/888888/history
```

```json
[
  {
    "courier": null,
    "created_at": "2026-10-17T10:28:26+00:00",
    "reason": "AsyncAPI Generator demo (code-declared binding)",
    "status": "generated"
  }
]
```

History deduplicates events by `event_id`, which defaults to
`order_id:status`. If you run the demo again with the same `order_id` and
`status`, the new message is delivered to History but ignored as a duplicate;
the stored event keeps the first payload. Use a new `order_id`/`status`, or
delete the stored event, to see a new reason.

The generated template leaves a few stray commas in `src/api/index.js` when a
channel has two operations (a known limitation of the archived template). Remove
the lines that contain only a comma before starting the app:

```bash
python3 - <<'PY'
from pathlib import Path
path = Path('generated/pizza-nodejs/src/api/index.js')
path.write_text(path.read_text().replace(',\n  ,\n', ',\n'))
PY
```
