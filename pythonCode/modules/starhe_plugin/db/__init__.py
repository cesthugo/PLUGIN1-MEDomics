# db/__init__.py
from starhe_plugin.db.mongo_client import save_result, get_result, list_results, delete_result

__all__ = ["save_result", "get_result", "list_results", "delete_result"]
