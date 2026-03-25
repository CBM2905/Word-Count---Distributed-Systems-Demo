from fastapi import FastAPI, Request, Query
from fastapi.responses import FileResponse, JSONResponse
from collections import Counter
import uvicorn
import logging
import time
import os
from typing import Dict, Any
import threading

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI()

# Task storage and state
tasks = []  # list of {id:int, text:str}
assigned_tasks = {}  # task_id -> worker_id
results = []  # list of Counters received
global_counter = Counter()

# Worker tracking: worker_id -> {last_seen: timestamp, name: str, tasks_processed: int, words_processed: int}
worker_info = {}

# pruning configuration (seconds)
WORKER_TIMEOUT = 15
PRUNE_INTERVAL = 5
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))


def is_worker_active(info: Dict[str, Any], now: float = None) -> bool:
    now = now or time.time()
    return (now - info.get("last_seen", 0)) <= WORKER_TIMEOUT


def active_worker_count(now: float = None) -> int:
    now = now or time.time()
    return sum(1 for info in worker_info.values() if is_worker_active(info, now))

# load text and create tasks
text = open("book.txt").read()
chunk_size = 100
task_id = 0
for i in range(0, len(text), chunk_size):
    tasks.append({"id": task_id, "text": text[i:i+chunk_size]})
    task_id += 1


@app.get("/")
def root():
    return FileResponse("worker.html")


@app.get("/lab")
def lab():
    return FileResponse("lab.html")


@app.get("/task")
def get_task(worker_id: str = Query(None), worker_name: str = Query(None)):
    """Assign one task to the requesting worker (if available).

    Worker should include `worker_id` as query parameter. We update
    the worker's last-seen timestamp so /status can show connected workers.
    """
    now = time.time()
    if not worker_id:
        return {"task": None, "error": "missing_worker_id"}

    if worker_id:
        prev = worker_info.get(worker_id, {})
        is_new_or_inactive = (not prev) or (not is_worker_active(prev, now))
        if is_new_or_inactive and active_worker_count(now) >= MAX_WORKERS:
            logging.info(f"Rejected worker {worker_id}: max_workers={MAX_WORKERS} reached")
            return {"task": None, "error": "max_workers_reached", "max_workers": MAX_WORKERS}

        name = worker_name or (prev.get('name') if prev else worker_id)
        # preserve counters if present
        tasks_processed = prev.get('tasks_processed', 0)
        words_processed = prev.get('words_processed', 0)
        worker_info[worker_id] = {"last_seen": now, "name": name, "tasks_processed": tasks_processed, "words_processed": words_processed}
        if not prev:
            logging.info(f"Worker connected: {worker_id} name={name}")
        elif prev and prev.get('name') != name:
            logging.info(f"Worker renamed: {worker_id} -> {name}")
        logging.info(f"Worker {worker_id} heartbeat/update")

    if tasks:
        task = tasks.pop()
        assigned_tasks[task["id"]] = worker_id
        wname = worker_info.get(worker_id, {}).get('name') if worker_id else None
        logging.info(f"Assigned task {task['id']} to worker {worker_id} name={wname}")
        return {"task": {"id": task["id"], "text": task["text"]}}

    return {"task": None}


@app.post("/result")
async def receive_result(request: Request):
    """Receive a worker result. Expected JSON body:
    {"worker_id": "abc", "task_id": 3, "counts": {"word": 2, ...}}
    """
    body = await request.json()
    worker_id = body.get("worker_id")
    worker_name = body.get("worker_name")
    task_id = body.get("task_id")
    counts = body.get("counts") or {}

    if worker_id:
        prev = worker_info.get(worker_id, {})
        name = worker_name or (prev.get('name') if prev else worker_id)
        tasks_processed = prev.get('tasks_processed', 0)
        words_processed = prev.get('words_processed', 0)
        worker_info[worker_id] = {"last_seen": time.time(), "name": name, "tasks_processed": tasks_processed, "words_processed": words_processed}

    # store and aggregate
    c = Counter(counts)
    results.append(c)
    global_counter.update(c)

    # update per-worker stats
    if worker_id:
        info = worker_info.get(worker_id, {})
        info['tasks_processed'] = info.get('tasks_processed', 0) + 1
        info['words_processed'] = info.get('words_processed', 0) + sum(c.values())
        info['last_seen'] = time.time()
        # update per-worker local counter
        local = info.get('local_counter', Counter())
        local.update(c)
        info['local_counter'] = local
        worker_info[worker_id] = info

    wname = worker_info.get(worker_id, {}).get('name')
    logging.info(f"Result received from worker={worker_id} name={wname} task={task_id} words={sum(c.values())} unique={len(c)}")

    # mark task as no longer assigned (if present)
    if task_id in assigned_tasks:
        assigned_tasks.pop(task_id, None)

    return JSONResponse({"status": "ok"})


@app.get("/status")
def status():
    """Return simple status for the demo UI: connected workers, tasks remaining, results received."""
    now = time.time()
    # consider a worker "connected" if seen within last 15 seconds
    # consider a worker "connected" if seen within last 15 seconds
    threshold = 15.0
    # prune inactive workers and log disconnects
    to_remove = []
    for wid, info in list(worker_info.items()):
        if now - info.get('last_seen', 0) > threshold:
            to_remove.append(wid)

    for wid in to_remove:
        info = worker_info.pop(wid, None)
        logging.info(f"Worker disconnected (pruned): {wid} name={info.get('name') if info else None}")

    connected_workers = active_worker_count(now)

    return {
        "connected_workers": connected_workers,
        "max_workers": MAX_WORKERS,
        "worker_limit_reached": connected_workers >= MAX_WORKERS,
        "tasks_remaining": len(tasks),
        "results_received": len(results)
    }


@app.get("/top")
def top(n: int = 10):
    """Return top `n` most common words."""
    most = global_counter.most_common(n)
    return {"top": [{"word": w, "count": c} for w, c in most]}


@app.get("/dashboard")
def dashboard():
    return FileResponse("lab.html")


def start_pruner():
    """Background thread that removes inactive workers and requeues their tasks."""
    def pruner():
        while True:
            time.sleep(PRUNE_INTERVAL)
            now = time.time()
            removed = []
            # find inactive workers from worker_info
            for wid, info in list(worker_info.items()):
                if now - info.get('last_seen', 0) > WORKER_TIMEOUT:
                    removed.append(wid)
                    worker_info.pop(wid, None)
                    logging.info(f"Worker {wid} disconnected (timeout)")

            # requeue tasks assigned to removed workers
            for tid, wid in list(assigned_tasks.items()):
                if wid in removed:
                    assigned_tasks.pop(tid, None)
                    # placeholder empty text for demo; real system would persist
                    tasks.append({"id": tid, "text": ""})
                    logging.info(f"Requeued task {tid} from disconnected worker {wid}")

    t = threading.Thread(target=pruner, daemon=True)
    t.start()


@app.on_event("startup")
def on_startup():
    logging.info("Coordinator starting up; launching pruner thread")
    start_pruner()


@app.get("/workers")
def workers():
    """Return known workers and last-seen seconds ago."""
    now = time.time()
    return {
        "workers": [
            {
                "worker_id": wid,
                "name": info.get('name'),
                "last_seen_seconds": round(now - info.get('last_seen', 0), 1),
                "tasks_processed": info.get('tasks_processed', 0),
                "words_processed": info.get('words_processed', 0)
            }
            for wid, info in worker_info.items()
            if is_worker_active(info, now)
        ]
    }


@app.get("/worker/{worker_id}")
def worker_detail(worker_id: str, top: int = 20):
    """Return detailed per-worker stats including local top words."""
    info = worker_info.get(worker_id)
    if not info:
        return JSONResponse({"error": "unknown worker"}, status_code=404)

    local_counter = info.get('local_counter', Counter())
    most = local_counter.most_common(top)
    return {
        "worker_id": worker_id,
        "name": info.get('name'),
        "last_seen_seconds": round(time.time() - info.get('last_seen', 0), 1),
        "tasks_processed": info.get('tasks_processed', 0),
        "words_processed": info.get('words_processed', 0),
        "top_local": [{"word": w, "count": c} for w, c in most]
    }


@app.get("/tasks")
def list_tasks():
    """Return pending task ids and currently assigned tasks mapping."""
    pending = [t["id"] for t in tasks]
    # present assigned mapping with worker names when available
    assigned_presentable = {}
    for tid, wid in assigned_tasks.items():
        assigned_presentable[tid] = {"worker_id": wid, "worker_name": worker_info.get(wid, {}).get('name')}
    return {"pending": pending, "assigned": assigned_presentable}


@app.post("/requeue")
async def requeue(request: Request):
    """Requeue a single task by id for demo purposes: POST {"task_id": N}"""
    body = await request.json()
    tid = body.get("task_id")
    if tid is None:
        return JSONResponse({"error": "missing task_id"}, status_code=400)

    # only requeue if not already pending
    if any(t["id"] == tid for t in tasks):
        return JSONResponse({"status": "already_pending"})

    # if assigned, remove assignment and requeue
    assigned_tasks.pop(tid, None)
    # Can't reconstruct text easily from original chunks here; in demo we'll create an empty placeholder
    tasks.append({"id": tid, "text": ""})
    logging.info(f"Task {tid} requeued via /requeue")
    return JSONResponse({"status": "requeued", "task_id": tid})


# /top is implemented above with a parameterized endpoint


@app.get("/aggregate")
def aggregate(top: int = 50):
    """Return the global aggregated word counts (most common first)."""
    most = global_counter.most_common(top)
    return {"total_unique_words": len(global_counter), "top": [{"word": w, "count": c} for w, c in most]}


@app.post("/reset")
def reset():
    """Reset the server state and rebuild tasks from `book.txt`."""
    global tasks, assigned_tasks, results, global_counter, worker_info
    try:
        text = open("book.txt").read()
    except Exception as e:
        return JSONResponse({"error": f"could not read book.txt: {e}"}, status_code=500)

    # rebuild tasks
    chunk_size = 1000
    new_tasks = []
    tid = 0
    for i in range(0, len(text), chunk_size):
        new_tasks.append({"id": tid, "text": text[i:i+chunk_size]})
        tid += 1

    tasks = new_tasks
    assigned_tasks = {}
    results = []
    global_counter = Counter()
    worker_info = {}

    logging.info("Server state reset via /reset; tasks rebuilt")
    return JSONResponse({"status": "reset", "tasks": len(tasks)})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)