import sqlite3
from db.customers import update_kb_item

try:
    print("Updating kb item...")
    update_kb_item(1, "test", "test", True, 10, None, "test")
    print("Success")
except Exception as e:
    print("Error:", type(e), e)
