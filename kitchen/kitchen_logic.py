import kitchen_db


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

    # Adds stock to an ingredient
    def restock(self, ingredient, amount):
        return kitchen_db.restock(ingredient, amount, self.db_path)

    # Sets an exact ingredient stock value (for example, during inventory)
    def set_stock(self, ingredient, amount):
        return kitchen_db.set_stock(ingredient, amount, self.db_path)

    # Returns the kitchen journal record for an order
    def get_order(self, order_id):
        return kitchen_db.get_kitchen_order(order_id, self.db_path)

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
