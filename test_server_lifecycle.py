"""Lifecycle tests for jarvis_server: tool wiring, dedupe, reconnect, stop."""
import asyncio
import os
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jarvis_server as js


def _msg(**kw):
    base = dict(session_resumption_update=None, go_away=None, server_content=None, tool_call=None)
    base.update(kw)
    return SimpleNamespace(**base)


class FakeSession:
    def __init__(self, script):
        self.script = script          # async generator factory for receive()

    async def send_client_content(self, **kw): pass
    async def send_realtime_input(self, **kw): pass
    async def send_tool_response(self, **kw): pass

    def receive(self):
        return self.script()


class FakeConnect:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return False


class FakeClient:
    """Stands in for genai.Client; records each connect() call."""
    def __init__(self, sessions):
        self.sessions = list(sessions)
        self.connects = []
        outer = self

        class Live:
            def connect(self, model, config):
                outer.connects.append((model, config.session_resumption.handle))
                return FakeConnect(outer.sessions.pop(0) if outer.sessions else FakeSession(_forever))

        self.aio = SimpleNamespace(live=Live())


async def _forever():
    await asyncio.Event().wait()
    yield  # pragma: no cover


class LifecycleBase(unittest.TestCase):
    def setUp(self):
        self.mic_stop_events = []

        def fake_mic(loop, q, stop_event):
            self.mic_stop_events.append(stop_event)
            stop_event.wait()

        self.patches = [
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}),
            patch.object(js, "_mic_capture_thread", fake_mic),
            patch.object(js.pyaudio, "PyAudio", MagicMock()),
        ]
        for p in self.patches:
            p.start()
        js._active_mic_stop_event = None
        js._active_mic_thread = None

    def tearDown(self):
        js.session_running = False
        for p in reversed(self.patches):
            p.stop()


class TestToolWiring(unittest.TestCase):
    def test_every_declared_tool_is_implemented(self):
        cfg = js.build_live_config()
        decls = cfg.tools[0].function_declarations
        names = [d.name for d in decls]
        missing = [n for n in names if n not in js.tools_map and n != "confirm_action"]
        self.assertEqual(missing, [], f"Declared to Gemini but not wired: {missing}")

    def test_dedupe_only_blocks_identical_calls(self):
        calls = []
        js._last_tool_timestamps.clear()
        with patch.dict(js.tools_map, {"page_scroll": lambda **kw: calls.append(kw) or "ok"}):
            run = lambda a: asyncio.run(js.execute_tool_safely("page_scroll", a))
            self.assertEqual(run({"direction": "down"}), "ok")
            self.assertIn("just run", run({"direction": "down"}))     # immediate duplicate
            self.assertEqual(run({"direction": "up"}), "ok")         # different args run
            js._last_tool_timestamps.clear()                          # time passes
            self.assertEqual(run({"direction": "down"}), "ok")
        self.assertEqual(len(calls), 3)


class TestReconnect(LifecycleBase):
    def test_reconnects_with_resume_handle_after_drop(self):
        async def first_session():
            yield _msg(session_resumption_update=SimpleNamespace(resumable=True, new_handle="H1"))
            raise ConnectionError("socket dropped")

        client = FakeClient([FakeSession(first_session)])

        async def scenario():
            js.session_running = True
            with patch.object(js.genai, "Client", lambda **kw: client):
                task = asyncio.create_task(js.run_gemini_live())
                for _ in range(80):              # up to 8 s (includes 2 s backoff)
                    await asyncio.sleep(0.1)
                    if len(client.connects) >= 2:
                        break
                js.session_running = False
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        asyncio.run(scenario())
        self.assertGreaterEqual(len(client.connects), 2, "never reconnected after the drop")
        self.assertIsNone(client.connects[0][1])
        self.assertEqual(client.connects[1][1], "H1", "reconnect should resume the session")


class TestStop(LifecycleBase):
    def test_cancel_stops_session_and_mic_thread(self):
        client = FakeClient([FakeSession(_forever)])

        async def scenario():
            js.session_running = True
            with patch.object(js.genai, "Client", lambda **kw: client):
                task = asyncio.create_task(js.run_gemini_live())
                await asyncio.sleep(0.5)
                self.assertFalse(task.done())
                task.cancel()                                  # what "stop" now does
                done, _ = await asyncio.wait([task], timeout=5)
                return bool(done)

        finished = asyncio.run(scenario())
        self.assertTrue(finished, "session task did not stop")
        self.assertTrue(self.mic_stop_events and self.mic_stop_events[0].is_set(), "mic thread kept running")
        self.assertFalse(js.session_running)


if __name__ == "__main__":
    unittest.main()
