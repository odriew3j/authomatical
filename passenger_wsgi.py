# passenger_wsgi.py
import sys
import os


sys.path.insert(0, os.path.dirname(__file__))

from services.web_app import app

application = app
