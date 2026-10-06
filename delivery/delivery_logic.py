import delivery_db


# Dispatcher assigns couriers and tracks their load in its own database
class Dispatcher:
    def __init__(self, db_path=None):
        self.db_path = db_path
        delivery_db.init_db(db_path)

    # Adds default couriers (optional)
    def seed(self):
        return delivery_db.seed(self.db_path)

    # Returns all couriers
    def list_couriers(self):
        return delivery_db.list_couriers(self.db_path)

    # Adds a new courier
    def register_courier(self, name, phone):
        return delivery_db.register_courier(name, phone, self.db_path)

    # Returns a delivery by order id
    def get_delivery(self, order_id):
        return delivery_db.get_delivery_by_order(order_id, self.db_path)

    # Assigns an order to the least loaded free courier.
    # A free courier is chosen by the smallest number of deliveries.
    def assign(self, order_id, address):
        now = delivery_db._now()
        with delivery_db.get_connection(self.db_path) as connection:
            courier = connection.execute('''
                SELECT id, name, phone, deliveries_count
                FROM couriers
                WHERE status = 'free'
                ORDER BY deliveries_count ASC, id ASC
                LIMIT 1
            ''').fetchone()

            if courier is None:
                # No free couriers, so the order is queued
                connection.execute('''
                    INSERT INTO deliveries (order_id, courier_id, address, status, created_at)
                    VALUES (?, NULL, ?, 'queued', ?)
                ''', (order_id, address, now))
                return {'status': 'queued', 'reason': 'All couriers are busy'}

            cursor = connection.execute('''
                INSERT INTO deliveries (order_id, courier_id, address, status, created_at)
                VALUES (?, ?, ?, 'delivering', ?)
            ''', (order_id, courier['id'], address, now))

            connection.execute('''
                UPDATE couriers
                SET status = 'busy', deliveries_count = deliveries_count + 1
                WHERE id = ?
            ''', (courier['id'],))

            return {
                'status': 'assigned',
                'delivery_id': cursor.lastrowid,
                'order_id': order_id,
                'address': address,
                'courier_id': courier['id'],
                'courier': courier['name'],
                'phone': courier['phone'],
            }

    # Completes a delivery: closes the order and frees the courier
    def complete(self, order_id):
        now = delivery_db._now()
        with delivery_db.get_connection(self.db_path) as connection:
            delivery = connection.execute('''
                SELECT * FROM deliveries
                WHERE order_id = ? AND status = 'delivering'
                ORDER BY id DESC LIMIT 1
            ''', (order_id,)).fetchone()

            if delivery is None:
                return False

            connection.execute('''
                UPDATE deliveries SET status = 'delivered', delivered_at = ? WHERE id = ?
            ''', (now, delivery['id']))

            if delivery['courier_id'] is not None:
                connection.execute('''
                    UPDATE couriers SET status = 'free' WHERE id = ?
                ''', (delivery['courier_id'],))

            return True

    # Hands a queued order to a courier as soon as one becomes free
    def dispatch_queued(self):
        now = delivery_db._now()
        with delivery_db.get_connection(self.db_path) as connection:
            waiting = connection.execute('''
                SELECT * FROM deliveries WHERE status = 'queued' ORDER BY id LIMIT 1
            ''').fetchone()
            if waiting is None:
                return None

            courier = connection.execute('''
                SELECT id, name, phone FROM couriers
                WHERE status = 'free'
                ORDER BY deliveries_count ASC, id ASC
                LIMIT 1
            ''').fetchone()
            if courier is None:
                return None

            connection.execute('''
                UPDATE deliveries SET courier_id = ?, status = 'delivering', created_at = ?
                WHERE id = ?
            ''', (courier['id'], now, waiting['id']))

            connection.execute('''
                UPDATE couriers
                SET status = 'busy', deliveries_count = deliveries_count + 1
                WHERE id = ?
            ''', (courier['id'],))

            return {
                'status': 'assigned',
                'delivery_id': waiting['id'],
                'order_id': waiting['order_id'],
                'address': waiting['address'],
                'courier_id': courier['id'],
                'courier': courier['name'],
                'phone': courier['phone'],
            }
