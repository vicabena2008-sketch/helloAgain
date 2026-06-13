import os
from werkzeug.serving import run_simple
from admin import app as admin_app

application = admin_app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting server on port {port}...")
    print("Admin dashboard: http://localhost:{}/".format(port))
    run_simple('0.0.0.0', port, application, use_reloader=True, use_debugger=True)
