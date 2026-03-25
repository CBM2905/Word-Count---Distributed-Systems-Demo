# Minimal MapReduce demo (browser workers)

Run the coordinator and open multiple browser tabs to act as workers.

Requirements:

- Python 3.8+
- Install dependencies: `pip install -r requirements.txt`

Start server:

```bash
python server.py
# or: uvicorn server:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/` in several browser tabs. Each tab will request a text chunk, compute local word counts, and POST results back to the server. Check `http://localhost:8000/status` and `http://localhost:8000/aggregate` to see progress and final aggregated counts.

For a simple lab dashboard open: `http://localhost:8000/dashboard` or `http://localhost:8000/lab`.

Useful endpoints:

- `GET /status` — summary of workers, tasks, results
- `GET /workers` — list active workers and last-seen
- `GET /top?n=10` — top n words
- `POST /requeue` — requeue a task (body `{task_id: N}`)
- `POST /reset` — reset server state and rebuild tasks

Simulate multiple workers locally:

```bash
python simulate_worker.py sim1 0.2 &
python simulate_worker.py sim2 0.5 &
```

Open the dashboard and adjust the worker compute delay from real browser workers via the `Compute delay (ms)` control.
