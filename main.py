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


def print_header(title, icon="📌"):
    print(f"\n{COLOR_CYAN}{COLOR_BOLD}{icon} {title.upper()}{COLOR_RESET}\n")


def print_success(msg):
    print(f"{COLOR_GREEN}{COLOR_BOLD}✔ {msg}{COLOR_RESET}")


def print_error(msg):
    print(f"{COLOR_RED}{COLOR_BOLD}✖ {msg}{COLOR_RESET}")


def print_info(msg):
    print(f"{COLOR_YELLOW}ℹ {msg}{COLOR_RESET}")


def prompt(label):
    return input(f"{COLOR_BOLD}{COLOR_BLUE}➤ {label}:{COLOR_RESET} ").strip()


def display_menu():
    print(f"\n{COLOR_YELLOW}{COLOR_BOLD}🤗 СИСТЕМА ЗА УПРАВЛЕНИЕ И ПРОСЛЕДЯВАНЕ НА ПРАТКИ 👏🏻{COLOR_RESET}")
    print(f"{COLOR_GREEN}1.{COLOR_RESET} ➕📥 Добавяне на нова пратка")
    print(f"{COLOR_GREEN}2.{COLOR_RESET} 📋🙌 Показване на всички пратки")
    print(f"{COLOR_GREEN}3.{COLOR_RESET} 🔍🧐 Търсене по номер за проследяване")
    print(f"{COLOR_GREEN}4.{COLOR_RESET} 🔄🤩 Промяна на статус")
    print(f"{COLOR_GREEN}5.{COLOR_RESET} 📜😒 Показване на история на статус")
    print(f"{COLOR_GREEN}6.{COLOR_RESET} 📦🕳️ Изтриване на пратка")
    print(f"{COLOR_GREEN}7.{COLOR_RESET} 😵‍💫 Едновременна обработка")
    print(f"{COLOR_GREEN}8.{COLOR_RESET} 🕵️🤨 Търсене по име или град")
    print(f"{COLOR_GREEN}9.{COLOR_RESET} 📊🤭 Обща статистика")
    print(f"{COLOR_RED}0.{COLOR_RESET} 👉🏻🚪 Изход\n")


def render_shipments_table(shipment_list):
    if not shipment_list:
        print_info("Няма намерени пратки. 😔")
        return

    print_info(f"Общ брой пратки: {len(shipment_list)} 😜\n")

    for idx, s in enumerate(shipment_list, 1):
        print(f"{COLOR_CYAN}ПРАТКА #{idx} [{COLOR_YELLOW}{s.tracking_number}{COLOR_CYAN}]{COLOR_RESET}")
        print(f"  {COLOR_BOLD}Номер за проследяване:{COLOR_RESET} {s.tracking_number}")
        print(f"  {COLOR_BOLD}Подател:{COLOR_RESET}               {s.sender_name}")
        print(f"  {COLOR_BOLD}Получател:{COLOR_RESET}             {s.recipient_name}")
        print(f"  {COLOR_BOLD}Начален град:{COLOR_RESET}          {s.origin_city}")
        print(f"  {COLOR_BOLD}Краен град:{COLOR_RESET}            {s.destination_city}")
        print(f"  {COLOR_BOLD}Текущ статус:{COLOR_RESET}          {COLOR_MAGENTA}{s.current_status}{COLOR_RESET}")
        print(f"  {COLOR_BOLD}Тегло:{COLOR_RESET}                 {s.weight:.2f} kg\n")


def extract_tracking_numbers(shipment_list):
    numbers = []
    for s in shipment_list:
        numbers.append(s.tracking_number)
    return numbers


def action_add_shipment():
    print_header("Добавяне на пратка", "➕📥")
    try:
        all_shipments = database.get_all_shipments()
        all_numbers = extract_tracking_numbers(all_shipments)

        if hasattr(database, "get_file_tracking_numbers"):
            file_numbers = database.get_file_tracking_numbers()
            for num in file_numbers:
                if num not in all_numbers:
                    all_numbers.append(num)

        auto_num = shipments.next_tracking_number(all_numbers)

        num_input = prompt(f"Номер за проследяване (Enter за '{auto_num}' 😉)")
        tracking_number = num_input if shipments.clean(num_input) else auto_num

        if tracking_number in all_numbers:
            print_error(f"Номерът '{tracking_number}' вече съществува в системата или във файла! 😒")
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

        success = database.add_shipment(new_shipment)
        if success:
            print_success(f"Пратката {new_shipment.tracking_number} беше добавена успешно! 🤩")

    except shipments.ValidationError as error:
        print_error(f"Грешка във въвеждането: {error} 🥺")


def action_show_all():
    print_header("Всички пратки в системата", "📋🙌")
    all_shipments = database.get_all_shipments()

    if not all_shipments:
        print_info("Базата данни е празна. 😔")
        return

    render_shipments_table(all_shipments)


def action_search_by_tracking():
    print_header("Търсене по номер", "🔍🧐")
    tn = prompt("Въведете номер за проследяване")
    if not shipments.clean(tn):
        print_error("Номерът за проследяване не може да бъде празен. 😤")
        return

    shipment = database.find_shipment_by_tracking(tn)
    if shipment:
        print(f"\n{COLOR_CYAN}{COLOR_BOLD}ДЕТАЙЛИ ЗА ПРАТКА{COLOR_RESET}")
        print(shipment.format_full())
    else:
        print_error(f"Няма пратка с номер '{tn.upper()}'. 😬")


def action_change_status():
    print_header("Промяна на статус", "🔄🤩")
    tn = prompt("Въведете номер за проследяване")
    shipment = database.find_shipment_by_tracking(tn)

    if not shipment:
        print_error(f"Пратка с номер '{tn}' не съществува. 😐")
        return

    print(f"\nТекущ статус: {COLOR_MAGENTA}{COLOR_BOLD}{shipment.current_status}{COLOR_RESET}\n")
    print(f"{COLOR_BOLD}Изберете нов статус:{COLOR_RESET}")
    for idx, status in enumerate(shipments.STATUSES, 1):
        print(f"  {COLOR_GREEN}{idx}.{COLOR_RESET} {status}")

    choice = prompt("Изберете номер от списъка (1-8)")
    try:
        new_status = shipments.status_by_index(choice)
        success = database.update_status(tn, new_status)
        if success:
            print_success(f"Статусът на пратка {shipment.tracking_number} беше променен на '{new_status}'. 🥳")
    except shipments.ValidationError as error:
        print_error(str(error))


def action_show_history():
    print_header("История на статусите", "📜😒")
    tn = prompt("Въведете номер за проследяване")
    shipment = database.find_shipment_by_tracking(tn)

    if not shipment:
        print_error(f"Пратка с номер '{tn}' не съществува. 🤔")
        return

    print(f"\nИстория на промените за пратка {COLOR_YELLOW}{shipment.tracking_number}{COLOR_RESET}:")
    print(shipment.format_history())


def action_delete_shipment():
    print_header("Изтриване на пратка", "📦🕳️")
    tn = prompt("Въведете номер за проследяване")
    shipment = database.find_shipment_by_tracking(tn)

    if not shipment:
        print_error(f"Пратка с номер '{tn}' не съществува. 🙄")
        return

    confirm = prompt(f"Сигурни ли сте, че искате да изтриете {shipment.tracking_number}? (да/не)").lower()
    if confirm in ("да", "d", "y", "yes"):
        success = database.delete_shipment(tn)
        if success:
            print_success(f"Пратката {shipment.tracking_number} беше изтрита успешно. 😝")
        else:
            print_error("Изтриването не беше успешно. 😔")
    else:
        print_info("Действието беше отменено. ☹️")


def action_process_concurrently():
    print_header("Едновременна обработка", "😵‍💫")
    undelivered = database.get_undelivered_shipments()

    if not undelivered:
        print_info("Няма недоставени пратки за обработка. 😶")
        return

    print_info(f"Намерени недоставени пратки: {len(undelivered)}")
    batch_to_process = undelivered[:10]
    print_info(f"Стартиране на ThreadPoolExecutor за {len(batch_to_process)} пратки... 😮‍💨\n")

    results = workers.process_batch(batch_to_process, max_workers=workers.MAX_WORKERS, simulate=True)
    failed_trackings = database.apply_results(results)

    print(f"\n{COLOR_CYAN}РЕЗУЛТАТИ ОТ ОБРАБОТКАТА{COLOR_RESET}")
    print(workers.format_results(results))

    if failed_trackings:
        print_error(f"Внимание! {len(failed_trackings)} пратки не успяха да се обновят в базата. 😑")


def action_extra_search():
    print_header("Търсене по критерий", "🕵️🤨")
    print(f"{COLOR_DIM}Полета за търсене: град, подател, получател, начален град, краен град{COLOR_RESET}")
    field = prompt("Изберете поле (Enter за 'град')")
    if not shipments.clean(field):
        field = "град"

    term = prompt("Въведете дума за търсене")
    if not shipments.clean(term):
        print_error("Търсената дума не може да е празна. 🤨")
        return

    results = database.search_shipments(term, field=field)
    if not results:
        print_info(f"Няма намерени пратки по критерий '{term}'. 😔")
        return

    render_shipments_table(results)


def action_extra_stats():
    print_header("Обща статистика", "📊🤭")
    all_shipments = database.get_all_shipments()
    full_stats = shipments.summarize_shipments(all_shipments)
    print(shipments.format_stats(full_stats))


def main():
    database.create_table()

    while True:
        display_menu()
        choice = prompt("Изберете действие (0-9) 😁")

        if choice == "1":
            action_add_shipment()
        elif choice == "2":
            action_show_all()
        elif choice == "3":
            action_search_by_tracking()
        elif choice == "4":
            action_change_status()
        elif choice == "5":
            action_show_history()
        elif choice == "6":
            action_delete_shipment()
        elif choice == "7":
            action_process_concurrently()
        elif choice == "8":
            action_extra_search()
        elif choice == "9":
            action_extra_stats()
        elif choice == "0":
            print(
                f"\n{COLOR_GREEN}{COLOR_BOLD}😍 Благодарим ви, че използвахте системата за пратки! 🥰 BYEEEEEEE!!!!!! 😘👋🏻{COLOR_RESET}\n")
            sys.exit(0)
        else:
            print_error("Невалиден избор от менюто. Моля, въведете число от 0 до 9. 🤨")


if __name__ == "__main__":
    main()