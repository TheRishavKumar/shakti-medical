import os
import sys

def get_base_dir():
    if getattr(sys, 'frozen', False):
        # Running as exe
        return os.path.dirname(sys.executable)
    else:
        # Running as python script
        return os.path.abspath(os.path.dirname(__file__))

BASE_DIR = get_base_dir()
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_DIR, exist_ok=True)

class Config:
    SECRET_KEY = "medical_manager_secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(INSTANCE_DIR, 'database.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False