import sqlite3
import shipments

DB_NAME = "shipments.db"

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
        print("Грешка при създаване на таблицата:", error)
    finally:
        if conn is not None:
            conn.close()


def add_shipment(shipment):
    query = """
    INSERT INTO shipments (
        tracking_number, sender_name, recipient_name,
        origin_city, destination_city, weight,
        current_status, status_history, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """
    values = (
        shipment.tracking_number,
        shipment.sender_name,
        shipment.recipient_name,
        shipment.origin_city,
        shipment.destination_city,
        shipment.weight,
        shipment.current_status,
        shipment.status_history,
        shipment.created_at,
    )

    conn = None
    try:
        conn = get_connection()
        conn.execute(query, values)
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        print("Вече съществува пратка с този номер за проследяване.")
        return False
    except sqlite3.Error as error:
        print("Грешка при работа с базата:", error)
        return False
    finally:
        if conn is not None:
            conn.close()


def rows_to_shipments(rows):
    result = []
    for row in rows:
        result.append(shipments.Shipment.from_row(row))
    return result


def get_all_shipments(sort_by=None, descending=False):
    order_sql = "ORDER BY id ASC"
    if sort_by:
        try:
            order_sql = shipments.build_order_by(sort_by, descending)
        except shipments.ValidationError as error:
            print(error)

    query = "SELECT * FROM shipments " + order_sql + ";"

    conn = None
    try:
        conn = get_connection()
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        return rows_to_shipments(rows)
    except sqlite3.Error as error:
        print("Грешка при работа с базата:", error)
        return []
    finally:
        if conn is not None:
            conn.close()


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
        print("Грешка при работа с базата:", error)
        return None
    finally:
        if conn is not None:
            conn.close()



SEARCH_FIELDS = {
    "подател": "sender_name",
    "получател": "recipient_name",
    "начален град": "origin_city",
    "краен град": "destination_city",
    "град": "destination_city",
}


def search_shipments(term, field="град"):
    column = SEARCH_FIELDS.get(field, "destination_city")

    try:
        pattern = shipments.like_pattern(term)
    except shipments.ValidationError as error:
        print(error)
        return []

    query = (
        "SELECT * FROM shipments "
        "WHERE PYLOWER(" + column + ") LIKE PYLOWER(?) ESCAPE '\\' "
        "ORDER BY id ASC;"
    )

    conn = None
    try:
        conn = get_connection()
        cursor = conn.execute(query, (pattern,))
        rows = cursor.fetchall()
        return rows_to_shipments(rows)
    except sqlite3.Error as error:
        print("Грешка при работа с базата:", error)
        return []
    finally:
        if conn is not None:
            conn.close()


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
        conn.execute(query, (shipment.current_status, shipment.status_history, shipment.tracking_number))
        conn.commit()
        return True
    except sqlite3.Error as error:
        print("Грешка при работа с базата:", error)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_history(tracking_number):
    shipment = find_shipment_by_tracking(tracking_number)
    if shipment is None:
        return None
    return shipment.status_history


def delete_shipment(tracking_number):
    query = "DELETE FROM shipments WHERE tracking_number = ?;"

    conn = None
    try:
        conn = get_connection()
        cursor = conn.execute(query, (shipments.clean(tracking_number).upper(),))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as error:
        print("Грешка при работа с базата:", error)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_undelivered_shipments():
    query = """
    SELECT * FROM shipments
    WHERE current_status NOT IN (?, ?);
    """

    conn = None
    try:
        conn = get_connection()
        cursor = conn.execute(query, shipments.FINAL_STATUSES)
        rows = cursor.fetchall()
        return rows_to_shipments(rows)
    except sqlite3.Error as error:
        print("Грешка при работа с базата:", error)
        return []
    finally:
        if conn is not None:
            conn.close()


def apply_results(results):  
    failed = []
    for result in results:
        if not result.ok:
            failed.append(result.tracking_number)
            continue
        success = update_status(result.tracking_number, result.new_status)
        if not success:
            failed.append(result.tracking_number)
    return failed


def get_statistics():
    query = "SELECT COUNT(*), COALESCE(SUM(weight), 0), COALESCE(AVG(weight), 0) FROM shipments;"

    conn = None
    try:
        conn = get_connection()
        cursor = conn.execute(query)
        row = cursor.fetchone()
        count = row[0]
        total_weight = row[1]
        avg_weight = row[2]
        return {
            "count": count,
            "total_weight": round(total_weight, 3),
            "avg_weight": round(avg_weight, 3) if count else 0.0,
        }
    except sqlite3.Error as error:
        print("Грешка при работа с базата:", error)
        return {"count": 0, "total_weight": 0.0, "avg_weight": 0.0}
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    create_table()
    print("Таблицата 'shipments' е готова (файл:", DB_NAME, ")")