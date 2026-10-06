import os
import sqlite3
from datetime import datetime, timezone

# Delivery database path. Inside Docker it is the /data volume
DEFAULT_DB_PATH = '/data/delivery.db'

# Default couriers: name and phone
DEFAULT_COURIERS = [
    ('Alex', '+7-900-000-01-01'),
    ('Maria', '+7-900-000-01-02'),
    ('Dmitry', '+7-900-000-01-03'),
    ('Olga', '+7-900-000-01-04'),
]

SCHEMA = '''
    CREATE TABLE IF NOT EXISTS couriers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        phone TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'free',
        deliveries_count INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS deliveries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        courier_id INTEGER,
        address TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        delivered_at TEXT,
        FOREIGN KEY (courier_id) REFERENCES couriers(id)
    );
'''


# Returns the delivery database path
def get_database_path():
    return os.getenv('DELIVERY_DB_PATH', DEFAULT_DB_PATH)


# Opens a database connection
def get_connection(path=None):
    path = path or get_database_path()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    return connection


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# Creates the schema (tables only, no data)
def init_db(path=None):
    with get_connection(path) as connection:
        connection.executescript(SCHEMA)


# Adds default couriers (optional, idempotent)
def seed(path=None):
    with get_connection(path) as connection:
        already_filled = connection.execute('SELECT COUNT(*) AS count FROM couriers').fetchone()['count']
        if already_filled:
            return False
        connection.executemany(
            'INSERT INTO couriers (name, phone) VALUES (?, ?)', DEFAULT_COURIERS)
        return True


# Returns all couriers
def list_couriers(path=None):
    with get_connection(path) as connection:
        rows = connection.execute(
            'SELECT id, name, phone, status, deliveries_count FROM couriers ORDER BY id').fetchall()
    return [dict(row) for row in rows]


# Returns a courier by id or None
def get_courier(courier_id, path=None):
    with get_connection(path) as connection:
        row = connection.execute('SELECT * FROM couriers WHERE id = ?', (courier_id,)).fetchone()
    return dict(row) if row else None


# Adds a new courier
def register_courier(name, phone, path=None):
    with get_connection(path) as connection:
        cursor = connection.execute('INSERT INTO couriers (name, phone) VALUES (?, ?)', (name, phone))
        return cursor.lastrowid


# Returns a delivery by order id or None
def get_delivery_by_order(order_id, path=None):
    with get_connection(path) as connection:
        row = connection.execute(
            'SELECT d.*, c.name AS courier_name FROM deliveries d '
            'LEFT JOIN couriers c ON c.id = d.courier_id '
            'WHERE d.order_id = ? ORDER BY d.id DESC LIMIT 1', (order_id,)).fetchone()
    return dict(row) if row else None


# Returns all deliveries, newest first
def list_deliveries(path=None):
    with get_connection(path) as connection:
        rows = connection.execute('SELECT * FROM deliveries ORDER BY id DESC').fetchall()
    return [dict(row) for row in rows]
