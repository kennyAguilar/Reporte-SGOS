"""Configuración general de SGOS."""
import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    APP_NAME = os.getenv("APP_NAME", "SGOS")
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    DATABASE_URL = os.getenv("DATABASE_URL")
    FLASK_ENV = os.getenv("FLASK_ENV", "production")
    DEBUG = FLASK_ENV == "development"
