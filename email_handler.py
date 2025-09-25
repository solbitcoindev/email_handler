from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Подключение к PostgreSQL (Render даёт DATABASE_URL)
# Предпочтительно брать из переменной окружения, иначе используем предоставленный URL от пользователя
raw_database_url = os.getenv(
    "DATABASE_URL",
    "postgresql://email_db_v4ul_user:FGEM0or6rqn6Jya8Ug7d0ZIgP0UVAXsZ@dpg-d3aigfs9c44c73dtv3l0-a/email_db_v4ul",
)

# Нормализуем схемы и добавляем sslmode=require при необходимости (Render обычно требует SSL)
def _normalize_database_url(url: str) -> str:
    if not url:
        return url
    normalized = url
    # Heroku-style "postgres://" → SQLAlchemy ожидает "postgresql://"
    if normalized.startswith("postgres://"):
        normalized = "postgresql://" + normalized[len("postgres://"):]
    # Если нет параметра sslmode, добавим его как require
    if normalized.startswith("postgresql://") and "sslmode=" not in normalized:
        separator = "&" if "?" in normalized else "?"
        normalized = f"{normalized}{separator}sslmode=require"
    return normalized

DATABASE_URL = _normalize_database_url(raw_database_url)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

# Модель таблицы email
class Email(Base):
    __tablename__ = "emails"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# Создание таблиц
Base.metadata.create_all(bind=engine)

# Разрешённые домены
ALLOWED_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.co.uk", "outlook.com",
    "hotmail.com", "live.com", "msn.com", "icloud.com",
    "me.com", "gmx.com", "proton.me", "protonmail.com",
    "yandex.ru", "ya.ru", "mail.ru", "bk.ru", "inbox.ru",
    "list.ru", "rambler.ru",
}

def _levenshtein_distance(a: str, b: str) -> int:
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
        return make_response("", 200)

    data = request.get_json()
    if not data or "email" not in data:
        return jsonify({"error": "No data provided"}), 400

    email = data.get("email").strip()
    if not email or '@' not in email:
        return jsonify({"error": "Invalid email"}), 400

    # Запрет кириллицы
    try:
        email.encode('ascii')
    except UnicodeEncodeError:
        return jsonify({"error": "Invalid email: Cyrillic characters are not allowed"}), 400

    try:
        local_part, domain_part = email.rsplit('@', 1)
    except ValueError:
        return jsonify({"error": "Invalid email"}), 400

    domain_part_lower = domain_part.lower()

    # Проверка домена
    if '.' not in domain_part_lower or domain_part_lower.startswith('.') or domain_part_lower.endswith('.'):
        return jsonify({"error": "Invalid email domain"}), 400
    if '..' in domain_part_lower:
        return jsonify({"error": "Invalid email domain"}), 400

    if domain_part_lower not in ALLOWED_EMAIL_DOMAINS:
        closest_domain = min(ALLOWED_EMAIL_DOMAINS, key=lambda d: _levenshtein_distance(domain_part_lower, d))
        dist = _levenshtein_distance(domain_part_lower, closest_domain)
        if dist <= 2:
            suggested_email = f"{local_part}@{closest_domain}"
            return jsonify({
                "error": "Invalid email domain. Possible typo detected",
                "suggestion": suggested_email
            }), 400
        return jsonify({"error": "Unsupported email domain"}), 400

    # Сохранение в БД
    session = SessionLocal()
    try:
        existing = session.query(Email).filter_by(email=email).first()
        if existing:
            return jsonify({"error": "Email already subscribed"}), 409

        new_email = Email(email=email)
        session.add(new_email)
        session.commit()

        return jsonify({"message": "Email saved successfully"}), 200
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()

@app.route("/list", methods=["GET"])
def list_emails():
    session = SessionLocal()
    try:
        emails = session.query(Email).order_by(Email.created_at.desc()).all()
        return jsonify([{"email": e.email, "created_at": e.created_at.isoformat()} for e in emails])
    finally:
        session.close()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    host = os.environ.get("HOST", "0.0.0.0")
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug)
