import re

import order_db

DELIVERY_PRICE = 100        # Base delivery fee
FREE_DELIVERY_FROM = 1000   # Free delivery from this amount
BULK_DISCOUNT_FROM = 3      # Discount from this quantity of pizzas
BULK_DISCOUNT = 0.1         # Discount size (10%)


# Normalizes a pizza name: "Four Cheese" -> "four_cheese"
def normalize_pizza(pizza):
    return re.sub(r'[\s\-]+', '_', str(pizza).strip().lower())


# Order domain logic backed by the orders database (menu lives in the DB)
class OrderService:
    def __init__(self, db_path=None):
        self.db_path = db_path
        order_db.init_db(db_path)

    # Fills the menu with default data (optional)
    def seed(self):
        return order_db.seed(self.db_path)

    # Returns the whole menu
    def get_menu(self):
        return order_db.get_menu(self.db_path)

    # Calculates the order price
    def calculate_price(self, pizza, quantity):
        code = normalize_pizza(pizza)
        item = order_db.get_pizza(code, self.db_path)
        if item is None:
            raise ValueError(f'Pizza "{pizza}" is not on the menu')
        if quantity < 1:
            raise ValueError('Quantity must be at least 1')

        unit_price = item['price']
        subtotal = unit_price * quantity

        discount = 0
        if quantity >= BULK_DISCOUNT_FROM:
            discount = round(subtotal * BULK_DISCOUNT, 2)

        delivery = 0 if (subtotal - discount) >= FREE_DELIVERY_FROM else DELIVERY_PRICE
        total = round(subtotal - discount + delivery, 2)

        return {
            'pizza': code,
            'pizza_name': item['name'],
            'quantity': quantity,
            'unit_price': unit_price,
            'subtotal': subtotal,
            'discount': discount,
            'delivery_price': delivery,
            'total_price': total,
        }

    # Validates an order from an HTTP request and returns it with a calculated price
    def prepare_order(self, data):
        if not data or 'pizza' not in data:
            raise ValueError('Order must contain a "pizza" field')

        try:
            quantity = int(data.get('quantity', 1))
        except (TypeError, ValueError):
            raise ValueError('"quantity" must be an integer')

        address = str(data.get('address', '')).strip()
        if not address:
            raise ValueError('Order must contain an "address" field')

        order = self.calculate_price(data['pizza'], quantity)
        order['address'] = address
        return order

    # Creates and stores a new order
    def create_order(self, data):
        order = self.prepare_order(data)
        order_id = order_db.create_order(order, self.db_path)
        order['order_id'] = order_id
        return order

    # Returns all orders
    def list_orders(self):
        return order_db.list_orders(self.db_path)

    # Returns one order by id
    def get_order(self, order_id):
        return order_db.get_order(order_id, self.db_path)

    # Returns the status history of an order
    def get_history(self, order_id):
        if order_db.get_order(order_id, self.db_path) is None:
            raise KeyError(order_id)
        return order_db.get_history(order_id, self.db_path)

    # Updates the order status and, optionally, the courier
    def update_status(self, order_id, status, courier=None):
        return order_db.update_status(order_id, status, courier, self.db_path)
