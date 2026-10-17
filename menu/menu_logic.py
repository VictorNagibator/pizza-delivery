import re

import menu_db


# Raised when a pizza with the same code already exists
class PizzaAlreadyExists(Exception):
    pass


# Normalizes a pizza name: "Four Cheese" -> "four_cheese"
def normalize_pizza(pizza):
    return re.sub(r'[\s\-]+', '_', str(pizza).strip().lower())


# Validates and converts a price
def _validate_price(price):
    try:
        value = float(price)
    except (TypeError, ValueError):
        raise ValueError('"price" must be a number')
    if value <= 0:
        raise ValueError('"price" must be greater than 0')
    return round(value, 2)


# Validates an optional price boundary
def _optional_price(value, field):
    if value is None or value == '':
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'"{field}" must be a number')
    if number < 0:
        raise ValueError(f'"{field}" must not be negative')
    return number


# Validates a pizza code
def _validate_code(code):
    if code is None or not str(code).strip():
        raise ValueError('"code" must not be empty')
    return normalize_pizza(code)


# Validates a pizza name
def _validate_name(name):
    if name is None or not str(name).strip():
        raise ValueError('"name" must not be empty')
    return str(name).strip()


# Menu catalog backed by the menu database.
# The service owns product data only; pricing rules live in the orders service.
class MenuService:
    def __init__(self, db_path=None):
        self.db_path = db_path
        menu_db.init_db(db_path)

    # Fills the menu with default data (optional)
    def seed(self):
        return menu_db.seed(self.db_path)

    # Returns the whole menu
    def get_menu(self):
        return menu_db.get_menu(self.db_path)

    # Returns one pizza by code or name, or None if it is not on the menu
    def get_pizza(self, pizza):
        if pizza is None:
            return None
        return menu_db.get_pizza(normalize_pizza(pizza), self.db_path)

    # Searches the menu by text and optional price range
    def search_menu(self, query=None, min_price=None, max_price=None):
        text = str(query).strip() if query not in (None, '') else None
        minimum = _optional_price(min_price, 'min_price')
        maximum = _optional_price(max_price, 'max_price')
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError('"min_price" must not be greater than "max_price"')
        return menu_db.search_menu(text, minimum, maximum, self.db_path)

    # Adds a new pizza to the menu
    def add_pizza(self, data):
        if not data:
            raise ValueError('Request body must contain "code", "name" and "price"')

        code = _validate_code(data.get('code'))
        name = _validate_name(data.get('name'))
        price = _validate_price(data.get('price'))

        if not menu_db.add_pizza(code, name, price, self.db_path):
            raise PizzaAlreadyExists(f'Pizza "{code}" already exists')
        return menu_db.get_pizza(code, self.db_path)

    # Changes the price of an existing pizza
    def update_price(self, code, price):
        code = _validate_code(code)
        price = _validate_price(price)

        if not menu_db.update_price(code, price, self.db_path):
            raise KeyError(code)
        return menu_db.get_pizza(code, self.db_path)
