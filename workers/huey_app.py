import os
from huey import SqliteHuey

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
queue_file = os.path.join(DATA_DIR, 'huey_queue.db')

# Create a Huey instance with SQLite backend for lean deployment
huey = SqliteHuey(filename=queue_file)
