import json
import urllib.request
from app import app
from admin import app as admin_app

client = admin_app.test_client()

# Login
with client.session_transaction() as sess:
    sess['admin_ok'] = True

payload = {
    "category": "tech",
    "brand": "Test Brand",
    "in_stock": True,
    "stock_count": 10,
    "image_url": "",
    "content": "Test content here"
}

try:
    res = client.post('/api/kb', json=payload)
    print("STATUS:", res.status_code)
    print("DATA:", res.get_data(as_text=True))
except Exception as e:
    print("EXCEPTION:", type(e), e)
