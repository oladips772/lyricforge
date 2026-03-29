"""
Simple in-memory job store.
For production, replace with Redis:
  import redis, json
  r = redis.Redis(host='localhost', port=6379)
  job_store[id] = r.set(id, json.dumps(data))
"""

job_store: dict = {}


def update_job(job_id: str, **kwargs):
    if job_id in job_store:
        job_store[job_id].update(kwargs)
