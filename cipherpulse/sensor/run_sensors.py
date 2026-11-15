"""Wearable process: signs readings, streams over WebSocket, buffers offline.

Control messages from the gateway (scenario / link / spoof) arrive on the same socket.
"""
import asyncio
import copy
import json
import random
import time
from collections import deque
from datetime import datetime, timezone

import websockets
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .. import config
from ..security import crypto
from .simulator import Wearable


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Node:
    def __init__(self, astro_id):
        self.w = Wearable(astro_id)
        self.key = crypto.device_key(astro_id)
        self.seq = int(time.time() * 1000)
        self.queue = deque(maxlen=5000)  # offline buffer
        self.sent = deque(maxlen=50)     # for replay attacks

    def make_packet(self, link_up: bool) -> dict:
        self.seq = max(self.seq + 1, int(time.time() * 1000))
        body = {
            "astronaut_id": self.w.id, "seq": self.seq, "ts": now_iso(),
            "vitals": self.w.step(), "buffered": not link_up,
        }
        body["signature"] = crypto.sign(self.key, body)
        return body


async def main(url):
    nodes = {a: Node(a) for a in config.CREW}
    link = {"up": True}
    attacker = Ed25519PrivateKey.generate()
    outbox: asyncio.Queue = asyncio.Queue()

    async def spoof(astro, kind):
        n = nodes.get(astro)
        if not n:
            return
        if kind == "forge":
            body = {"astronaut_id": astro, "seq": n.seq + 1000, "ts": now_iso(),
                    "vitals": {"hr": 71, "spo2": 98, "temp": 36.6, "resp": 14, "radiation": 0.3},
                    "buffered": False}
            body["signature"] = crypto.sign(attacker, body)
            await outbox.put(body)
        elif kind == "replay" and n.sent:
            await outbox.put(copy.deepcopy(random.choice(list(n.sent))))
        elif kind == "modify" and n.sent:
            p = copy.deepcopy(n.sent[-1]); p["vitals"]["hr"] = 31.0  # keep old signature
            p["seq"] = n.seq + 2000
            await outbox.put(p)

    async def producer():
        while True:
            for n in nodes.values():
                p = n.make_packet(link["up"])
                if link["up"]:
                    n.sent.append(copy.deepcopy(p))
                    await outbox.put(p)
                else:
                    n.queue.append(p)
            await asyncio.sleep(1.0)

    while True:
        try:
            async with websockets.connect(url, max_size=2**22) as ws:
                print("[sensors] connected to gateway", flush=True)

                async def sender():
                    while True:
                        if link["up"]:
                            # flush buffered packets first, strictly in order
                            for n in nodes.values():
                                while n.queue:
                                    await ws.send(json.dumps(n.queue.popleft()))
                                    await asyncio.sleep(0.02)
                            await ws.send(json.dumps(await outbox.get()))
                        else:
                            await asyncio.sleep(0.2)

                async def receiver():
                    async for raw in ws:
                        m = json.loads(raw)
                        cmd = m.get("cmd")
                        if cmd == "scenario":
                            nodes[m["astro"]].w.trigger(m["name"]) if m.get("astro") in nodes else None
                        elif cmd == "phase":
                            for n in nodes.values():
                                n.w.set_phase(m.get("name"))
                        elif cmd == "link":
                            link["up"] = bool(m["up"])
                            await ws.send(json.dumps({"event": "link", "up": link["up"],
                                                      "queued": sum(len(n.queue) for n in nodes.values())}))
                        elif cmd == "spoof":
                            await spoof(m.get("astro"), m.get("kind"))

                prod = asyncio.create_task(producer())
                try:
                    await asyncio.gather(sender(), receiver())
                finally:
                    prod.cancel()
        except Exception as e:  # gateway down -> keep buffering, retry
            print(f"[sensors] gateway unreachable ({e!r}); buffering and retrying", flush=True)
            link_was = link["up"]
            link["up"] = False
            for _ in range(3):
                for n in nodes.values():
                    n.queue.append(n.make_packet(False))
                await asyncio.sleep(1)
            link["up"] = link_was


if __name__ == "__main__":
    asyncio.run(main(f"ws://{config.HOST}:{config.PORT}/ws/sensor"))
