from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import os
from datetime import datetime

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

EMAIL_FILE = "emails.txt"

# Разрешённые домены популярных почтовых сервисов
ALLOWED_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "yahoo.co.uk",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "icloud.com",
    "me.com",
    "gmx.com",
    "proton.me",
    "protonmail.com",
    # Популярные русскоязычные домены
    "yandex.ru",
    "ya.ru",
    "mail.ru",
    "bk.ru",
    "inbox.ru",
    "list.ru",
    "rambler.ru",
}


def _levenshtein_distance(a: str, b: str) -> int:
    """Вычисляет расстояние Левенштейна между двумя строками."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev_row = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr_row = [i]
        for j, cb in enumerate(b, start=1):
            insert_cost = curr_row[j - 1] + 1
            delete_cost = prev_row[j] + 1
            replace_cost = prev_row[j - 1] + (0 if ca == cb else 1)
            curr_row.append(min(insert_cost, delete_cost, replace_cost))
        prev_row = curr_row
    return prev_row[-1]

@app.route('/subscribe', methods=['POST', 'OPTIONS'])
def subscribe():
    if request.method == 'OPTIONS':
        print(">>> OPTIONS запрос")
        return make_response("", 200)

    data = request.get_json()
    print(">>> Получены данные:", data)

    if not data:
        return jsonify({"error": "No data provided"}), 400

    email = data.get('email')
    print(">>> Email:", email)

    # Базовая валидация и запрет кириллицы
    if not email or '@' not in email:
        return jsonify({"error": "Invalid email"}), 400
    email = email.strip()
    try:
        email.encode('ascii')
    except UnicodeEncodeError:
        return jsonify({"error": "Invalid email: Cyrillic characters are not allowed"}), 400

    # Детальная проверка доменной части и частых опечаток (gmai1, gmaifsfl и т.п.)
    try:
        local_part, domain_part = email.rsplit('@', 1)
    except ValueError:
        return jsonify({"error": "Invalid email"}), 400

    if not local_part or not domain_part:
        return jsonify({"error": "Invalid email"}), 400

    domain_part_lower = domain_part.lower()

    # Простейшие проверки домена
    if '.' not in domain_part_lower or domain_part_lower.startswith('.') or domain_part_lower.endswith('.'):
        return jsonify({"error": "Invalid email domain"}), 400
    if '..' in domain_part_lower:
        return jsonify({"error": "Invalid email domain"}), 400

    if domain_part_lower not in ALLOWED_EMAIL_DOMAINS:
        # Поиск ближайшего корректного домена по расстоянию Левенштейна
        closest_domain = min(ALLOWED_EMAIL_DOMAINS, key=lambda d: _levenshtein_distance(domain_part_lower, d))
        dist = _levenshtein_distance(domain_part_lower, closest_domain)
        # Порог в 2 символа хорошо ловит типичные опечатки (пропуск/перестановка пары букв)
        if dist <= 2:
            suggested_email = f"{local_part}@{closest_domain}"
            return jsonify({
                "error": "Invalid email domain. Possible typo detected",
                "suggestion": suggested_email
            }), 400
        # Если домен совсем другой, считаем его неподдерживаемым (минимизируем мусор)
        return jsonify({"error": "Unsupported email domain"}), 400

    try:
        directory = os.path.dirname(EMAIL_FILE) or "."
        os.makedirs(directory, exist_ok=True)

        # Проверка на существование файла и дубликат email
        if os.path.exists(EMAIL_FILE):
            try:
                with open(EMAIL_FILE, 'r') as rf:
                    for line in rf:
                        # ожидаемый формат: "YYYY-mm-dd HH:MM:SS - email"
                        if line.strip().endswith(f"- {email}") or line.strip().split(" - ")[-1] == email:
                            return jsonify({"error": "Email already subscribed"}), 409
            except Exception as read_err:
                print(">>> Ошибка чтения файла при проверке дубликатов:", read_err)

        with open(EMAIL_FILE, 'a') as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{timestamp} - {email}\n")

        print(">>> Email сохранён")
        return jsonify({"message": "Email saved successfully"}), 200

    except Exception as e:
        print(">>> Ошибка при сохранении:", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Allow port override via ENV; default 5001 per frontend expectation
    port = int(os.environ.get("PORT", 5001))
    host = os.environ.get("HOST", "0.0.0.0")
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    print(f">>> Starting Flask on http://{host}:{port} (debug={debug})")
    app.run(host=host, port=port, debug=debug)