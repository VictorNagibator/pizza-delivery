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

    # Returns the latest status event of an order or None
    def get_latest_status(self, order_id):
        try:
            order_id = int(order_id)
        except (TypeError, ValueError):
            raise ValueError('"order_id" must be an integer')

        return history_db.get_latest_status(order_id, self.db_path)

    # Returns recent events with optional status filter and pagination
    def list_events(self, limit=50, offset=0, status=None):
        try:
            limit = int(limit if limit not in (None, '') else 50)
            offset = int(offset if offset not in (None, '') else 0)
        except (TypeError, ValueError):
            raise ValueError('"limit" and "offset" must be integers')

        if limit < 1 or limit > 200:
            raise ValueError('"limit" must be between 1 and 200')
        if offset < 0:
            raise ValueError('"offset" must not be negative')

        status = str(status).strip().lower() if status not in (None, '') else None
        return history_db.list_events(limit, offset, status, self.db_path)

    # Returns aggregate statistics for the status log
    def get_stats(self):
        return history_db.get_stats(self.db_path)
