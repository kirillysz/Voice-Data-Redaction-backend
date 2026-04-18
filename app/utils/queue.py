from rq import Queue
from app.utils.redis_client import get_redis

def get_queue():
    return Queue("audio", connection=get_redis())
