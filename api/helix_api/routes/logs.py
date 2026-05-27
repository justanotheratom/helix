"""SSE log stream — subscribes to redis pub/sub channel for a job.

Replay-on-connect is not supported in v1; live tail only. (Historical
log content is uploaded as the `helix/stdout.log` artifact on job
completion.)
"""
from __future__ import annotations

import json
import uuid
from typing import Iterator

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from .. import redis_bus

router = APIRouter(prefix="/jobs/{job_id}", tags=["logs"])


@router.get("/logs")
def stream_logs(job_id: uuid.UUID, follow: bool = Query(default=True)):
    def gen() -> Iterator[bytes]:
        r = redis_bus.get_redis()
        pubsub = r.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(redis_bus.logs_channel(str(job_id)))
        try:
            yield b": connected\n\n"
            if not follow:
                # One-shot: emit a single "no live stream" comment and close.
                yield b": follow=false; no replay available in v1\n\n"
                return
            while True:
                msg = pubsub.get_message(timeout=15.0)
                if msg is None:
                    # heartbeat to keep proxies from closing the connection
                    yield b": ping\n\n"
                    continue
                data = msg.get("data", "")
                if isinstance(data, bytes):
                    data = data.decode("utf-8", errors="replace")
                payload = data if data.startswith("{") else json.dumps({"line": data})
                yield f"data: {payload}\n\n".encode()
        finally:
            try:
                pubsub.close()
            except Exception:
                pass

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
