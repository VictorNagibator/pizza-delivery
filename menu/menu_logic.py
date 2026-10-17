import re

import menu_db


# Normalizes a pizza name: "Four Cheese" -> "four_cheese"
def normalize_pizza(pizza):
    return re.sub(r'[\s\-]+', '_', str(pizza).strip().lower())


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
