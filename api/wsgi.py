"""WSGI entry point for gunicorn."""
from serve import app, load_data

load_data()
