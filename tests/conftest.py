import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Project root and service directories
ROOT = Path(__file__).resolve().parent.parent
GATEWAY_DIR = ROOT / 'gateway'
ORDERS_DIR = ROOT / 'orders'
KITCHEN_DIR = ROOT / 'kitchen'
DELIVERY_DIR = ROOT / 'delivery'

# Tests use temporary databases so real data is never touched
TEMP_DIR = tempfile.mkdtemp(prefix='pizza-tests-')
os.environ['ORDERS_DB_PATH'] = str(Path(TEMP_DIR) / 'orders.db')
os.environ['KITCHEN_DB_PATH'] = str(Path(TEMP_DIR) / 'kitchen.db')
os.environ['DELIVERY_DB_PATH'] = str(Path(TEMP_DIR) / 'delivery.db')
os.environ.setdefault('RABBITMQ_HOST', 'localhost')

# Services import their sibling modules by short names,
# so add their directories to the module search path
for directory in (GATEWAY_DIR, ORDERS_DIR, KITCHEN_DIR, DELIVERY_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


# Loads a module by path under a unique name
def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Load order matters: logic modules import their database modules
orders_logic_module = _load_module(ORDERS_DIR / 'order_logic.py', 'order_logic')
orders_app_module = _load_module(ORDERS_DIR / 'app.py', 'orders_app')
kitchen_logic_module = _load_module(KITCHEN_DIR / 'kitchen_logic.py', 'kitchen_logic')
kitchen_app_module = _load_module(KITCHEN_DIR / 'app.py', 'kitchen_app')
delivery_logic_module = _load_module(DELIVERY_DIR / 'delivery_logic.py', 'delivery_logic')
delivery_app_module = _load_module(DELIVERY_DIR / 'app.py', 'delivery_app')
gateway_app_module = _load_module(GATEWAY_DIR / 'app.py', 'gateway_app')


@pytest.fixture(scope='session')
def orders():
    # Schema is created on import, sample menu data is seeded explicitly here
    orders_app_module.service.seed()
    return orders_app_module


@pytest.fixture
def gateway():
    return gateway_app_module


@pytest.fixture
def gateway_client(gateway):
    gateway.app.config['TESTING'] = True
    return gateway.app.test_client()


@pytest.fixture
def kitchen(tmp_path):
    # A separate kitchen database per test, seeded with recipes and stock
    kitchen = kitchen_logic_module.Kitchen(db_path=str(tmp_path / 'kitchen.db'))
    kitchen.seed()
    return kitchen


@pytest.fixture
def dispatcher(tmp_path):
    # A separate delivery database per test, seeded with couriers
    dispatcher = delivery_logic_module.Dispatcher(db_path=str(tmp_path / 'delivery.db'))
    dispatcher.seed()
    return dispatcher


@pytest.fixture
def order_service(tmp_path):
    # A separate orders database per test, seeded with the default menu
    service = orders_logic_module.OrderService(db_path=str(tmp_path / 'orders.db'))
    service.seed()
    return service


@pytest.fixture
def orders_module():
    return orders_app_module


@pytest.fixture
def kitchen_module():
    # The module-level kitchen uses the shared test database
    kitchen_app_module.kitchen.seed()
    return kitchen_app_module


@pytest.fixture
def delivery_module():
    delivery_app_module.dispatcher.seed()
    return delivery_app_module
