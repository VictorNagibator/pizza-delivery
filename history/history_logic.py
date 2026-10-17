import history_db


# Status history service. It owns the append-only order status log.
class HistoryService:
    def __init__(self, db_path=None):
        self.db_path = db_path
        history_db.init_db(db_path)

    # Stores a status event. The event is idempotent by (order_id, status):
    # a redelivered AMQP message does not create a duplicate record.
    def record(self, event):
        if not event or 'order_id' not in event or 'status' not in event:
            raise ValueError('Event must contain "order_id" and "status"')

        try:
            order_id = int(event['order_id'])
        except (TypeError, ValueError):
            raise ValueError('"order_id" must be an integer')

        status = str(event['status']).strip()
        if not status:
            raise ValueError('"status" must not be empty')

        return history_db.append_event({
            'event_id': event.get('event_id') or f'{order_id}:{status}',
            'order_id': order_id,
            'status': status,
            'courier': event.get('courier'),
            'reason': event.get('reason'),
            'created_at': event.get('created_at'),
        }, self.db_path)

    # Returns the history of an order or None when the order has no events
    def get_history(self, order_id):
        try:
            order_id = int(order_id)
        except (TypeError, ValueError):
            raise ValueError('"order_id" must be an integer')

        entries = history_db.get_history(order_id, self.db_path)
        return entries or None
