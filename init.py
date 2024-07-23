from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_restful import Api
from celery import Celery, Task
from flask_cors import CORS
from flask_caching import Cache
# from flask_socketio import SocketIO, emit

online_users = set()

db = SQLAlchemy()
app = Flask(__name__)
api = Api(app)
CORS(app, origins="*",
     methods='GET,HEAD,PUT,PATCH,POST,DELETE', allow_headers="*")
UPLOAD_FOLDER = r'static'
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["PRO_UPLOAD_FOLDER"] = 'protected'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///library_database.sqlite3'
app.secret_key = "My_very_secret_key"
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/1'
app.config['RESULT_BACKEND'] = 'redis://localhost:6379/2'
app.config['CACHE_TYPE'] = 'RedisCache'
app.config['CACHE_REDIS_HOST'] = 'localhost'
app.config['CACHE_REDIS_PORT'] = 6379
app.config['CACHE_REDIS_DB'] = 0
celery = Celery(
    app.name, broker=app.config['CELERY_BROKER_URL'], backend=app.config['RESULT_BACKEND'])
celery.conf.update(app.config)
celery.conf.enable_utc = False
celery.conf.timezone = "Asia/Kolkata"
cache = Cache(app)


class ContextTask(Task):
    def __call__(self, *args, **kwargs):
        with app.app_context():
            return self.run(*args, **kwargs)


celery.Task = ContextTask

db.init_app(app)
app.app_context().push()
