import os
import sqlite3

# Menu database path. Inside Docker it is the /data volume
DEFAULT_DATABASE_PATH = '/data/menu.db'

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
'''


# Returns the menu database path (the environment variable is read on every call)
def get_database_path():
    return os.getenv('MENU_DB_PATH', DEFAULT_DATABASE_PATH)


# Opens a database connection
def get_connection(path=None):
    path = path or get_database_path()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


# Creates the schema (table only, no data)
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
