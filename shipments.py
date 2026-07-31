"""Домейн слой: модел Shipment + валидации + формат.

Тук НЯМА изпълнение на SQL и НЯМА нишки. Има само чиста логика и
няколко безопасни SQL *фрагмента* (ORDER BY / WHERE), които се строят
единствено от бял списък - така database.py, workers.py и main.py
ползват едни и същи правила.
"""

from __future__ import annotations  # позволява 'str | None' и на Python 3.8/3.9

import math
import re
from datetime import datetime

# ---------------------------------------------------------------- константи

TS_FMT = "%Y-%m-%d %H:%M:%S"

STATUS_REGISTERED = "Регистрирана"
STATUS_OFFICE = "Приета в офис"
STATUS_PROCESSING = "В процес на обработка"
STATUS_TRANSIT = "Транспортира се"
STATUS_HUB = "Пристигнала в център"
STATUS_COURIER = "Предадена на куриер"
STATUS_DELIVERED = "Доставена"
STATUS_FAILED = "Неуспешна доставка"

# tuple
STATUSES = (
    STATUS_REGISTERED,
    STATUS_OFFICE,
    STATUS_PROCESSING,
    STATUS_TRANSIT,
    STATUS_HUB,
    STATUS_COURIER,
    STATUS_DELIVERED,
    STATUS_FAILED,
)

# крайни статуси - пратката не се обработва повече от нишките
FINAL_STATUSES = (STATUS_DELIVERED, STATUS_FAILED)

# статуси, които нишките могат да задават при симулация
INTRANSIT_STATUSES = (
    STATUS_PROCESSING,
    STATUS_TRANSIT,
    STATUS_HUB,
    STATUS_COURIER,
)

# ред на колоните в таблица shipments - database.py да ползва това
COLUMNS = (
    "id",
    "tracking_number",
    "sender_name",
    "recipient_name",
    "origin_city",
    "destination_city",
    "weight",
    "current_status",
    "status_history",
    "created_at",
)
INSERT_COLUMNS = COLUMNS[1:]  # без id (AUTOINCREMENT)

# колони, които потребителят има право да редактира (меню 10)
EDITABLE_COLUMNS = (
    "sender_name",
    "recipient_name",
    "origin_city",
    "destination_city",
    "weight",
)

# полета, по които е разрешено сортиране (ORDER BY не приема параметри,
# затова се ползва whitelist - иначе има риск от SQL injection)
SORT_FIELDS = {
    "тегло": "weight",
    "weight": "weight",
    "дата": "created_at",
    "date": "created_at",
    "град": "destination_city",
    "city": "destination_city",
    "номер": "tracking_number",
    "статус": "current_status",
}

# подредено меню за сортиране (ключ, надпис) - ползва се от main.py
SORT_MENU = (
    ("тегло", "Тегло"),
    ("дата", "Дата на създаване"),
    ("град", "Краен град"),
    ("номер", "Номер за проследяване"),
    ("статус", "Текущ статус"),
)

# полета за текстово търсене (LIKE) - също whitelist
SEARCH_FIELDS = {
    "подател": "sender_name",
    "получател": "recipient_name",
    "начален град": "origin_city",
    "краен град": "destination_city",
    "град": "destination_city",
}

SEARCH_MENU = (
    ("подател", "Подател"),
    ("получател", "Получател"),
    ("начален град", "Начален град"),
    ("краен град", "Краен град"),
)

TRACKING_PREFIX = "ZIP"
TRACKING_START = 1001
# Валидиране на тракинг ид-та: 3-20 символа; главни латински букви,
# цифри, underscore и тире. (Точка НЕ се допуска.)
TRACKING_RE = re.compile(r"^[A-Z0-9_-]{3,20}$")
_AUTO_RE = re.compile(r"^" + TRACKING_PREFIX + r"(\d+)$")

MIN_WEIGHT = 0.001
MAX_WEIGHT = 1000.0
MAX_TEXT = 60


class ValidationError(Exception):
    """Грешка от невалидни потр. данни. main.py трябва да я хваща и печата съобщение."""


# -------------------------------- помощни --------------------

def now_ts() -> str:
    return datetime.now().strftime(TS_FMT)


def clean(value) -> str:
    """None -> "", маха излишни интервали и нови редове."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def validate_text(value, label: str, min_len: int = 2) -> str:
    v = clean(value)
    if not v:
        raise ValidationError(f"Липсва стойност за: {label}.")
    if len(v) < min_len:
        raise ValidationError(f"{label}: минимум {min_len} символа.")
    if len(v) > MAX_TEXT:
        raise ValidationError(f"{label}: максимум {MAX_TEXT} символа.")
    if not any(ch.isalpha() for ch in v):
        raise ValidationError(f"{label}: трябва да съдържа букви.")
    return v


def validate_tracking_number(value) -> str:
    v = clean(value).upper()
    if not v:
        raise ValidationError("Номерът за проследяване не може да е празен.")
    if not TRACKING_RE.match(v):
        raise ValidationError(
            "Номерът може да съдържа само букви, цифри, - и _ (3-20 символа)."
        )
    return v


def parse_weight(value) -> float:
    """Приема '2,5', '2.5', 2.5 -> float. Хвърля ValidationError при боклук."""
    if isinstance(value, bool):
        raise ValidationError("Теглото трябва да е число.")
    if isinstance(value, (int, float)):
        w = float(value)
    else:
        raw = clean(value).replace(",", ".")
        if not raw:
            raise ValidationError("Теглото не може да е празно.")
        try:
            w = float(raw)
        except (TypeError, ValueError):
            raise ValidationError("Теглото трябва да е число.") from None
    if math.isnan(w) or math.isinf(w):
        raise ValidationError("Теглото трябва да е реално число.")
    if w <= 0:
        raise ValidationError("Теглото трябва да е положително число.")
    if w < MIN_WEIGHT:
        raise ValidationError(f"Теглото трябва да е поне {MIN_WEIGHT} kg.")
    if w > MAX_WEIGHT:
        raise ValidationError(f"Теглото не може да е над {MAX_WEIGHT:g} kg.")
    return round(w, 3)


def parse_min_weight(value) -> float:
    """Като parse_weight, но за филтър 'поне X kg' - тук 0 е допустимо."""
    raw = clean(value).replace(",", ".")
    if not raw:
        raise ValidationError("Минималното тегло не може да е празно.")
    try:
        w = float(raw)
    except (TypeError, ValueError):
        raise ValidationError("Минималното тегло трябва да е число.") from None
    if math.isnan(w) or math.isinf(w):
        raise ValidationError("Минималното тегло трябва да е реално число.")
    if w < 0:
        raise ValidationError("Минималното тегло не може да е отрицателно.")
    if w > MAX_WEIGHT:
        raise ValidationError(f"Минималното тегло не може да е над {MAX_WEIGHT:g} kg.")
    return round(w, 3)


def validate_status(value) -> str:
    v = clean(value)
    if not v:
        raise ValidationError("Статусът не може да е празен.")
    if v not in STATUSES:
        raise ValidationError(f"Непознат статус: {v}")
    return v


def choice_index(choice, count: int) -> int:
    """'3' -> 3, с проверка за диапазон 1..count. Общо за всички менюта."""
    raw = clean(choice)
    if not raw.isdigit():
        raise ValidationError("Моля, въведете валидно число.")
    idx = int(raw)
    if not 1 <= idx <= count:
        raise ValidationError(f"Изберете число от 1 до {count}.")
    return idx


def status_by_index(choice) -> str:
    """Меню избор 1..len(STATUSES) -> статус."""
    return STATUSES[choice_index(choice, len(STATUSES)) - 1]


def sort_key_by_index(choice) -> str:
    """Меню избор 1..len(SORT_MENU) -> ключ за build_order_by()."""
    return SORT_MENU[choice_index(choice, len(SORT_MENU)) - 1][0]


def search_field_by_index(choice) -> str:
    """Меню избор 1..len(SEARCH_MENU) -> ключ за resolve_search_field()."""
    return SEARCH_MENU[choice_index(choice, len(SEARCH_MENU)) - 1][0]


def resolve_search_field(field) -> str:
    """Ключ на български -> име на колона. Непознато поле = грешка, НЕ тихо
    връщане към 'краен град' (иначе потребителят вижда грешни резултати)."""
    key = clean(field).lower()
    column = SEARCH_FIELDS.get(key)
    if column is None:
        raise ValidationError(
            "Търсене е възможно по: " + ", ".join(sorted(SEARCH_FIELDS))
        )
    return column


# -------------------------------- история -----------------------

def history_entry(status: str, changed_at: str | None = None) -> str:
    return f"{changed_at or now_ts()} - {status}"


def append_history(old_history, status: str, changed_at: str | None = None) -> str:
    """Връща новия текст за колона status_history (стар + нов ред)."""
    entry = history_entry(status, changed_at)
    old = (old_history or "").strip()
    return f"{old}\n{entry}" if old else entry


def parse_history(text) -> list[tuple[str, str]]:
    """Текст -> [(дата, статус), ...]. Толерира повредени редове."""
    rows = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        ts, sep, status = line.partition(" - ")
        rows.append((ts.strip(), status.strip()) if sep else ("", line))
    return rows


# ---------------------------------------------------------------- номера

def next_tracking_number(existing=()) -> str:
    """Авт. номер: най-големият ZIPnnnn + 1. existing = всички номера от БД."""
    top = TRACKING_START - 1
    for num in existing:
        m = _AUTO_RE.match(clean(num).upper())
        if m:
            try:
                top = max(top, int(m.group(1)))
            except ValueError:
                continue
    return f"{TRACKING_PREFIX}{max(top + 1, TRACKING_START)}"


# ---------------------------------------------------------------- заявки

def pylower(value):
    """SQLite LOWER() не работи с кирилица - тази ф-я се регистрира в БД:
    conn.create_function("PYLOWER", 1, shipments.pylower)"""
    return value.lower() if isinstance(value, str) else value


def like_pattern(term) -> str:
    """'рус' -> '%рус%' с екраниран % и _ (ползва се с ESCAPE '\\')."""
    raw = clean(term)
    if not raw:
        raise ValidationError("Търсената дума не може да е празна.")
    escaped = raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def build_order_by(field, descending: bool = False) -> str:
    """Безопасен ORDER BY фрагмент (само от белия списък SORT_FIELDS)."""
    key = clean(field).lower()
    column = SORT_FIELDS.get(key)
    if column is None:
        raise ValidationError(
            "Сортиране е възможно по: " + ", ".join(sorted(set(SORT_FIELDS)))
        )
    return f"ORDER BY {column} {'DESC' if descending else 'ASC'}"


def build_filter(status=None, city=None, min_weight=None) -> tuple[str, tuple]:
    """Безопасен WHERE фрагмент + параметри за филтриране.

    Върнатият SQL съдържа САМО '?' плейсхолдъри - никакви потребителски
    стойности не се лепят в текста на заявката.
    Градът се търси и в началния, и в крайния град.
    """
    clauses = []
    params: list = []

    if clean(status):
        clauses.append("current_status = ?")
        params.append(validate_status(status))

    if clean(city):
        pattern = like_pattern(city)
        clauses.append(
            "(PYLOWER(origin_city) LIKE PYLOWER(?) ESCAPE '\\' "
            "OR PYLOWER(destination_city) LIKE PYLOWER(?) ESCAPE '\\')"
        )
        params.append(pattern)
        params.append(pattern)

    if clean(min_weight):
        clauses.append("weight >= ?")
        params.append(parse_min_weight(min_weight))

    if not clauses:
        raise ValidationError("Не е зададен нито един филтър.")

    return "WHERE " + " AND ".join(clauses), tuple(params)


# ---------------------------------------------------------------- модел

class Shipment:
    """Една пратка. Стойностите се валидират при създаване и при промяна."""

    def __init__(
        self,
        tracking_number,
        sender_name,
        recipient_name,
        origin_city,
        destination_city,
        weight,
        current_status=STATUS_REGISTERED,
        status_history="",
        created_at=None,
        shipment_id=None,
        strict=True,
    ):
        if strict:
            self.tracking_number = validate_tracking_number(tracking_number)
            self.sender_name = validate_text(sender_name, "Име на подател")
            self.recipient_name = validate_text(recipient_name, "Име на получател")
            self.origin_city = validate_text(origin_city, "Начален град")
            self.destination_city = validate_text(destination_city, "Краен град")
            self.weight = parse_weight(weight)
            self.current_status = validate_status(current_status or STATUS_REGISTERED)
        else:
            # strict=False само за редове, идващи от БД (вече валидирани)
            self.tracking_number = clean(tracking_number).upper()
            self.sender_name = clean(sender_name)
            self.recipient_name = clean(recipient_name)
            self.origin_city = clean(origin_city)
            self.destination_city = clean(destination_city)
            try:
                self.weight = float(weight)
            except (TypeError, ValueError):
                self.weight = 0.0
            self.current_status = clean(current_status) or STATUS_REGISTERED
        self.status_history = status_history or ""
        self.created_at = clean(created_at) or now_ts()
        self.id = shipment_id

    # --- фабрики ---

    @classmethod
    def create(
        cls,
        tracking_number,
        sender_name,
        recipient_name,
        origin_city,
        destination_city,
        weight,
    ) -> "Shipment":
        """Нова пратка: статус Регистрирана + първи ред в историята."""
        ts = now_ts()
        obj = cls(
            tracking_number,
            sender_name,
            recipient_name,
            origin_city,
            destination_city,
            weight,
            current_status=STATUS_REGISTERED,
            status_history="",
            created_at=ts,
        )
        obj.status_history = append_history("", STATUS_REGISTERED, ts)
        return obj

    @classmethod
    def from_row(cls, row) -> "Shipment":
        """sqlite3.Row / dict / tuple -> Shipment (в реда на COLUMNS)."""
        if row is None:
            raise ValidationError("Няма данни за пратка.")
        if isinstance(row, (tuple, list)):
            if len(row) != len(COLUMNS):
                raise ValidationError(
                    f"Очаквани {len(COLUMNS)} колони, получени {len(row)}."
                )
            data = dict(zip(COLUMNS, row))
        else:
            data = {c: row[c] for c in COLUMNS}
        return cls(
            data["tracking_number"],
            data["sender_name"],
            data["recipient_name"],
            data["origin_city"],
            data["destination_city"],
            data["weight"],
            current_status=data["current_status"],
            status_history=data["status_history"],
            created_at=data["created_at"],
            shipment_id=data["id"],
            strict=False,
        )

    # --- промени ---

    def set_status(self, new_status, changed_at: str | None = None) -> str:
        """Валидира, сменя статуса и добавя ред в историята. Връща реда."""
        status = validate_status(new_status)
        ts = clean(changed_at) or now_ts()
        self.current_status = status
        self.status_history = append_history(self.status_history, status, ts)
        return history_entry(status, ts)

    def update_details(
        self,
        sender_name=None,
        recipient_name=None,
        origin_city=None,
        destination_city=None,
        weight=None,
    ) -> dict:
        """Редакция. Празна стойност = без промяна. Връща {колона: нова ст-ст}."""
        changes: dict = {}
        if clean(sender_name):
            changes["sender_name"] = validate_text(sender_name, "Име на подател")
        if clean(recipient_name):
            changes["recipient_name"] = validate_text(
                recipient_name, "Име на получател"
            )
        if clean(origin_city):
            changes["origin_city"] = validate_text(origin_city, "Начален град")
        if clean(destination_city):
            changes["destination_city"] = validate_text(
                destination_city, "Краен град"
            )
        if clean(weight):
            changes["weight"] = parse_weight(weight)
        if not changes:
            raise ValidationError("Няма въведени промени.")
        for key, value in changes.items():
            setattr(self, key, value)
        return changes

    # --- четене ---

    @property
    def is_final(self) -> bool:
        return self.current_status in FINAL_STATUSES

    def history_lines(self) -> list[tuple[str, str]]:
        return parse_history(self.status_history)

    def to_dict(self) -> dict:
        return {c: getattr(self, c) for c in COLUMNS}

    def to_insert_params(self) -> tuple:
        """Кортеж за INSERT в реда на INSERT_COLUMNS."""
        return tuple(getattr(self, c) for c in INSERT_COLUMNS)

    def copy(self) -> "Shipment":
        return Shipment.from_row(tuple(self.to_dict()[c] for c in COLUMNS))

    def format_short(self) -> str:
        # ZIP1005 | София -> Варна | 2.5 kg | Транспортира се
        return (
            f"{self.tracking_number} | {self.origin_city} -> "
            f"{self.destination_city} | {self.weight:g} kg | {self.current_status}"
        )

    def format_full(self) -> str:
        lines = [
            f"Номер:      {self.tracking_number}",
            f"Подател:    {self.sender_name}",
            f"Получател:  {self.recipient_name}",
            f"Маршрут:    {self.origin_city} -> {self.destination_city}",
            f"Тегло:      {self.weight:g} kg",
            f"Статус:     {self.current_status}",
            f"Създадена:  {self.created_at}",
        ]
        return "\n".join(lines)

    def format_history(self) -> str:
        rows = self.history_lines()
        if not rows:
            return "Няма записана история."
        return "\n".join(
            f"{i}. {ts} - {st}" if ts else f"{i}. {st}"
            for i, (ts, st) in enumerate(rows, 1)
        )

    def __eq__(self, other) -> bool:
        if not isinstance(other, Shipment):
            return NotImplemented
        return self.tracking_number == other.tracking_number

    def __hash__(self) -> int:
        return hash(self.tracking_number)

    def __repr__(self) -> str:
        # дебъгинг
        return f"<Shipment {self.tracking_number} {self.current_status}>"


# ---------------------------------------------------------------- статистика

def summarize_shipments(items) -> dict:
    """Резервна статистика в Python (основният SQL вариант е в database.py)."""
    items = list(items)
    weights = [s.weight for s in items]
    by_status: dict = {}
    for s in items:
        by_status[s.current_status] = by_status.get(s.current_status, 0) + 1
    return {
        "count": len(items),
        "total_weight": round(sum(weights), 3) if weights else 0.0,
        "avg_weight": round(sum(weights) / len(weights), 3) if weights else 0.0,
        "by_status": by_status,
    }


def format_stats(stats: dict) -> str:
    lines = [
        f"Брой пратки:    {stats['count']}",
        f"Общо тегло:     {stats['total_weight']:g} kg",
        f"Средно тегло:   {stats['avg_weight']:g} kg",
    ]
    by_status = stats.get("by_status") or {}
    if by_status:
        lines.append("По статус:")
        lines.extend(f"  - {k}: {v}" for k, v in by_status.items())
    return "\n".join(lines)