from rq import Worker, Queue

from app.utils.redis_client import get_redis
from app.utils.asr import get_model
from app.core.config import settings


get_model(settings.ASR_MODEL_NAME)

def main():
    redis_conn = get_redis()
    queues = [Queue("audio", connection=redis_conn)]

    worker = Worker(queues, connection=redis_conn)
    worker.work()

if __name__ == "__main__":
    main()