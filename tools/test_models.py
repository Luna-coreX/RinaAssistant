# -*- coding: utf-8 -*-
"""
4.0-E05: fetching a model says how it goes and stops when told.

Checked against a server of our own rather than a real model. A hundred and
forty megabytes over somebody's line is not a check, it is a wait — and a
check that needs the network gives a different answer depending on the room
it is run in.

What matters is not the bytes but the three promises: progress is reported,
cancelling stops it, and nothing half-finished is left behind. All three are
about what happens **while** it downloads, which a finished download cannot
show.
"""
import http.server
import os
import shutil
import sys
import tempfile
import threading

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")

from core import models

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


BODY = b"x" * (900 * 1024)


class Slow(http.server.BaseHTTPRequestHandler):
    """Serves a megabyte slowly enough to be caught in the middle."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        for at in range(0, len(BODY), 64 * 1024):
            try:
                self.wfile.write(BODY[at:at + 64 * 1024])
                self.wfile.flush()
            except (BrokenPipeError, ConnectionAbortedError):
                return              # cancelled — that is the point
            import time
            time.sleep(0.02)

    def log_message(self, *args):
        pass


server = http.server.HTTPServer(("127.0.0.1", 0), Slow)
threading.Thread(target=server.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{server.server_address[1]}/model.bin"

room = tempfile.mkdtemp(prefix="rina-models-")
try:
    print("=== скачивание отчитывается о ходе ===")
    seen = []
    early = []
    target = os.path.join(room, "model.bin")

    def note(p):
        seen.append((p.done, p.total))
        # Whether the final name exists **while** it is still downloading.
        # Asked here and nowhere else: after the fact both a careful
        # download and a careless one look the same, and the promise is
        # about the middle — a half-written file under the real name is
        # found by the next run and used as though it were whole.
        if 0 < p.done < p.total:
            early.append(os.path.exists(target))

    models.fetch(URL, target, name="проверочная", on_progress=note)

    check("файл на месте", os.path.isfile(target),
          f"| {os.path.getsize(target) if os.path.isfile(target) else 0} Б")
    check("размер сказан заранее", seen and seen[0][1] == len(BODY),
          f"| {seen[0] if seen else '—'}")
    check("о ходе сообщили не один раз", len(seen) > 3, f"| {len(seen)} раз")
    check("и дошли до конца", seen[-1][0] == len(BODY), f"| {seen[-1]}")
    check("доля растёт, а не скачет",
          all(a[0] <= b[0] for a, b in zip(seen, seen[1:])))
    check("под настоящим именем ничего не лежит, пока не дописано",
          early and not any(early), f"| замеров {len(early)}")

    print()
    print("=== отмена останавливает и не оставляет следов ===")
    os.remove(target)
    stop = threading.Event()
    # Stopped part-way: after the first pieces, while there is plainly more
    # to come. Cancelling a download that has already finished proves
    # nothing.
    def halt(p):
        if p.done > 128 * 1024:
            stop.set()

    stopped = False
    try:
        models.fetch(URL, target, on_progress=halt, stop=stop)
    except models.Cancelled:
        stopped = True

    check("отмена сработала", stopped)
    check("готового файла не появилось", not os.path.exists(target))
    check("и недокачанного тоже", not os.path.exists(target + ".part"),
          f"| {os.listdir(room)}")

    print()
    print("=== сорванная связь тоже ничего не оставляет ===")
    broken = os.path.join(room, "nowhere.bin")
    fell = False
    try:
        models.fetch("http://127.0.0.1:1/nothing", broken)
    except models.Cancelled:
        fell = False
    except Exception:
        fell = True
    check("ошибка сети доходит до вызвавшего", fell)
    check("и мусора не осталось", not os.path.exists(broken + ".part"))
finally:
    server.shutdown()
    shutil.rmtree(room, ignore_errors=True)

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
