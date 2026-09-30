# -*- coding: utf-8 -*-
"""
B08: доступность возможностей спрашивается только через интерфейс.

Критерий приёмки — «в коде нет ни одной проверки доступности мимо этого
интерфейса» — проверяется буквально: обходом исходников.
"""
import io
import os
import re
import sys

ROOT = r"C:\DevStation\PCDev\DesktopApps\RinaAssistant"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from core.features import (COMMUNITY, FEATURES, CommunityFeatures,
                           FeatureProvider, LimitedFeatures, UnknownFeature,
                           default_features)

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


print("=== чистота ===")
check("Qt не загружен", "PySide6" not in sys.modules)
check("настройки не загружены", "core.settings_store" not in sys.modules)

print()
print("=== бесплатный план ===")
free = CommunityFeatures()
check("удовлетворяет протоколу", isinstance(free, FeatureProvider))
check("план назван", free.plan() == COMMUNITY, f"| {free.plan()}")
check("в бете доступно всё",
      all(free.has_feature(f) for f in FEATURES), f"| {len(FEATURES)} шт.")
check("список совпадает со словарём",
      free.enabled_features() == set(FEATURES))

print()
print("=== опечатка не выглядит отказом ===")
try:
    free.has_feature("agent")           # правильное имя — agents
    check("неизвестное имя отклонено", False)
except UnknownFeature as e:
    check("неизвестное имя отклонено", True, f"| {e}")

print()
print("=== ограниченный план ===")
limited = LimitedFeatures(allowed=("rag",), plan_name="pro")
check("разрешённое доступно", limited.has_feature("rag"))
check("остальное — нет", not limited.has_feature("agents"))
check("план назван", limited.plan() == "pro")
try:
    LimitedFeatures(allowed=("выдумка",))
    check("опечатка в наборе отклонена", False)
except UnknownFeature:
    check("опечатка в наборе отклонена", True)

print()
print("=== ядро отдаёт провайдера ===")
from core.engine import RinaEngine
from core.events import EventBus
from core.settings_api import MemorySettings

engine = RinaEngine(event_bus=EventBus(), settings=MemorySettings())
check("по умолчанию бесплатный план",
      engine.features.plan() == COMMUNITY)
custom = RinaEngine(event_bus=EventBus(), settings=MemorySettings(),
                    features=limited)
check("провайдера можно подставить", custom.features is limited)
check("подставленный решает", not custom.features.has_feature("agents"))

print()
print("=== критерий приёмки: проверок мимо интерфейса нет ===")
# Ищем самодельные проверки плана и лицензии по всему коду приложения.
SUSPECT = re.compile(
    r"""(plan\s*==|==\s*["']pro["']|is_pro|is_premium|licen[sc]e_ok"""
    r"""|has_licen[sc]e|tier\s*==)""", re.I)
SKIP_DIRS = {"venv", "venv (3.14)", ".git", "__pycache__", "build", "dist",
             "out", ".impeccable", "tools", "docs"}

offenders = []
for base, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for name in files:
        if not name.endswith(".py") or name == "features.py":
            continue
        path = os.path.join(base, name)
        for i, line in enumerate(io.open(path, encoding="utf-8",
                                         errors="replace"), 1):
            if line.lstrip().startswith("#"):
                continue
            if SUSPECT.search(line):
                offenders.append(f"{os.path.relpath(path, ROOT)}:{i}")

check("самодельных проверок плана нет", not offenders, f"| {offenders}")

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
