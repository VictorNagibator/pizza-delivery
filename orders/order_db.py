import os
import sqlite3
from datetime import datetime, timezone

# Orders database path. Inside Docker it is the /data volume
DEFAULT_DATABASE_PATH = '/data/orders.db'

# Default pizzeria menu: code, name, price in rubles
DEFAULT_MENU = [
    ('margherita', 'Margherita', 450),
    ('pepperoni', 'Pepperoni', 550),
    ('four_cheese', 'Four Cheese', 650),
    ('hawaiian', 'Hawaiian', 600),
    ('diablo', 'Diablo', 620),
]

SCHEMA = '''
    CREATE TABLE IF NOT EXISTS menu (
        code TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        price REAL NOT NULL
    );

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

    CREATE TABLE IF NOT EXISTS order_status_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        status TEXT NOT NULL,
        courier TEXT,
        created_at TEXT NOT NULL
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


# Creates the schema (tables only, no data)
def init_db(path=None):
    with get_connection(path) as connection:
        connection.executescript(SCHEMA)


# Fills the menu with default data (optional, idempotent)
def seed(path=None):
    with get_connection(path) as connection:
        already_filled = connection.execute('SELECT COUNT(*) AS count FROM menu').fetchone()['count']
        if already_filled:
            return False
        connection.executemany('INSERT INTO menu (code, name, price) VALUES (?, ?, ?)', DEFAULT_MENU)
        return True


# Returns the whole menu as {code: {name, price}}
def get_menu(path=None):
    with get_connection(path) as connection:
        rows = connection.execute('SELECT code, name, price FROM menu ORDER BY code').fetchall()
    return {row['code']: {'name': row['name'], 'price': row['price']} for row in rows}


# Returns a menu item by pizza code or None
def get_pizza(code, path=None):
    with get_connection(path) as connection:
        row = connection.execute('SELECT code, name, price FROM menu WHERE code = ?', (code,)).fetchone()
    return dict(row) if row else None


def _row_to_dict(row):
    return dict(row) if row is not None else None


# Saves a new order, writes the first status to the history and returns its id
def create_order(order, path=None):
    now = _now()
    with get_connection(path) as connection:
        cursor = connection.execute('''
            INSERT INTO orders (pizza, pizza_name, address, quantity, total_price, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'new', ?, ?)
        ''', (order['pizza'], order['pizza_name'], order['address'], order['quantity'],
              order['total_price'], now, now))
        order_id = cursor.lastrowid
        connection.execute('''
            INSERT INTO order_status_history (order_id, status, courier, created_at)
            VALUES (?, 'new', NULL, ?)
        ''', (order_id, now))
        return order_id


# Returns an order by id or None
def get_order(order_id, path=None):
    with get_connection(path) as connection:
        row = connection.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
    return _row_to_dict(row)


# Returns all orders, newest first
def list_orders(path=None):
    with get_connection(path) as connection:
        rows = connection.execute('SELECT * FROM orders ORDER BY id DESC').fetchall()
    return [dict(row) for row in rows]


# Updates the order status and courier, and appends a history record
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

        if cursor.rowcount == 0:
            return False

        connection.execute('''
            INSERT INTO order_status_history (order_id, status, courier, created_at)
            VALUES (?, ?, ?, ?)
        ''', (order_id, status, courier, now))
        return True


# Returns the status history of an order
def get_history(order_id, path=None):
    with get_connection(path) as connection:
        rows = connection.execute('''
            SELECT status, courier, created_at
            FROM order_status_history
            WHERE order_id = ?
            ORDER BY id
        ''', (order_id,)).fetchall()
    return [dict(row) for row in rows]
