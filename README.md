# Demo distribuida simple

Mini demo tipo MapReduce
Cada pestana del navegador funciona como un worker que:

1. Pide una tarea al servidor.
2. Cuenta palabras del fragmento recibido.
3. Devuelve el resultado al coordinador.

## Requisitos

- Python 3.8+
- Dependencias instaladas

```bash
pip install -r requirements.txt
```

## Ejecutar local

```bash
python3 server.py
```

Abrir en navegador:

- Worker: http://localhost:8000/
- Dashboard: http://localhost:8000/lab

Uso recomendado:

1. Abrir 2-4 pestanas en `/` para simular workers.
2. Dejar abierto `/lab` para ver metricas en vivo.
3. Revisar workers activos, tareas pendientes y top de palabras.

## Limite de workers

Puede limitar cuantos workers activos se aceptan:

```bash
MAX_WORKERS=4 python3 server.py
```

Si se supera el limite, los workers extra reciben `max_workers_reached`.

## Exponer con ngrok

Con el servidor ya corriendo, en otra terminal:

```bash
ngrok http 8000
```

Si desea compartir la URL publica HTTPS de ngrok.

- `https://.../` para workers
- `https://.../lab` para dashboard

Nota: ngrok solo expone su app; si el servidor local esta apagado, la URL no responde.

## Endpoints utiles

- GET /status: estado general (workers, tareas, resultados)
- GET /workers: detalle de workers activos
- GET /worker/{worker_id}: detalle de un worker
- GET /aggregate: top global de palabras
- GET /tasks: pendientes y asignadas
- POST /requeue: reencolar una tarea
- POST /reset: reiniciar estado y reconstruir tareas



## Problemas comunes

- Puerto en uso: Recuerde que el puerto debe estar libre
- Server no responde en navegador: verifique que `python3 server.py` siga corriendo.
- Dashboard sin workers: abra nuevas pestanas en `/` y espere unos segundos (suele tardar un poco).
