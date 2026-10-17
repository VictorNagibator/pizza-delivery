import re

import kitchen_db


# Normalizes a pizza name: "Four Cheese" -> "four_cheese"
def normalize_pizza(pizza):
    return re.sub(r'[\s\-]+', '_', str(pizza).strip().lower())


# Writes the order processing result to the kitchen journal
def _record_result(connection, order_id, pizza, quantity, status, reason, created_at):
    connection.execute('''
        INSERT INTO kitchen_orders (order_id, pizza, quantity, status, reason, created_at, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(order_id) DO UPDATE SET
            pizza = excluded.pizza,
            quantity = excluded.quantity,
            status = excluded.status,
            reason = excluded.reason,
            finished_at = excluded.finished_at
    ''', (order_id, pizza, quantity, status, reason, created_at, created_at))


# The kitchen keeps recipes and ingredient stock in its own database
class Kitchen:
    def __init__(self, db_path=None):
        self.db_path = db_path
        kitchen_db.init_db(db_path)

    # Fills the database with default recipes and stock (optional)
    def seed(self):
        return kitchen_db.seed(self.db_path)

    # Returns all recipes
    def get_recipes(self):
        return kitchen_db.get_recipes(self.db_path)

    # Returns a recipe by pizza code
    def get_recipe(self, code):
        return kitchen_db.get_recipe(code, self.db_path)

    # Returns the current stock
    def get_stock(self):
        return kitchen_db.get_stock(self.db_path)

    # Checks whether the kitchen can cook the given pizza right now
    def check_availability(self, pizza, quantity=1):
        code = normalize_pizza(pizza)

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            raise ValueError('"quantity" must be an integer')
        if quantity < 1:
            raise ValueError('Quantity must be at least 1')

        with kitchen_db.get_connection(self.db_path) as connection:
            recipe = connection.execute(
                'SELECT code, name, cook_time FROM recipes WHERE code = ?', (code,)).fetchone()
            if recipe is None:
                raise KeyError(code)

            required = connection.execute('''
                SELECT ri.ingredient, ri.amount, i.unit, i.stock
                FROM recipe_ingredients ri
                JOIN ingredients i ON i.name = ri.ingredient
                WHERE ri.recipe_code = ?
                ORDER BY ri.ingredient
            ''', (code,)).fetchall()

        ingredients = []
        missing = []
        for row in required:
            need = row['amount'] * quantity
            ingredients.append({
                'ingredient': row['ingredient'],
                'unit': row['unit'],
                'per_pizza': row['amount'],
                'required': need,
                'stock': row['stock'],
            })
            if row['stock'] < need:
                missing.append(row['ingredient'])

        return {
            'pizza': code,
            'pizza_name': recipe['name'],
            'quantity': quantity,
            'available': not missing,
            'missing': missing,
            'ingredients': ingredients,
        }

    # Adds stock to an ingredient
    def restock(self, ingredient, amount):
        return kitchen_db.restock(ingredient, amount, self.db_path)

    # Sets an exact ingredient stock value (for example, during inventory)
    def set_stock(self, ingredient, amount):
        return kitchen_db.set_stock(ingredient, amount, self.db_path)

    # Returns the kitchen journal record for an order
    def get_order(self, order_id):
        return kitchen_db.get_kitchen_order(order_id, self.db_path)

    # Returns recent kitchen journal records
    def list_orders(self, limit=50):
        try:
            limit = int(limit if limit not in (None, '') else 50)
        except (TypeError, ValueError):
            raise ValueError('"limit" must be an integer')
        if limit < 1 or limit > 200:
            raise ValueError('"limit" must be between 1 and 200')
        return kitchen_db.list_kitchen_orders(limit, self.db_path)

    # Cooks a pizza: checks the recipe, consumes ingredients, writes the journal
    def cook(self, order_id, pizza, quantity=1):
        now = kitchen_db._now()
        with kitchen_db.get_connection(self.db_path) as connection:
            if quantity < 1:
                reason = 'Quantity must be at least 1'
                _record_result(connection, order_id, pizza, quantity, 'rejected', reason, now)
                return {'status': 'rejected', 'reason': reason}

            recipe = connection.execute(
                'SELECT code, name, cook_time FROM recipes WHERE code = ?', (pizza,)).fetchone()
            if recipe is None:
                reason = f'Pizza "{pizza}" is not in the kitchen menu'
                _record_result(connection, order_id, pizza, quantity, 'rejected', reason, now)
                return {'status': 'rejected', 'reason': reason}

            required = connection.execute(
                'SELECT ingredient, amount FROM recipe_ingredients WHERE recipe_code = ?',
                (pizza,)).fetchall()
            missing = []
            for row in required:
                need = row['amount'] * quantity
                stock_row = connection.execute(
                    'SELECT stock FROM ingredients WHERE name = ?', (row['ingredient'],)).fetchone()
                available = stock_row['stock'] if stock_row else 0
                if available < need:
                    missing.append(row['ingredient'])

            if missing:
                reason = 'Out of ingredients: ' + ', '.join(sorted(missing))
                _record_result(connection, order_id, pizza, quantity, 'rejected', reason, now)
                return {'status': 'rejected', 'reason': reason}

            # Consume ingredients from the stock
            for row in required:
                connection.execute(
                    'UPDATE ingredients SET stock = stock - ? WHERE name = ?',
                    (row['amount'] * quantity, row['ingredient']))

            _record_result(connection, order_id, pizza, quantity, 'ready', None, now)
            return {
                'status': 'ready',
                'pizza': recipe['code'],
                'pizza_name': recipe['name'],
                'quantity': quantity,
                'cook_time': recipe['cook_time'],
            }
