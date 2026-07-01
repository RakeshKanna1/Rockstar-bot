import os

def required_env(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} environment variable is required")
    return value

BOT_TOKEN = required_env("BOT_TOKEN")
ADMIN_ID = int(required_env("ADMIN_ID"))
WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "+918317416695")
