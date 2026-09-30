# -*- coding: utf-8 -*-
"""
The core in a process of its own, spoken to over the real protocol.

Lifted out of `test_service.py`, where it was written and where two other
checks would have had to copy it. A driver copied is a driver that drifts:
the second copy keeps answering the handshake the way the protocol looked
on the day it was pasted.

**Speaks frames, not method calls.** Reaching into the core's objects would
check that the handlers exist, which is never in doubt; what is in doubt is
whether a shell that asks over the wire gets an answer it can act on.
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from console import child_env
from core.wire import (Envelope, FrameDecoder, IdGenerator, MessageType,
                       Session, Side, encode_frame, new_trace_id)

LAUNCHER = os.path.join(ROOT, "rina_core.py")


class Core:
    """The core in a separate process; outwards — only frames."""

    def __init__(self, extra=(), env=None):
        # `env` so a check can give the core a profile of its own. Questions
        # like "is this a first run" are answered out of the settings file,
        # and a check answering out of the developer's would say "no" on the
        # one machine it is ever run on — and pass for the wrong reason.
        environment = child_env()
        environment.update(env or {})
        self.proc = subprocess.Popen(
            [sys.executable, "-u", LAUNCHER, "--transport", "stdio", *extra],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=ROOT, env=environment)
        self.decoder = FrameDecoder()
        self.ids = IdGenerator("s-")
        self.session = Session(side=Side.SHELL)
        self.apps = []          # the index we hand to the core
        self.did = []           # the system actions that were asked for
        self.launched = []      # what was asked to be launched

    def send(self, envelope):
        self.proc.stdin.write(encode_frame(envelope))
        self.proc.stdin.flush()
        return envelope

    def ask(self, method, payload=None, trace_id=None):
        return self.send(Envelope.request(
            method, dict(payload or {}), id=self.ids.next(),
            trace_id=trace_id or new_trace_id()))

    def read_until(self, method, timeout=30.0, limit=20):
        """
        Read until the event we need arrives.

        The "accepted" answer and Rina's answer itself are separated in
        time — that is the point: the command thinks, and the request is not
        held open. Waiting for a fixed number of messages would mean
        guessing how many there will be.
        """
        seen = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(seen) < limit:
            if self.proc.poll() is not None:
                break                # the core died — there is nothing more to wait for
            batch = self.read(1, timeout=deadline - time.monotonic())
            if not batch:
                break
            seen.extend(batch)
            if any(m.method == method for m in batch):
                break
        return seen

    #: What the core asked to be done to the machine and what to launch.
    #: The checks look here: the core has no system calls of its own any more.
    def serve(self, message):
        """
        Answer a counter-request from the core, as a shell would.

        Returns True if the message was a request and was answered — such
        messages do not count as "arrived": they are our half of the
        conversation, not the core's answer.
        """
        if message.type != MessageType.REQUEST:
            return False

        if message.method == "apps.index":
            payload = {"entries": list(self.apps)}
        elif message.method == "apps.launch":
            self.launched.append(message.payload.get("launch", ""))
            payload = {"ok": True, "reason": ""}
        elif message.method == "system.do":
            self.did.append(message.payload.get("action", ""))
            payload = {"ok": True, "detail": ""}
        else:
            return False

        self.send(message.reply(payload, id=self.ids.next()))
        return True

    def read(self, count=1, timeout=15.0):
        """Wait for the stated number of messages."""
        got, deadline = [], time.monotonic() + timeout
        while len(got) < count and time.monotonic() < deadline:
            header = self.proc.stdout.read(4)
            if not header or len(header) < 4:
                break
            size = int.from_bytes(header, "big")
            body = b""
            while len(body) < size:
                piece = self.proc.stdout.read(size - len(body))
                if not piece:
                    break
                body += piece
            for message in self.decoder.feed(header + body):
                # A request from the core is our own business rather than
                # an "arrived message": handing it outwards would mean
                # making every check know that the core sometimes asks.
                if not self.serve(message):
                    got.append(message)
        return got

    def handshake(self):
        """
        Say hello and take **the reply**, not the first thing that arrives.

        The core may emit an event before it answers — a plugin switching
        on, a setting read — and taking the first message treated that as
        the reply. The failure looked like "the core did not name a
        protocol version", which is true of an event and says nothing about
        what went wrong.
        """
        sent = self.ask("hello", self.session.hello_payload())
        for _ in range(8):
            got = self.read(1)
            if not got:
                break
            if got[0].correlation_id == sent.id:
                self.session.accept_hello_result(got[0].payload)
                return got[0]
        raise RuntimeError("ядро не ответило на приветствие")

    def stderr_text(self):
        try:
            return self.proc.stderr.read().decode("utf-8", "replace")
        except Exception:
            return ""

    def wait(self, timeout=15.0):
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            return None
