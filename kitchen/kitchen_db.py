import os
import sqlite3
from datetime import datetime, timezone

# Kitchen database path. Inside Docker it is the /data volume
DEFAULT_DB_PATH = '/data/kitchen.db'

# Recipes: code, name, cooking time in seconds
DEFAULT_RECIPES = [
    ('margherita', 'Margherita', 2),
    ('pepperoni', 'Pepperoni', 3),
    ('four_cheese', 'Four Cheese', 3),
    ('hawaiian', 'Hawaiian', 4),
    ('diablo', 'Diablo', 4),
]

# Ingredients: name, unit, initial stock
DEFAULT_INGREDIENTS = [
    ('dough', 'pcs', 50),
    ('tomato', 'g', 5000),
    ('mozzarella', 'g', 5000),
    ('basil', 'g', 200),
    ('pepperoni', 'g', 2000),
    ('parmesan', 'g', 1000),
    ('gorgonzola', 'g', 1000),
    ('cheddar', 'g', 1000),
    ('ham', 'g', 2000),
    ('pineapple', 'g', 2000),
    ('salami', 'g', 2000),
    ('chili', 'g', 1000),
]

# Recipe composition: pizza code, ingredient, amount per pizza
DEFAULT_RECIPE_INGREDIENTS = [
    ('margherita', 'dough', 1), ('margherita', 'tomato', 100),
    ('margherita', 'mozzarella', 120), ('margherita', 'basil', 5),

    ('pepperoni', 'dough', 1), ('pepperoni', 'tomato', 100),
    ('pepperoni', 'mozzarella', 120), ('pepperoni', 'pepperoni', 80),

    ('four_cheese', 'dough', 1), ('four_cheese', 'mozzarella', 80),
    ('four_cheese', 'parmesan', 60), ('four_cheese', 'gorgonzola', 60),
    ('four_cheese', 'cheddar', 60),

    ('hawaiian', 'dough', 1), ('hawaiian', 'tomato', 100),
    ('hawaiian', 'mozzarella', 120), ('hawaiian', 'ham', 80),
    ('hawaiian', 'pineapple', 70),

    ('diablo', 'dough', 1), ('diablo', 'tomato', 100),
    ('diablo', 'mozzarella', 120), ('diablo', 'salami', 80),
    ('diablo', 'chili', 30),
]

SCHEMA = '''
    CREATE TABLE IF NOT EXISTS recipes (
        code TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        cook_time INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS ingredients (
        name TEXT PRIMARY KEY,
        unit TEXT NOT NULL,
        stock REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS recipe_ingredients (
        recipe_code TEXT NOT NULL,
        ingredient TEXT NOT NULL,
        amount REAL NOT NULL,
        PRIMARY KEY (recipe_code, ingredient),
        FOREIGN KEY (recipe_code) REFERENCES recipes(code),
        FOREIGN KEY (ingredient) REFERENCES ingredients(name)
    );

    CREATE TABLE IF NOT EXISTS kitchen_orders (
        order_id INTEGER PRIMARY KEY,
        pizza TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        status TEXT NOT NULL,
        reason TEXT,
        created_at TEXT NOT NULL,
        finished_at TEXT
    );
'''


# Returns the kitchen database path
def get_database_path():
    return os.getenv('KITCHEN_DB_PATH', DEFAULT_DB_PATH)


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


# Fills the database with default recipes and stock (optional, idempotent)
def seed(path=None):
    with get_connection(path) as connection:
        already_filled = connection.execute('SELECT COUNT(*) AS count FROM recipes').fetchone()['count']
        if already_filled:
            return False
        connection.executemany('INSERT INTO recipes (code, name, cook_time) VALUES (?, ?, ?)', DEFAULT_RECIPES)
        connection.executemany('INSERT INTO ingredients (name, unit, stock) VALUES (?, ?, ?)', DEFAULT_INGREDIENTS)
        connection.executemany(
            'INSERT INTO recipe_ingredients (recipe_code, ingredient, amount) VALUES (?, ?, ?)',
            DEFAULT_RECIPE_INGREDIENTS)
        return True


# Returns a recipe by code or None
def get_recipe(code, path=None):
    with get_connection(path) as connection:
        row = connection.execute('SELECT * FROM recipes WHERE code = ?', (code,)).fetchone()
    return dict(row) if row else None


# Returns all recipes
def get_recipes(path=None):
    with get_connection(path) as connection:
        rows = connection.execute('SELECT * FROM recipes ORDER BY code').fetchall()
    return [dict(row) for row in rows]


# Returns the current ingredient stock
def get_stock(path=None):
    with get_connection(path) as connection:
        rows = connection.execute('SELECT name, unit, stock FROM ingredients ORDER BY name').fetchall()
    return [dict(row) for row in rows]


# Sets an exact ingredient stock value
def set_stock(ingredient, amount, path=None):
    with get_connection(path) as connection:
        cursor = connection.execute('UPDATE ingredients SET stock = ? WHERE name = ?', (amount, ingredient))
        return cursor.rowcount > 0


# Adds the given amount to an ingredient stock
def restock(ingredient, amount, path=None):
    with get_connection(path) as connection:
        cursor = connection.execute('UPDATE ingredients SET stock = stock + ? WHERE name = ?', (amount, ingredient))
        return cursor.rowcount > 0


# Returns the kitchen order journal record
def get_kitchen_order(order_id, path=None):
    with get_connection(path) as connection:
        row = connection.execute('SELECT * FROM kitchen_orders WHERE order_id = ?', (order_id,)).fetchone()
    return dict(row) if row else None
