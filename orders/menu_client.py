import os

from rpc_client import RpcClient

# Queue of the menu service (overridable for tests / another deployment)
MENU_QUEUE = os.getenv('MENU_RPC_QUEUE', 'menu_rpc')


# Raised when the menu service cannot answer (broker error, timeout, 5xx)
class MenuUnavailable(Exception):
    pass


# Synchronous client for the menu service. Orders has no menu table anymore,
# so every price lookup is a small RPC call.
class MenuClient:
    def __init__(self, host, timeout=5, queue=None):
        self.rpc = RpcClient(host, timeout)
        self.queue = queue or MENU_QUEUE

    # Returns a pizza by code or None when it is not on the menu
    def get_pizza(self, code):
        try:
            response = self.rpc.call(
                self.queue, {'action': 'get_pizza', 'payload': {'pizza': code}})
        except Exception as error:
            raise MenuUnavailable(str(error)) from error

        status = response.get('status')
        if status == 404:
            return None
        if status != 200:
            body = response.get('body') or {}
            raise MenuUnavailable(body.get('error') or f'Menu service returned {status}')
        return response.get('body')
