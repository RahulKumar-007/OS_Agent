"""Manual smoke test for the interactive PTY terminal WebSocket.
Run with the backend already running: python3 test_pty_ws_manual.py
"""
import asyncio
import json

import websockets


async def main():
    uri = "ws://localhost:8000/ws/terminal"
    async with websockets.connect(uri) as ws:
        # Send a command
        await ws.send(json.dumps({"type": "input", "data": "echo HELLO_FROM_PTY\n"}))
        output = ""
        try:
            for _ in range(20):
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
                data = json.loads(msg)
                if data.get("type") == "output":
                    output += data["data"]
                    if "HELLO_FROM_PTY" in output:
                        break
        except asyncio.TimeoutError:
            pass
        print("=== OUTPUT ===")
        print(output)
        assert "HELLO_FROM_PTY" in output, "PTY did not echo expected output"
        print("PTY TEST PASSED")


asyncio.run(main())
