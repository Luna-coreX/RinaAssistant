# -*- coding: utf-8 -*-
"""
4.0b-A14: downloadable models — the catalogue, the transfer, and stopping it.

Checked against a **local** server rather than the real one. A check that
downloads forty-six megabytes from the internet is a check that fails on a
train and passes at a desk, and it would be measuring somebody else's
uptime rather than our code.

What is genuinely ours and worth checking: that progress is reported as
bytes arrive, that cancelling stops the transfer and leaves nothing
half-written behind, that a failure is reported rather than swallowed, and
that a finished model points the setting at the folder the engine wants.
"""
import http.server
import io
import os
import shutil
import sys
import threading
import time
import zipfile

sys.path.insert(0, r"C:\DevStation\PCDev\DesktopApps\RinaAssistant")

from core import models
from core.settings_api import MemorySettings

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


# --- a model archive and a server to serve it slowly ----------------------
# Two megabytes: the downloader reads in blocks of a quarter, and a
# fixture smaller than a few blocks cannot show whether progress is
# reported along the way or only at the end.
def make_archive(inner_name="the-model", padding=2_000_000):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr(f"{inner_name}/README", "a model, honestly")
        zipped.writestr(f"{inner_name}/weights.bin", b"\0" * padding)
    return buffer.getvalue()


ARCHIVE = make_archive()


class Slowly(http.server.BaseHTTPRequestHandler):
    """Serves the archive in dribs, so a cancel has something to stop."""

    def do_GET(self):
        if self.path == "/missing.zip":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(ARCHIVE)))
        self.end_headers()
        for at in range(0, len(ARCHIVE), 16 * 1024):
            try:
                self.wfile.write(ARCHIVE[at:at + 16 * 1024])
                self.wfile.flush()
            except Exception:                           # noqa: BLE001
                return                                  # the other side left
            time.sleep(0.02)

    def log_message(self, *_args):
        pass


server = http.server.HTTPServer(("127.0.0.1", 0), Slowly)
threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{server.server_address[1]}"


def fetch_of(url, model_id="probe", setting="vosk_model"):
    model = models.Model(model_id, "Проба", "vosk", size=len(ARCHIVE),
                         url=url, setting=setting)
    return model


def clean(model_id):
    where = os.path.join(models.models_dir(), model_id)
    if os.path.isdir(where):
        shutil.rmtree(where, ignore_errors=True)
    part = where + ".part"
    if os.path.exists(part):
        os.remove(part)


print("=== каталог ===")
listed = models.catalogue()
check("каталог не пуст", len(listed) > 0, f"| записей {len(listed)}")
check("у всего есть размер", all(m["size"] > 0 for m in listed))
check("наше и чужое различимо",
      any(m["ours"] for m in listed) and any(not m["ours"] for m in listed),
      "| " + ", ".join(f"{m['id']}:{'наше' if m['ours'] else 'движка'}"
                       for m in listed))
check("модель находится по имени",
      models.find(listed[0]["id"]) is not None and models.find("нет") is None)

print()
print("=== скачивание ===")
clean("probe")
store = MemorySettings({})
seen = []
fetch = models.Fetch(fetch_of(f"{BASE}/model.zip"), on_progress=seen.append,
                     settings=store).start()
for _ in range(300):
    if seen and seen[-1]["state"] in ("ready", "failed"):
        break
    time.sleep(0.05)

check("скачалось", seen and seen[-1]["state"] == "ready",
      f"| {seen[-1] if seen else 'ни одного сообщения'}")
# Progress must be reported *while* it goes, not once at the end: a bar
# that jumps from nothing to done is a bar that was never watched.
middle = [s for s in seen if s["state"] == "downloading" and 0 < s["done"]
          < len(ARCHIVE)]
check("прогресс шёл по дороге, а не одним прыжком", len(middle) >= 2,
      f"| промежуточных сообщений {len(middle)}")
check("байты не превысили обещанного",
      all(s["done"] <= s["total"] for s in seen))
check("настройка указывает на распакованное",
      os.path.isdir(str(store.get("vosk_model", ""))),
      f"| {store.get('vosk_model', '')!r}")
check("внутренняя папка развёрнута, а не её обёртка",
      os.path.isfile(os.path.join(str(store.get("vosk_model", "")), "README")))
check("временный файл убран",
      not os.path.exists(os.path.join(models.models_dir(), "probe.part")))
check("каталог видит установленное",
      models.installed(fetch.model) != "")

print()
print("=== отмена ===")
clean("probe")
store2 = MemorySettings({})
seen2 = []
fetch2 = models.Fetch(fetch_of(f"{BASE}/model.zip"), on_progress=seen2.append,
                      settings=store2).start()
for _ in range(100):
    if seen2 and seen2[-1]["done"] > 0:
        break
    time.sleep(0.02)
fetch2.cancel()
for _ in range(200):
    if seen2 and seen2[-1]["state"] in ("cancelled", "ready", "failed"):
        break
    time.sleep(0.05)

# By bytes, not by the word "cancelled". The first version of this check
# asserted the state, and it stayed green when the stop flag was taken out
# of the reading loop entirely: the whole file came down and *then* the
# transfer announced itself as cancelled. A check on an announcement passes
# for anything that announces.
check("отмена останавливает, а не доводит до конца",
      seen2 and seen2[-1]["state"] == "cancelled"
      and fetch2.done < len(ARCHIVE),
      f"| состояние {seen2[-1]['state'] if seen2 else '—'}, "
      f"взято {fetch2.done} из {len(ARCHIVE)} Б")
check("недокачанное не осталось лежать",
      not os.path.exists(os.path.join(models.models_dir(), "probe.part")))
check("и настройка на него не указывает", not store2.get("vosk_model", ""))

print()
print("=== каталог рассказывает про идущее ===")
# What a window opened **during** a download is told. Without this the
# settings showed a model halfway through fetching as simply "not
# installed", and offered to fetch it a second time.
clean("probe")
probe = fetch_of(f"{BASE}/model.zip")
quiet = models.catalogue()
check("пока ничего не идёт — состояния нет",
      all("state" not in m for m in quiet))

seen4 = []
fetch4 = models.Fetch(probe, on_progress=seen4.append,
                      settings=MemorySettings({})).start()
fetch4.task_id = "task-0007"
for _ in range(100):
    if seen4 and seen4[-1]["done"] > 0:
        break
    time.sleep(0.02)

during = models.catalogue(running={m["id"]: fetch4 for m in models.catalogue()})
check("идущее видно на каждой записи",
      all(m.get("state") for m in during),
      f"| {[m.get('state') for m in during]}")
check("и номер задачи, чтобы было что останавливать",
      all(m.get("task_id") == "task-0007" for m in during))
check("с байтами, а не с процентами",
      all(m.get("total", 0) > 0 for m in during))
fetch4.cancel()
for _ in range(100):
    if seen4 and seen4[-1]["state"] == "cancelled":
        break
    time.sleep(0.05)
clean("probe")

print()
print("=== неудача ===")
clean("probe")
seen3 = []
models.Fetch(fetch_of(f"{BASE}/missing.zip"), on_progress=seen3.append,
             settings=MemorySettings({})).start()
for _ in range(200):
    if seen3 and seen3[-1]["state"] in ("failed", "ready"):
        break
    time.sleep(0.05)
check("о неудаче сообщено, а не проглочено",
      seen3 and seen3[-1]["state"] == "failed",
      f"| {seen3[-1].get('error', '')[:50] if seen3 else '—'}")
check("и причина названа", seen3 and seen3[-1]["error"] != "")

clean("probe")
server.shutdown()

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
