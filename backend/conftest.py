import os
import tempfile

# Tests run in development mode with an isolated database and demo users.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'test.db')}")
os.environ.setdefault("SEED_DEMO_USERS", "true")
os.environ.setdefault("DEMO_PASSWORD", "a-long-demo-password-1")
