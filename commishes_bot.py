import urllib.request
import urllib.parse
import json
import time
import os
import re
import threading


# ==========================================
# НАСТРОЙКИ
# ==========================================

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

CHECK_INTERVAL = 30


# ==========================================
# COMMISHES
# ==========================================

def get_auction(url):
    json_url = url.rstrip("/")

    if not json_url.endswith(".json"):
        json_url += ".json"

    request = urllib.request.Request(
        json_url,
        headers={
            "User-Agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0.0.0 Safari/537.36"
        }
    )

    response = urllib.request.urlopen(request, timeout=15)

    return json.loads(
        response.read().decode("utf-8")
    )


def get_auction_info(url):
    data = get_auction(url)
    payload = data["payload"]

    slot = next(iter(payload["slots"].values()))
    bids = slot.get("bids", [])

    return {
        "id": str(payload["id"]),
        "title": payload["title"],
        "bid": slot["highestbid"],
        "bids": bids,
        "ends": payload["ends"],
        "endsunix": payload["endsunix"]
    }


# ==========================================
# ID АУКЦИОНА
# ==========================================

def get_auction_id(url):
    match = re.search(
        r"/auction/show/([^/]+)",
        url
    )

    if match:
        return match.group(1)

    return None


# ==========================================
# TELEGRAM
# ==========================================

def telegram_request(method, params=None):
    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/{method}"
    )

    if params:
        data = urllib.parse.urlencode(
            params
        ).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=data
        )
    else:
        request = urllib.request.Request(url)

    response = urllib.request.urlopen(
        request,
        timeout=30
    )

    return json.loads(
        response.read().decode("utf-8")
    )


def send_telegram(message):
    try:
        telegram_request(
            "sendMessage",
            {
                "chat_id": CHAT_ID,
                "text": message
            }
        )

    except Exception as error:
        print(
            f"⚠️ Ошибка Telegram: {error}"
        )


# ==========================================
# ХРАНЕНИЕ АУКЦИОНОВ
# ==========================================

# Для Railway используем простой файл.
# При перезапуске Railway список может сброситься,
# поэтому позже можем подключить постоянное хранилище.

auctions = {}


# ==========================================
# ДОБАВЛЕНИЕ
# ==========================================

def add_auction(url):
    auction_id = get_auction_id(url)

    if not auction_id:
        raise ValueError(
            "Не удалось определить ID аукциона."
        )

    info = get_auction_info(url)

    if auction_id in auctions:
        return False, auction_id, info

    auctions[auction_id] = {
        "url": (
            f"https://ych.commishes.com/"
            f"auction/show/{auction_id}/"
        ),
        "title": info["title"],
        "last_bid": info["bid"],
        "last_bids_count": len(info["bids"]),
        "endsunix": info["endsunix"]
    }

    return True, auction_id, info


# ==========================================
# УДАЛЕНИЕ
# ==========================================

def remove_auction(auction_id):
    if auction_id in auctions:
        del auctions[auction_id]
        return True

    return False


# ==========================================
# TELEGRAM КОМАНДЫ
# ==========================================

def process_message(message):

    chat_id = str(
        message["chat"]["id"]
    )

    # Только твой аккаунт может управлять ботом
    if chat_id != CHAT_ID:
        return

    text = message.get(
        "text",
        ""
    ).strip()

    if not text:
        return


    # --------------------------------------
    # /start
    # --------------------------------------

    if text == "/start":

        send_telegram(
            "🌸 Commishes Bid Watcher\n\n"
            "Я слежу за ставками на "
            "YCH.Commishes.\n\n"
            "Команды:\n"
            "/add <ссылка> — добавить аукцион\n"
            "/remove <ID> — удалить аукцион\n"
            "/list — список аукционов\n"
            "/check — проверить сейчас"
        )

        return


    # --------------------------------------
    # /list
    # --------------------------------------

    if text == "/list":

        if not auctions:

            send_telegram(
                "📭 Сейчас я ни за одним "
                "аукционом не слежу."
            )

            return

        result = (
            "🌸 Отслеживаемые аукционы:\n\n"
        )

        for auction_id, auction in auctions.items():

            result += (
                f"🌸 {auction['title']}\n"
                f"💰 ${auction['last_bid']}\n"
                f"🆔 {auction_id}\n"
                f"🔗 {auction['url']}\n\n"
            )

        send_telegram(result)

        return


    # --------------------------------------
    # /add
    # --------------------------------------

    if text.startswith("/add"):

        parts = text.split(
            maxsplit=1
        )

        if len(parts) < 2:

            send_telegram(
                "Использование:\n\n"
                "/add https://ych.commishes.com/auction/..."
            )

            return

        url = parts[1].strip()

        try:

            added, auction_id, info = add_auction(
                url
            )

            if added:

                send_telegram(
                    "✅ Начал следить!\n\n"
                    f"🌸 {info['title']}\n"
                    f"💰 Текущая ставка: ${info['bid']}\n"
                    f"👥 Ставок: {len(info['bids'])}\n"
                    f"🆔 {auction_id}\n\n"
                    f"https://ych.commishes.com/"
                    f"auction/show/{auction_id}/"
                )

            else:

                send_telegram(
                    "ℹ️ Я уже слежу за этим аукционом.\n\n"
                    f"🌸 {info['title']}\n"
                    f"💰 ${info['bid']}\n"
                    f"🆔 {auction_id}"
                )

        except Exception as error:

            send_telegram(
                "❌ Не удалось добавить аукцион.\n\n"
                f"Ошибка: {error}"
            )

        return


    # --------------------------------------
    # /remove
    # --------------------------------------

    if text.startswith("/remove"):

        parts = text.split(
            maxsplit=1
        )

        if len(parts) < 2:

            send_telegram(
                "Использование:\n\n"
                "/remove 5PSFM"
            )

            return

        auction_id = parts[1].strip()

        if remove_auction(auction_id):

            send_telegram(
                "🗑 Перестал следить за аукционом."
            )

        else:

            send_telegram(
                f"❌ Аукцион {auction_id} "
                "не найден."
            )

        return


    # --------------------------------------
    # /check
    # --------------------------------------

    if text == "/check":

        send_telegram(
            "🔎 Проверяю аукционы..."
        )

        check_auctions()

        return


# ==========================================
# TELEGRAM LISTENER
# ==========================================

def telegram_listener():

    offset = None

    print(
        "📱 Telegram listener запущен."
    )

    while True:

        try:

            params = {
                "timeout": 10
            }

            if offset is not None:
                params["offset"] = offset

            result = telegram_request(
                "getUpdates",
                params
            )

            for update in result.get(
                "result",
                []
            ):

                offset = (
                    update["update_id"] + 1
                )

                message = update.get(
                    "message"
                )

                if message:
                    process_message(message)

        except Exception as error:

            print(
                f"⚠️ Telegram listener: {error}"
            )

            time.sleep(5)


# ==========================================
# ПРОВЕРКА АУКЦИОНОВ
# ==========================================

def check_auctions():

    if not auctions:
        return

    for auction_id in list(
        auctions.keys()
    ):

        auction = auctions[auction_id]

        try:

            info = get_auction_info(
                auction["url"]
            )

            current_bids = info["bids"]
            old_count = auction[
                "last_bids_count"
            ]


            # Новые ставки
            if len(current_bids) > old_count:

                new_bids = current_bids[
                    old_count:
                ]

                for bid in new_bids:

                    username = bid.get(
                        "name",
                        "Unknown"
                    )

                    amount = bid.get(
                        "bid",
                        "?"
                    )

                    send_telegram(
                        "🔔 НОВАЯ СТАВКА!\n\n"
                        f"🌸 {info['title']}\n"
                        f"💰 ${amount}\n"
                        f"👤 {username}\n\n"
                        f"{auction['url']}"
                    )

                    print(
                        f"🔔 {info['title']} — "
                        f"{username}: ${amount}"
                    )


            auction["last_bid"] = info["bid"]

            auction["last_bids_count"] = (
                len(current_bids)
            )

            auction["title"] = info["title"]

            auction["endsunix"] = (
                info["endsunix"]
            )

            print(
                f"✓ {info['title']} — "
                f"${info['bid']} — "
                f"{len(current_bids)} ставок"
            )


        except Exception as error:

            print(
                f"⚠️ Ошибка {auction_id}: "
                f"{error}"
            )


# ==========================================
# ЗАПУСК
# ==========================================

print()
print("🌸 Commishes Bid Watcher")
print("========================")
print("Telegram подключён.")
print("Бот запущен!")
print()


# Запускаем Telegram listener
telegram_thread = threading.Thread(
    target=telegram_listener,
    daemon=True
)

telegram_thread.start()


send_telegram(
    "🌸 Commishes Bid Watcher запущен!\n\n"
    "Напиши /add и ссылку на YCH, "
    "чтобы начать отслеживание."
)


# ==========================================
# ГЛАВНЫЙ ЦИКЛ
# ==========================================

while True:

    try:

        check_auctions()

    except Exception as error:

        print(
            f"⚠️ Ошибка проверки: {error}"
        )

    time.sleep(
        CHECK_INTERVAL
    )
