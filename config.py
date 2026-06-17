import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key')
    DATABASE_PATH = os.environ.get('DATABASE_PATH', 'database/app.db')
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 20971520))
    OLLAMA_HOST = os.environ.get('OLLAMA_HOST', 'host.docker.internal')
    OLLAMA_PORT = os.environ.get('OLLAMA_PORT', '11434')
    OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'qwen2.5:14b')
    OLLAMA_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"
