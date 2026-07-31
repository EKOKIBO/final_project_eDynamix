"""SQLite слой. Всички потребителски стойности влизат само през '?'.

Единствените места, където текст се лепи в заявка, са ORDER BY / WHERE
фрагментите и имената на колони - и те идват изключително от белите
списъци в shipments.py (SORT_FIELDS, SEARCH_FIELDS, INSERT_COLUMNS).
"""

import sqlite3

import shipments
from workers import get_logger

DB_NAME = "shipments.db"

log = get_logger()


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.create_function("PYLOWER", 1, shipments.pylower)
    return conn


def create_table():
    query = """
    CREATE TABLE IF NOT EXISTS shipments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tracking_number TEXT UNIQUE NOT NULL,
        sender_name TEXT NOT NULL,
        recipient_name TEXT NOT NULL,
        origin_city TEXT NOT NULL,
        destination_city TEXT NOT NULL,
        weight REAL NOT NULL,
        current_status TEXT NOT NULL,
        status_history TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """
    conn = None
    try:
        conn = get_connection()
        conn.execute(query)
        conn.commit()
    except sqlite3.Error as error:
        log.error("CREATE TABLE: %s", error)
        print("Грешка при създаване на таблицата:", error)
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------- INSERT

def add_shipment(shipment):
    """INSERT. Колоните се вземат от shipments.INSERT_COLUMNS, а стойностите
    от shipment.to_insert_params() - така редът им не може да се разминe."""
    columns_sql = ", ".join(shipments.INSERT_COLUMNS)
    placeholders = ", ".join("?" for _ in shipments.INSERT_COLUMNS)
    query = f"INSERT INTO shipments ({columns_sql}) VALUES ({placeholders});"
    values = shipment.to_insert_params()

    conn = None
    try:
        conn = get_connection()
        conn.execute(query, values)
        conn.commit()
        log.info("Добавена пратка %s", shipment.tracking_number)
        return True
    except sqlite3.IntegrityError:
        log.warning("Дублиран номер: %s", shipment.tracking_number)
        print("Вече съществува пратка с този номер за проследяване.")
        return False
    except sqlite3.Error as error:
        log.error("INSERT %s: %s", shipment.tracking_number, error)
        print("Грешка при работа с базата:", error)
        return False
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------- SELECT

def rows_to_shipments(rows):
    result = []
    for row in rows:
        result.append(shipments.Shipment.from_row(row))
    return result


def _select(query, params=()):
    """Общо изпълнение на SELECT -> списък от Shipment."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        return rows_to_shipments(rows)
    except sqlite3.Error as error:
        log.error("SELECT: %s", error)
        print("Грешка при работа с базата:", error)
        return []
    finally:
        if conn is not None:
            conn.close()


def get_all_shipments(sort_by=None, descending=False):
    """Всички пратки. sort_by е ключ от shipments.SORT_FIELDS (или None).

    При невалиден ключ хвърля ValidationError - main.py я хваща и печата.
    """
    order_sql = "ORDER BY id ASC"
    if sort_by:
        order_sql = shipments.build_order_by(sort_by, descending)
    return _select(f"SELECT * FROM shipments {order_sql};")


def find_shipment_by_tracking(tracking_number):
    query = "SELECT * FROM shipments WHERE tracking_number = ?;"

    conn = None
    try:
        conn = get_connection()
        cursor = conn.execute(query, (shipments.clean(tracking_number).upper(),))
        row = cursor.fetchone()
        if row is None:
            return None
        return shipments.Shipment.from_row(row)
    except sqlite3.Error as error:
        log.error("SELECT by tracking: %s", error)
        print("Грешка при работа с базата:", error)
        return None
    finally:
        if conn is not None:
            conn.close()


def search_shipments(term, field="град", sort_by=None, descending=False):
    """Търсене по дума в едно поле (LIKE, независимо от малки/главни).

    Непознато поле вече НЕ се подменя тихо - resolve_search_field хвърля
    ValidationError и main.py показва списъка с допустимите полета.
    """
    column = shipments.resolve_search_field(field)
    pattern = shipments.like_pattern(term)

    order_sql = "ORDER BY id ASC"
    if sort_by:
        order_sql = shipments.build_order_by(sort_by, descending)

    query = (
        "SELECT * FROM shipments "
        f"WHERE PYLOWER({column}) LIKE PYLOWER(?) ESCAPE '\\' "
        f"{order_sql};"
    )
    return _select(query, (pattern,))


def filter_shipments(status=None, city=None, min_weight=None,
                     sort_by=None, descending=False):
    """Филтриране по статус / град / минимално тегло (комбинирано с AND)."""
    where_sql, params = shipments.build_filter(status, city, min_weight)

    order_sql = "ORDER BY id ASC"
    if sort_by:
        order_sql = shipments.build_order_by(sort_by, descending)

    query = f"SELECT * FROM shipments {where_sql} {order_sql};"
    return _select(query, params)


def get_undelivered_shipments():
    query = """
    SELECT * FROM shipments
    WHERE current_status NOT IN (?, ?);
    """
    return _select(query, shipments.FINAL_STATUSES)


# ---------------------------------------------------------------- UPDATE

def update_status(tracking_number, new_status):
    shipment = find_shipment_by_tracking(tracking_number)
    if shipment is None:
        print("Няма пратка с такъв номер за проследяване.")
        return False

    try:
        shipment.set_status(new_status)
    except shipments.ValidationError as error:
        print(error)
        return False

    query = """
    UPDATE shipments
    SET current_status = ?, status_history = ?
    WHERE tracking_number = ?;
    """

    conn = None
    try:
        conn = get_connection()
        conn.execute(
            query,
            (shipment.current_status, shipment.status_history, shipment.tracking_number),
        )
        conn.commit()
        log.info("Статус %s -> %s", shipment.tracking_number, shipment.current_status)
        return True
    except sqlite3.Error as error:
        log.error("UPDATE status %s: %s", shipment.tracking_number, error)
        print("Грешка при работа с базата:", error)
        return False
    finally:
        if conn is not None:
            conn.close()


def update_shipment(tracking_number, changes):
    """Редакция на данни (меню 10). changes = {колона: нова стойност}.

    Имената на колоните минават през whitelist, стойностите - през '?'.
    """
    if not changes:
        raise shipments.ValidationError("Няма въведени промени.")
    for column in changes:
        if column not in shipments.EDITABLE_COLUMNS:
            raise shipments.ValidationError(f"Непозволена за редакция колона: {column}")

    set_sql = ", ".join(f"{c} = ?" for c in changes)
    query = f"UPDATE shipments SET {set_sql} WHERE tracking_number = ?;"
    values = tuple(changes.values()) + (shipments.clean(tracking_number).upper(),)

    conn = None
    try:
        conn = get_connection()
        cursor = conn.execute(query, values)
        conn.commit()
        log.info("Редактирана %s: %s", tracking_number, ", ".join(changes))
        return cursor.rowcount > 0
    except sqlite3.Error as error:
        log.error("UPDATE details %s: %s", tracking_number, error)
        print("Грешка при работа с базата:", error)
        return False
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------- DELETE

def delete_shipment(tracking_number):
    query = "DELETE FROM shipments WHERE tracking_number = ?;"

    conn = None
    try:
        conn = get_connection()
        cursor = conn.execute(query, (shipments.clean(tracking_number).upper(),))
        conn.commit()
        log.info("Изтрита пратка %s", shipments.clean(tracking_number).upper())
        return cursor.rowcount > 0
    except sqlite3.Error as error:
        log.error("DELETE %s: %s", tracking_number, error)
        print("Грешка при работа с базата:", error)
        return False
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------- нишки -> БД

def apply_results(results):
    """Записва резултатите от нишките ПОСЛЕДОВАТЕЛНО, в главната нишка."""
    failed = []
    for result in results:
        if not result.ok:
            failed.append(result.tracking_number)
            continue
        success = update_status(result.tracking_number, result.new_status)
        if not success:
            failed.append(result.tracking_number)
    return failed


# ---------------------------------------------------------------- статистика

def get_statistics():
    """COUNT / SUM / AVG + разбивка по статус - всичко от SQL."""
    totals_query = (
        "SELECT COUNT(*), COALESCE(SUM(weight), 0), COALESCE(AVG(weight), 0) "
        "FROM shipments;"
    )
    by_status_query = (
        "SELECT current_status, COUNT(*) FROM shipments "
        "GROUP BY current_status ORDER BY COUNT(*) DESC;"
    )

    conn = None
    try:
        conn = get_connection()
        count, total_weight, avg_weight = conn.execute(totals_query).fetchone()
        by_status = {}
        for status, number in conn.execute(by_status_query).fetchall():
            by_status[status] = number
        return {
            "count": count,
            "total_weight": round(total_weight, 3),
            "avg_weight": round(avg_weight, 3) if count else 0.0,
            "by_status": by_status,
        }
    except sqlite3.Error as error:
        log.error("Статистика: %s", error)
        print("Грешка при работа с базата:", error)
        return {"count": 0, "total_weight": 0.0, "avg_weight": 0.0, "by_status": {}}
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    create_table()
    print("Таблицата 'shipments' е готова (файл:", DB_NAME, ")")