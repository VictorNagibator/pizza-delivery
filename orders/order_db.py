import os
import sqlite3
from datetime import datetime, timezone

# Orders database path. Inside Docker it is the /data volume
DEFAULT_DATABASE_PATH = '/data/orders.db'

SCHEMA = '''
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pizza TEXT NOT NULL,
        pizza_name TEXT NOT NULL,
        address TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        total_price REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'new',
        courier TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
'''


# Returns the database path (the environment variable is read on every call)
def get_database_path():
    return os.getenv('ORDERS_DB_PATH', DEFAULT_DATABASE_PATH)


# Opens a database connection
def get_connection(path=None):
    path = path or get_database_path()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# Creates the schema (table only, no data)
def init_db(path=None):
    with get_connection(path) as connection:
        connection.executescript(SCHEMA)


# Saves a new order and returns its id
def create_order(order, path=None):
    now = _now()
    with get_connection(path) as connection:
        cursor = connection.execute('''
            INSERT INTO orders (pizza, pizza_name, address, quantity, total_price, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'new', ?, ?)
        ''', (order['pizza'], order['pizza_name'], order['address'], order['quantity'],
              order['total_price'], now, now))
        return cursor.lastrowid


# Returns an order by id or None
def get_order(order_id, path=None):
    with get_connection(path) as connection:
        row = connection.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
    return dict(row) if row else None


# Returns all orders, newest first. Optionally filters by status.
def list_orders(path=None, status=None):
    with get_connection(path) as connection:
        if status is None:
            rows = connection.execute('SELECT * FROM orders ORDER BY id DESC').fetchall()
        else:
            rows = connection.execute(
                'SELECT * FROM orders WHERE status = ? ORDER BY id DESC', (status,)).fetchall()
    return [dict(row) for row in rows]


# Returns aggregate information about all orders
def get_order_stats(path=None):
    with get_connection(path) as connection:
        rows = connection.execute('''
            SELECT status, COUNT(*) AS count, COALESCE(SUM(total_price), 0) AS revenue
            FROM orders
            GROUP BY status
            ORDER BY status
        ''').fetchall()
        total = connection.execute('''
            SELECT COUNT(*) AS count, COALESCE(SUM(total_price), 0) AS revenue
            FROM orders
        ''').fetchone()

    by_status = {
        row['status']: {'count': row['count'], 'revenue': row['revenue']}
        for row in rows
    }
    total_orders = total['count']
    total_revenue = total['revenue']
    return {
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'average_order_value': round(total_revenue / total_orders, 2) if total_orders else 0,
        'by_status': by_status,
    }


# Updates the current order status and courier
def update_status(order_id, status, courier=None, path=None):
    now = _now()
    with get_connection(path) as connection:
        if courier is None:
            cursor = connection.execute(
                'UPDATE orders SET status = ?, updated_at = ? WHERE id = ?',
                (status, now, order_id))
        else:
            cursor = connection.execute(
                'UPDATE orders SET status = ?, courier = ?, updated_at = ? WHERE id = ?',
                (status, courier, now, order_id))
        return cursor.rowcount > 0
