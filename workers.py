"""Многопоточна обработка на пратки.

ВАЖНО: нишките НЕ пипат SQLite. Те само симулират работа и връщат
резултат. Записът в базата се прави след join()/map() в главната нишка
(main.py), последователно - така няма 'database is locked'.

start() -> пуска нова нишка, която извиква run()
run() -> кодът, който се изпълнява в нишката (не се вика директно)
join() -> главната нишка чака нишката да приключи
"""

from __future__ import annotations

import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from shipments import (
    FINAL_STATUSES,
    INTRANSIT_STATUSES,
    ValidationError,
    clean,
    validate_status,
)

# ---------------------------------------------------------------- настройки

MAX_WORKERS = 3
DELAY_RANGE = (1, 4)  # сек. симулирано чакане
LOG_FILE = "delivery_tracking.log"

_print_lock = threading.Lock()  # без него редовете от нишките се смесват
_log_lock = threading.Lock()


def get_logger(name: str = "delivery_tracking", log_file: str = LOG_FILE):
    """Един логер за целия проект (main.py и database.py също го ползват)."""
    logger = logging.getLogger(name)
    with _log_lock:
        if not logger.handlers:
            logger.setLevel(logging.INFO)
            logger.propagate = False
            try:
                handler = logging.FileHandler(log_file, encoding="utf-8")
            except OSError:
                handler = logging.StreamHandler()  # ако файлът не може да се пише
            handler.setFormatter(
                logging.Formatter("%(asctime)s | %(levelname)s | %(threadName)s | %(message)s")
            )
            logger.addHandler(handler)
    return logger


log = get_logger()


def safe_print(*args, **kwargs) -> None:
    """print от нишка - под ключалка, за да не се разбърква изходът."""
    with _print_lock:
        print(*args, **kwargs)


# ---------------------------------------------------------------- резултат

class ProcessResult:
    """Резултат от една обработена пратка.

    Разопакова се и като кортеж:  tracking_number, new_status = result
    """

    __slots__ = ("tracking_number", "new_status", "ok", "error", "seconds")

    def __init__(self, tracking_number, new_status=None, ok=True, error=None, seconds=0.0):
        self.tracking_number = clean(tracking_number)
        self.new_status = new_status
        self.ok = bool(ok)
        self.error = error
        self.seconds = round(float(seconds), 2)

    def __iter__(self):
        yield self.tracking_number
        yield self.new_status

    def format_line(self) -> str:
        if self.ok:
            return (
                f"[OK]    {self.tracking_number} -> {self.new_status} "
                f"({self.seconds:g} сек.)"
            )
        return f"[ГРЕШКА] {self.tracking_number or '(без номер)'}: {self.error}"

    def __repr__(self) -> str:
        state = self.new_status if self.ok else f"ГРЕШКА: {self.error}"
        return f"<ProcessResult {self.tracking_number} {state}>"


# ---------------------------------------------------------------- логика

def _field(obj, name):
    """Чете поле от Shipment, dict или sqlite3.Row - без да гърми."""
    if hasattr(obj, name):
        return getattr(obj, name)
    try:
        return obj[name]
    except (TypeError, KeyError, IndexError):
        return None


def pick_next_status(current_status) -> str:
    """Случаен нов статус от списъка 'в движение'.

    Крайните статуси НЕ се променят. Обратно - нишките никога не задават
    краен статус: приключването на пратка е ръчно действие (меню 4).
    """
    current = clean(current_status)
    if current in FINAL_STATUSES:
        return current
    options = [s for s in INTRANSIT_STATUSES if s != current]
    return random.choice(options or list(INTRANSIT_STATUSES))


def process_shipment(shipment, delay_range=DELAY_RANGE, simulate: bool = True) -> ProcessResult:
    """Обработва ЕДНА пратка в нишка. Никога не хвърля - връща ProcessResult."""
    started = time.monotonic()
    tracking_number = clean(_field(shipment, "tracking_number"))
    try:
        if not tracking_number:
            raise ValidationError("Липсва номер за проследяване.")
        if simulate:
            low, high = int(delay_range[0]), int(delay_range[1])
            delay = random.randint(min(low, high), max(low, high))
            safe_print(f"   [{threading.current_thread().name}] {tracking_number}: старт ({delay} сек.)")
            time.sleep(delay)
            safe_print(f"   [{threading.current_thread().name}] {tracking_number}: готово")
        new_status = validate_status(pick_next_status(_field(shipment, "current_status")))
        elapsed = time.monotonic() - started
        log.info("Обработена %s -> %s за %.2f сек.", tracking_number, new_status, elapsed)
        return ProcessResult(tracking_number, new_status, True, None, elapsed)
    except Exception as error:  # нишка не бива да умира тихо
        elapsed = time.monotonic() - started
        log.error("Грешка при %s: %s", tracking_number or "?", error)
        return ProcessResult(tracking_number, None, False, str(error), elapsed)


# ---------------------------------------------------------------- вариант 1

def process_batch(
    shipments,
    max_workers: int = MAX_WORKERS,
    delay_range=DELAY_RANGE,
    simulate: bool = True,
) -> list[ProcessResult]:
    """ThreadPoolExecutor.

    Връща резултатите В СЪЩИЯ РЕД като входа (executor.map пази реда).
    """
    items = list(shipments)
    if not items:
        return []
    workers = max(1, min(int(max_workers), len(items)))
    job = partial(process_shipment, delay_range=delay_range, simulate=simulate)
    log.info("Старт на обработка (pool): %d пратки, %d нишки", len(items), workers)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(job, items))
    log.info("Край на обработката: %d резултата", len(results))
    return results


# ---------------------------------------------------------------- вариант 2

class ShipmentWorker(threading.Thread):
    """Допустимият вариант: собствен клас, наследяващ Thread."""

    def __init__(self, shipment, delay_range=DELAY_RANGE, simulate: bool = True):
        super().__init__(daemon=True)
        self.shipment = shipment
        self.delay_range = delay_range
        self.simulate = simulate
        self.result: ProcessResult | None = None

    def run(self) -> None:
        # изпълнява се в нишката; резултатът се чете след join()
        self.result = process_shipment(self.shipment, self.delay_range, self.simulate)


def process_batch_threads(
    shipments,
    delay_range=DELAY_RANGE,
    simulate: bool = True,
) -> list[ProcessResult]:
    """Същото като process_batch, но с ShipmentWorker (start/join)."""
    items = list(shipments)
    if not items:
        return []
    log.info("Старт на обработка (Thread): %d пратки", len(items))
    workers = [ShipmentWorker(s, delay_range, simulate) for s in items]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    log.info("Край на обработката (Thread): %d резултата", len(workers))
    return [
        w.result
        if w.result is not None
        else ProcessResult(_field(w.shipment, "tracking_number"), None, False, "Нишката не върна резултат.")
        for w in workers
    ]


# ---------------------------------------------------------------- обобщение

def summarize(results) -> dict:
    items = list(results)
    ok = [r for r in items if r.ok]
    return {
        "total": len(items),
        "ok": len(ok),
        "failed": len(items) - len(ok),
        "seconds": round(max((r.seconds for r in items), default=0.0), 2),
    }


def format_results(results) -> str:
    items = list(results)
    if not items:
        return "Няма пратки за обработка."
    stats = summarize(items)
    lines = [r.format_line() for r in items]
    lines.append(
        f"Готово: {stats['ok']} успешни, {stats['failed']} с грешка "
        f"(най-дълга задача: {stats['seconds']:g} сек.)"
    )
    return "\n".join(lines)


if __name__ == "__main__":
    # бърза проверка без БД: python workers.py
    from shipments import Shipment

    demo = [
        Shipment.create("ZIP1001", "Иван", "Мария", "София", "Варна", 2.5),
        Shipment.create("ZIP1002", "Петър", "Елена", "Пловдив", "Бургас", 1.2),
        Shipment.create("ZIP1003", "Георги", "Анна", "Русе", "Стара Загора", 4),
    ]
    print(format_results(process_batch(demo, simulate=False)))
    print(format_results(process_batch_threads(demo, simulate=False)))