import os
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import run_simple
from app import app as chat_app
from admin import app as admin_app

# The chat application is the default (available at /)
# The admin dashboard is mounted at /admin
application = DispatcherMiddleware(chat_app, {
    '/admin': admin_app
})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting server on port {port}...")
    print("Chat interface: http://localhost:{}/".format(port))
    print("Admin dashboard: http://localhost:{}/admin/".format(port))
    run_simple('0.0.0.0', port, application, use_reloader=True, use_debugger=True)
