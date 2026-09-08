import asyncio
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import TimeoutError as PoolTimeout
from wsi_viewer.assessment_admission import AssessmentAdmissionMiddleware
from wsi_viewer.database_pressure import PressureQueuePool


async def request(app, path="/api/v2/assessment/access"):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app({"type": "http", "path": path}, receive, send)
    return messages


def test_burst_queues_before_pool_checkout_instead_of_timing_out():
    async def scenario(gated):
        engine = create_engine(
            "sqlite://", poolclass=PressureQueuePool, pool_size=2, max_overflow=0,
            pool_timeout=0.005, connect_args={"check_same_thread": False},
        )

        def work():
            try:
                with engine.connect():
                    time.sleep(0.03)
                return 200
            except PoolTimeout:
                return 500

        async def app(scope, receive, send):
            status = await asyncio.to_thread(work)
            await send({"type": "http.response.start", "status": status, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        target = AssessmentAdmissionMiddleware(app, concurrency=2) if gated else app
        try:
            responses = await asyncio.gather(*(request(target) for _ in range(40)))
            return [messages[0]["status"] for messages in responses]
        finally:
            engine.dispose()

    assert 500 in asyncio.run(scenario(False))
    assert asyncio.run(scenario(True)) == [200] * 40


def test_queue_bound_timeout_cancellation_and_observer_bypass():
    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()

        async def app(scope, receive, send):
            if scope["path"].startswith("/api/v2/"):
                entered.set()
                await release.wait()
            await send({"type": "http.response.start", "status": 200, "headers": []})

        gate = AssessmentAdmissionMiddleware(app, concurrency=1, max_waiting=1, wait_seconds=0.05)
        active = asyncio.create_task(request(gate))
        await entered.wait()
        queued = asyncio.create_task(request(gate))
        while gate.pending != 2:
            await asyncio.sleep(0)
        assert (await request(gate))[0]["status"] == 503
        assert (await request(gate, "/api/v1/internal/capacity/pressure"))[0]["status"] == 200
        assert (await queued)[0]["status"] == 503
        assert gate.pending == 1
        queued = asyncio.create_task(request(gate))
        while gate.pending != 2:
            await asyncio.sleep(0)
        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued
        assert gate.pending == 1
        active.cancel()
        with pytest.raises(asyncio.CancelledError):
            await active
        assert gate.pending == 0
        release.set()
        assert (await request(gate))[0]["status"] == 200

    asyncio.run(scenario())


def test_slot_is_held_through_response_teardown_and_released_on_error():
    async def scenario():
        response_sent = asyncio.Event()
        finish_cleanup = asyncio.Event()

        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            response_sent.set()
            await finish_cleanup.wait()
            raise RuntimeError("synthetic teardown failure")

        gate = AssessmentAdmissionMiddleware(app, concurrency=1, max_waiting=0)
        active = asyncio.create_task(request(gate))
        await response_sent.wait()
        assert (await request(gate))[0]["status"] == 503
        finish_cleanup.set()
        with pytest.raises(RuntimeError, match="synthetic teardown"):
            await active
        assert gate.pending == 0
        assert not gate.slots.locked()

    asyncio.run(scenario())
