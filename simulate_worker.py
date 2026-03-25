#!/usr/bin/env python3
import urllib.request
import urllib.parse
import json
import time
import re
import sys

def normalize(word):
    w = word.lower()
    w = re.sub(r"[^a-z0-9'-]", '', w)
    return w

def main():
    worker_id = sys.argv[1] if len(sys.argv) > 1 else 'sim-' + str(int(time.time()*1000)%100000)
    delay = float(sys.argv[2]) if len(sys.argv) > 2 else 0.2
    worker_name = sys.argv[3] if len(sys.argv) > 3 else None
    url_base = 'http://127.0.0.1:8000'
    print('Worker id:', worker_id, 'delay(s)=', delay, 'name=', worker_name)

    while True:
        try:
            q = f"{url_base}/task?worker_id={urllib.parse.quote(worker_id)}"
            if worker_name:
                q += f"&worker_name={urllib.parse.quote(worker_name)}"
            with urllib.request.urlopen(q) as r:
                data = json.load(r)
        except Exception as e:
            print('Error fetching task:', e)
            break

        task = data.get('task')
        if not task:
            print('No more tasks; exiting')
            break

        task_id = task.get('id')
        text = task.get('text', '')
        words = [normalize(w) for w in re.split(r"\s+", text) if w.strip()]

        counts = {}
        for w in words:
            if not w: continue
            counts[w] = counts.get(w, 0) + 1

        payload = {'worker_id': worker_id, 'worker_name': worker_name, 'task_id': task_id, 'counts': counts}
        data_bytes = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(f"{url_base}/result", data=data_bytes, headers={'Content-Type':'application/json'})
        try:
            # simulate compute time
            time.sleep(delay)
            with urllib.request.urlopen(req) as resp:
                resp_data = resp.read().decode()
            print(f"Posted result for task={task_id} words={sum(counts.values())} unique={len(counts)}")
        except Exception as e:
            print('Error posting result:', e)
            # push task back? for demo we just exit
            break

        time.sleep(0.2)

if __name__ == '__main__':
    main()
