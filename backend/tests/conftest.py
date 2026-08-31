import os

# Tests must never inherit development credentials or middleware policy from
# the repository-root .env. These values are applied while conftest is loaded,
# before test modules import app.main and freeze its middleware configuration.
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "AUTH_MODE": "disabled",
        "TRUSTED_HOSTS": "localhost,127.0.0.1,testserver",
        "CORS_ORIGINS": "http://localhost:3000,http://127.0.0.1:3000",
        "DATABASE_URL": "",
        "MIGRATION_DATABASE_URL": "",
        "AGENT_CHECKPOINT_DATABASE_URL": "",
        "SUPABASE_URL": "",
        "SUPABASE_SERVICE_ROLE_KEY": "",
        "GROQ_API_KEY": "",
        "RAZORPAY_KEY_ID": "",
        "RAZORPAY_KEY_SECRET": "",
    }
)
