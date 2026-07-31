import sys

import database
import shipments
import workers

COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_CYAN = "\033[36m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_RED = "\033[31m"
COLOR_MAGENTA = "\033[35m"
COLOR_BLUE = "\033[34m"
COLOR_DIM = "\033[2m"

YES_ANSWERS = ("да", "д", "yes", "y", "d")


def print_header(title, icon="📌"):
    print(f"\n{COLOR_CYAN}{COLOR_BOLD}{icon} {title.upper()}{COLOR_RESET}\n")


def print_success(msg):
    print(f"{COLOR_GREEN}{COLOR_BOLD}✔ {msg}{COLOR_RESET}")


def print_error(msg):
    print(f"{COLOR_RED}{COLOR_BOLD}✖ {msg}{COLOR_RESET}")


def print_info(msg):
    print(f"{COLOR_YELLOW}ℹ {msg}{COLOR_RESET}")


def prompt(label):
    """input() със защита от Ctrl+C / Ctrl+D - без traceback на екрана."""
    try:
        return input(f"{COLOR_BOLD}{COLOR_BLUE}➤ {label}:{COLOR_RESET} ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        print_info("Прекъснато от потребителя. Изход.")
        sys.exit(0)


def confirm(label):
    return prompt(f"{label} (да/не)").lower() in YES_ANSWERS


def display_menu():
    print(f"\n{COLOR_YELLOW}{COLOR_BOLD}ZIPShip{COLOR_RESET}")
    print(f"{COLOR_GREEN} 1.{COLOR_RESET} ➕📥 Добавяне на нова пратка")
    print(f"{COLOR_GREEN} 2.{COLOR_RESET} 📋🙌 Показване на всички пратки (със сортиране)")
    print(f"{COLOR_GREEN} 3.{COLOR_RESET} 🔍🧐 Търсене по номер за проследяване")
    print(f"{COLOR_GREEN} 4.{COLOR_RESET} 🔄🤩 Промяна на статус")
    print(f"{COLOR_GREEN} 5.{COLOR_RESET} 📜😒 Показване на история на статус")
    print(f"{COLOR_GREEN} 6.{COLOR_RESET} 📦🕳️ Изтриване на пратка")
    print(f"{COLOR_GREEN} 7.{COLOR_RESET} 😵‍💫 Едновременна обработка (нишки)")
    print(f"{COLOR_GREEN} 8.{COLOR_RESET} 🕵️🤨 Търсене и филтриране")
    print(f"{COLOR_GREEN} 9.{COLOR_RESET} 📊🤭 Обща статистика")
    print(f"{COLOR_GREEN}10.{COLOR_RESET} Редактиране на пратка")
    print(f"{COLOR_RED} 0.{COLOR_RESET} Изход\n")


def render_shipments_table(shipment_list):
    if not shipment_list:
        print_info("Няма намерени пратки. 😔")
        return

    print_info(f"Общ брой пратки: {len(shipment_list)}\n")

    for idx, s in enumerate(shipment_list, 1):
        print(f"{COLOR_CYAN}ПРАТКА #{idx}{COLOR_RESET}")
        print(f"  {COLOR_BOLD}Номер за проследяване:{COLOR_RESET} {COLOR_YELLOW}{s.tracking_number}{COLOR_RESET}")
        print(f"  {COLOR_BOLD}Подател:{COLOR_RESET}               {s.sender_name}")
        print(f"  {COLOR_BOLD}Получател:{COLOR_RESET}             {s.recipient_name}")
        print(f"  {COLOR_BOLD}Начален град:{COLOR_RESET}          {s.origin_city}")
        print(f"  {COLOR_BOLD}Краен град:{COLOR_RESET}            {s.destination_city}")
        print(f"  {COLOR_BOLD}Текущ статус:{COLOR_RESET}          {COLOR_MAGENTA}{s.current_status}{COLOR_RESET}")
        print(f"  {COLOR_BOLD}Тегло:{COLOR_RESET}                 {s.weight:g} kg")
        print(f"  {COLOR_BOLD}Създадена:{COLOR_RESET}             {s.created_at}\n")


def extract_tracking_numbers(shipment_list):
    return [s.tracking_number for s in shipment_list]


# ---------------------------------------------------------------- сортиране

def ask_sorting():
    """Връща (sort_by, descending). Enter = без сортиране."""
    print(f"\n{COLOR_BOLD}Сортиране:{COLOR_RESET}")
    for idx, (_, label) in enumerate(shipments.SORT_MENU, 1):
        print(f"  {COLOR_GREEN}{idx}.{COLOR_RESET} {label}")
    print(f"  {COLOR_DIM}Enter = без сортиране (по реда на въвеждане){COLOR_RESET}")

    choice = prompt(f"Изберете поле (1-{len(shipments.SORT_MENU)})")
    if not shipments.clean(choice):
        return None, False

    sort_by = shipments.sort_key_by_index(choice)
    descending = prompt("Посока: 1. Възходящо  2. Низходящо (Enter = възходящо)") == "2"
    return sort_by, descending


# ---------------------------------------------------------------- действия

def action_add_shipment():
    print_header("Добавяне на пратка", "➕")
    try:
        all_shipments = database.get_all_shipments()
        all_numbers = extract_tracking_numbers(all_shipments)
        auto_num = shipments.next_tracking_number(all_numbers)

        num_input = prompt(f"Номер за проследяване (Enter за '{auto_num}' 😉)")
        # нормализираме ВЕДНАГА, иначе 'zip1001' минава проверката за дубликат
        if shipments.clean(num_input):
            tracking_number = shipments.validate_tracking_number(num_input)
        else:
            tracking_number = auto_num

        if tracking_number in all_numbers:
            print_error(f"Номерът '{tracking_number}' вече съществува в системата!")
            return

        sender = prompt("Име на подател")
        recipient = prompt("Име на получател")
        origin = prompt("Начален град")
        destination = prompt("Краен град")
        weight_raw = prompt("Тегло (kg)")

        new_shipment = shipments.Shipment.create(
            tracking_number=tracking_number,
            sender_name=sender,
            recipient_name=recipient,
            origin_city=origin,
            destination_city=destination,
            weight=weight_raw,
        )

        if database.add_shipment(new_shipment):
            print_success(f"Пратката {new_shipment.tracking_number} беше добавена успешно!")

    except shipments.ValidationError as error:
        print_error(f"Грешка във въвеждането: {error} 🥺")


def action_show_all():
    print_header("Всички пратки в системата", "📋")
    try:
        sort_by, descending = ask_sorting()
        all_shipments = database.get_all_shipments(sort_by=sort_by, descending=descending)
    except shipments.ValidationError as error:
        print_error(str(error))
        return

    if not all_shipments:
        print_info("Базата данни е празна. 😔")
        return

    render_shipments_table(all_shipments)


def action_search_by_tracking():
    print_header("Търсене по номер", "🔍")
    tn = prompt("Въведете номер за проследяване")
    if not shipments.clean(tn):
        print_error("Номерът за проследяване не може да бъде празен. 😤")
        return

    shipment = database.find_shipment_by_tracking(tn)
    if shipment:
        print(f"\n{COLOR_CYAN}{COLOR_BOLD}ДЕТАЙЛИ ЗА ПРАТКА{COLOR_RESET}")
        print(shipment.format_full())
    else:
        print_error(f"Няма пратка с номер '{shipments.clean(tn).upper()}'. 😬")


def action_change_status():
    print_header("Промяна на статус", "🔄")
    tn = prompt("Въведете номер за проследяване")
    shipment = database.find_shipment_by_tracking(tn)

    if not shipment:
        print_error(f"Пратка с номер '{tn}' не съществува. 😐")
        return

    print(f"\nТекущ статус: {COLOR_MAGENTA}{COLOR_BOLD}{shipment.current_status}{COLOR_RESET}\n")

    # краен статус = приключена пратка; връщането в обработка изисква потвърждение
    if shipment.is_final:
        print_info(
            f"Пратката е в краен статус '{shipment.current_status}' и се води приключена."
        )
        if not confirm("Сигурни ли сте, че искате да я върнете в обработка?"):
            print_info("Действието беше отменено.")
            return

    print(f"{COLOR_BOLD}Изберете нов статус:{COLOR_RESET}")
    for idx, status in enumerate(shipments.STATUSES, 1):
        print(f"  {COLOR_GREEN}{idx}.{COLOR_RESET} {status}")

    choice = prompt(f"Изберете номер от списъка (1-{len(shipments.STATUSES)})")
    try:
        new_status = shipments.status_by_index(choice)
        if database.update_status(tn, new_status):
            print_success(
                f"Статусът на пратка {shipment.tracking_number} беше променен на '{new_status}' 🥳."
            )
    except shipments.ValidationError as error:
        print_error(str(error))


def action_show_history():
    print_header("История на статусите", "📜")
    tn = prompt("Въведете номер за проследяване")
    shipment = database.find_shipment_by_tracking(tn)

    if not shipment:
        print_error(f"Пратка с номер '{tn}' не съществува. 🤔")
        return

    print(f"\nИстория на промените за пратка {COLOR_YELLOW}{shipment.tracking_number}{COLOR_RESET}:")
    print(shipment.format_history())


def action_delete_shipment():
    print_header("Изтриване на пратка", "🗑")
    tn = prompt("Въведете номер за проследяване")
    shipment = database.find_shipment_by_tracking(tn)

    if not shipment:
        print_error(f"Пратка с номер '{tn}' не съществува. 🙄")
        return

    print("\n" + shipment.format_full() + "\n")
    if confirm(f"Сигурни ли сте, че искате да изтриете {shipment.tracking_number}?"):
        if database.delete_shipment(tn):
            print_success(f"Пратката {shipment.tracking_number} беше изтрита успешно.")
        else:
            print_error("Изтриването не беше успешно. 😔")
    else:
        print_info("Действието беше отменено. ☹️")


def action_edit_shipment():
    print_header("Редактиране на пратка", "✏")
    tn = prompt("Въведете номер за проследяване")
    shipment = database.find_shipment_by_tracking(tn)

    if not shipment:
        print_error(f"Пратка с номер '{tn}' не съществува.")
        return

    before = shipment.copy()  # снимка отпреди промяната, за да покажем разликата
    print("\n" + before.format_full() + "\n")
    print_info("Enter на празно поле = стойността остава непроменена.")

    try:
        changes = shipment.update_details(
            sender_name=prompt(f"Подател [{before.sender_name}]"),
            recipient_name=prompt(f"Получател [{before.recipient_name}]"),
            origin_city=prompt(f"Начален град [{before.origin_city}]"),
            destination_city=prompt(f"Краен град [{before.destination_city}]"),
            weight=prompt(f"Тегло kg [{before.weight:g}]"),
        )
        if not database.update_shipment(shipment.tracking_number, changes):
            print_error("Промените не бяха записани.")
            return
    except shipments.ValidationError as error:
        print_error(str(error))
        return

    print_success(f"Пратката {shipment.tracking_number} беше редактирана.")
    for column, new_value in changes.items():
        old_value = getattr(before, column)
        print(f"  {column}: {COLOR_DIM}{old_value}{COLOR_RESET} -> {COLOR_GREEN}{new_value}{COLOR_RESET}")


def action_process_concurrently():
    print_header("Едновременна обработка", "🧵")
    undelivered = database.get_undelivered_shipments()

    if not undelivered:
        print_info("Няма недоставени пратки за обработка. 😶")
        return

    print_info(f"Намерени недоставени пратки: {len(undelivered)}")
    if len(undelivered) < 3:
        print_error(
            "Внимание: заданието изисква едновременна обработка на поне 3 пратки. "
            f"В момента има само {len(undelivered)}."
        )

    batch = undelivered[:10]

    print(f"\n{COLOR_BOLD}Реализация:{COLOR_RESET}")
    print(f"  {COLOR_GREEN}1.{COLOR_RESET} ThreadPoolExecutor (executor.map)")
    print(f"  {COLOR_GREEN}2.{COLOR_RESET} Клас ShipmentWorker(Thread) - start() / run() / join()")
    impl = prompt("Изберете реализация (Enter = 1)")

    print_info(f"Стартиране за {len(batch)} пратки...\n")
    if impl == "2":
        results = workers.process_batch_threads(batch, simulate=True)
    else:
        results = workers.process_batch(
            batch, max_workers=workers.MAX_WORKERS, simulate=True
        )

    failed_trackings = database.apply_results(results)

    print(f"\n{COLOR_CYAN}{COLOR_BOLD}РЕЗУЛТАТИ ОТ ОБРАБОТКАТА{COLOR_RESET}")
    print(workers.format_results(results))

    print(f"\n{COLOR_CYAN}{COLOR_BOLD}АКТУАЛНО СЪСТОЯНИЕ{COLOR_RESET}")
    for s in batch:
        refreshed = database.find_shipment_by_tracking(s.tracking_number)
        if refreshed:
            print("  " + refreshed.format_short())

    if failed_trackings:
        print_error(f"Внимание! {len(failed_trackings)} пратки не успяха да се обновят в базата. 😑")


def action_search_or_filter():
    print_header("Търсене и филтриране", "🕵")
    print(f"  {COLOR_GREEN}1.{COLOR_RESET} Търсене по дума (име или град)")
    print(f"  {COLOR_GREEN}2.{COLOR_RESET} Филтриране (статус / град / минимално тегло)")
    mode = prompt("Изберете режим (Enter = 1)")

    try:
        if mode == "2":
            results = _run_filter()
        else:
            results = _run_search()
    except shipments.ValidationError as error:
        print_error(str(error))
        return

    if not results:
        print_info("Няма намерени пратки по зададените критерии.")
        return

    render_shipments_table(results)


def _run_search():
    print(f"\n{COLOR_BOLD}Поле за търсене:{COLOR_RESET}")
    for idx, (_, label) in enumerate(shipments.SEARCH_MENU, 1):
        print(f"  {COLOR_GREEN}{idx}.{COLOR_RESET} {label}")
    print(f"  {COLOR_DIM}Enter = Краен град{COLOR_RESET}")

    field_choice = prompt(f"Изберете поле (1-{len(shipments.SEARCH_MENU)})")
    field = "краен град"
    if shipments.clean(field_choice):
        field = shipments.search_field_by_index(field_choice)

    term = prompt("Въведете дума за търсене")
    sort_by, descending = ask_sorting()
    return database.search_shipments(term, field=field, sort_by=sort_by, descending=descending)


def _run_filter():
    print(f"\n{COLOR_DIM}Всеки филтър е незадължителен - Enter го пропуска. "
          f"Зададените се комбинират с AND.{COLOR_RESET}")

    print(f"\n{COLOR_BOLD}Статус:{COLOR_RESET}")
    for idx, status in enumerate(shipments.STATUSES, 1):
        print(f"  {COLOR_GREEN}{idx}.{COLOR_RESET} {status}")
    status_choice = prompt(f"Изберете статус (1-{len(shipments.STATUSES)}, Enter = без филтър)")
    status = shipments.status_by_index(status_choice) if shipments.clean(status_choice) else None

    city = prompt("Град (начален или краен, Enter = без филтър)") or None
    min_weight = prompt("Минимално тегло в kg (Enter = без филтър)") or None

    sort_by, descending = ask_sorting()
    return database.filter_shipments(
        status=status,
        city=city,
        min_weight=min_weight,
        sort_by=sort_by,
        descending=descending,
    )


def action_stats():
    print_header("Обща статистика", "📊")
    # COUNT / SUM / AVG + GROUP BY идват директно от SQL
    print(shipments.format_stats(database.get_statistics()))


# ---------------------------------------------------------------- цикъл

ACTIONS = {
    "1": action_add_shipment,
    "2": action_show_all,
    "3": action_search_by_tracking,
    "4": action_change_status,
    "5": action_show_history,
    "6": action_delete_shipment,
    "7": action_process_concurrently,
    "8": action_search_or_filter,
    "9": action_stats,
    "10": action_edit_shipment,
}


def main():
    database.create_table()

    while True:
        display_menu()
        choice = prompt("Изберете действие (0-10) 😁")

        if choice == "0":
            print(f"\n{COLOR_GREEN}{COLOR_BOLD}😍 Благодарим ви, че използвахте ZIPShip! 🥰 BYEEEEEEE!!!!!! 😘👋🏻{COLOR_RESET}\n")
            sys.exit(0)

        action = ACTIONS.get(choice)
        if action is None:
            print_error("Невалиден избор от менюто. Моля, въведете число от 0 до 10. 🤨")
            continue

        action()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print_info("Прекъснато от потребителя. Изход.")
        sys.exit(0)