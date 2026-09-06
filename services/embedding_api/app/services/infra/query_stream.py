"""Bounded sync RAG -> async NDJSON bridge with heartbeat and cancellation."""
import asyncio
import json
import logging
import queue
import threading

logger = logging.getLogger(__name__)
# Bound expensive background jobs, including jobs draining after disconnect.
_slots = threading.BoundedSemaphore(4)


async def ndjson_events(factory, serialize, request, heartbeat_seconds=10):
    cancelled = threading.Event()
    pending = queue.Queue(maxsize=32)

    def encode(event):
        return json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n"

    if not _slots.acquire(blocking=False):
        yield encode({"type": "error", "message": "処理が混み合っています。時間をおいて再試行してください。"})
        return

    def send(event):
        while not cancelled.is_set():
            try:
                pending.put(event, timeout=0.1)
                return
            except queue.Full:
                pass

    def produce():
        events = None
        try:
            events = factory(cancelled)
            for event in events:
                if cancelled.is_set():
                    break
                if event["type"] == "result":
                    result = serialize(event["result"]).model_dump(mode="json")
                    send(encode({**result, "type": "complete"}))
                    break
                send(encode(event))
        except GeneratorExit:
            pass
        except Exception:
            logger.exception("Query stream failed")
            send(encode({"type": "error", "message": "回答処理中にエラーが発生しました。"}))
        finally:
            try:
                if events is not None:
                    events.close()
            finally:
                _slots.release()
                send(None)

    try:
        loop = asyncio.get_running_loop()
        worker = loop.run_in_executor(None, produce)
    except BaseException:
        _slots.release()
        raise
    last_sent = loop.time()
    try:
        while True:
            if await request.is_disconnected():
                return
            try:
                event = pending.get_nowait()
            except queue.Empty:
                if worker.done():
                    worker.result()
                    return
                if loop.time() - last_sent >= heartbeat_seconds:
                    yield encode({"type": "heartbeat"})
                    last_sent = loop.time()
                await asyncio.sleep(0.05)
                continue
            if event is None:
                return
            yield event
            last_sent = loop.time()
    finally:
        cancelled.set()
        # Sync model/DB calls cannot be forcibly interrupted safely. The worker
        # exits at its next checkpoint and keeps its slot until cleanup finishes.
