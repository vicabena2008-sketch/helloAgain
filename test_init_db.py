import os
from dotenv import load_dotenv

# Load the environment variables (including DATABASE_URL)
load_dotenv()

from db.customers import init_db
print(f"Connecting to: {os.environ.get('DATABASE_URL')}")
print("Running init_db...")
init_db()
print("Success! Tables should now be created in Supabase.")
