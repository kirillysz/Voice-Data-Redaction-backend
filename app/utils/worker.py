from rq import Worker, Queue
from redis_client import get_redis


def main():
    redis_conn = get_redis()
    queues = [Queue("audio", connection=redis_conn)]

    worker = Worker(queues)
    worker.work()

if __name__ == "__main__":
    main()