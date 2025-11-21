from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import json
import numpy as np
import re
import os
import urllib3
from sentence_transformers import SentenceTransformer
from datetime import datetime, date
import sqlite3
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === Настройки ===
DB_PATH = "events_vector_db.json"
USERS_DB = "users.db"
MODEL_NAME = "cointegrated/LaBSE-en-ru"
TOP_K = 10
GIGACHAT_CREDENTIALS = "MDE5YTlkYTItODZjYi03MjVjLTkwMjYtZjZmNWE3ZmIxNTBjOmViZmVkYTc0LWJhNjMtNGFmZS05MmY3LTdmOWVkODExZWE3Zg=="

# Email настройки
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_LOGIN = "v1asovd4ny@gmail.com"
SMTP_PASSWORD = "fild pggg xbjc acba"
ADMIN_EMAIL = "v1asovd4ny@gamil.com"

NORTHWEST_CITIES = [
    "санкт-петербург", "спб", "петербург", "деловой петербург", "питер",
    "всеволожск", "гатчина", "каменногорск", "кириши", "кольцово", "луза",
    "выборг", "тосно", "волхов", "сосновый бор",
    "петрозаводск", "кондопога", "беломорск", "олонец",
    "мурманск", "апатиты", "ковдор", "мончегорск", "полярные зори",
    "архангельск", "новодвинск", "коряжма", "котлас", "нарьян-мар",
    "калининград", "черняховск", "гусев", "балтийск", "советск",
    "великий новгород", "новгород", "боровичи", "старая русса",
    "псков", "великие луки", "остров", "невель",
    "вологда", "череповец", "грязовец", "кириллов",
]

STRICT_KEYWORDS = [
    "хакатон", "митап", "форум", "конференция", "семинар",
    "лекция", "премия", "сессия", "встреча", "круглый стол"
]

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
model = SentenceTransformer(MODEL_NAME, device="cpu")

# === Вспомогательные функции ===
def parse_date_to_date_obj(date_str):
    if not date_str:
        return None
    s = str(date_str).strip()
    if not s:
        return None

    range_split = re.split(r'\s*[-–—]\s*', s, maxsplit=1)
    first_part = range_split[0].strip()

    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', first_part):
            return datetime.strptime(first_part, "%Y-%m-%d").date()
    except:
        pass

    s_norm = re.sub(r'[./]', '.', first_part)
    clean = re.sub(r'[^\d.]', '', s_norm)
    parts = [p for p in clean.split('.') if p]
    if len(parts) == 3:
        d, m, y = parts
        if len(y) == 2:
            y = '20' + y
        if len(d) <= 2 and len(m) <= 2 and len(y) == 4:
            try:
                return datetime.strptime(f"{d}.{m}.{y}", "%d.%m.%Y").date()
            except ValueError:
                pass

    month_map = {
        'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
        'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
        'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
    }
    text_clean = re.sub(r'[^\w\s]', ' ', first_part.lower())
    match = re.search(r'(\d{1,2})\s+([а-яё]+)(?:\s+(\d{4}))?', text_clean)
    if match:
        day, month_word, year = match.groups()
        month_num = month_map.get(month_word)
        if month_num:
            year = year or "2025"
            try:
                return datetime(year=int(year), month=month_num, day=int(day)).date()
            except ValueError:
                pass

    return None

def is_future_or_today(date_str):
    event_date = parse_date_to_date_obj(date_str)
    if event_date is None:
        return False
    return event_date >= date.today()

def get_user_from_db(login):
    if not os.path.exists(USERS_DB):
        return None
    conn = sqlite3.connect(USERS_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT login, password, type, fio, manager_login FROM users WHERE login = ?", (login,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# === Векторный поиск (без изменений) ===
def is_it_related(query: str) -> bool:
    query_lower = query.lower().strip()
    if extract_northwest_geo_hints(query):
        return True
    if re.search(r'\b\d{1,2}[./]\d{1,2}', query_lower) or re.search(r'\b202[456]\b', query_lower):
        return True
    try:
        from gigachat import GigaChat
        prompt = f"""Относится ли запрос к IT-мероприятиям (хакатоны, митапы, конференции и т.п.)?
Ответь строго: "да" или "нет".
Запрос: «{query}»
Ответ:"""
        with GigaChat(credentials=GIGACHAT_CREDENTIALS, verify_ssl_certs=False) as giga:
            resp = giga.chat(prompt)
        return "да" in resp.choices[0].message.content.lower()
    except Exception as e:
        print(f"GigaChat недоступен: {e}")
        return True

def load_vector_db(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        db = json.load(f)
    for item in db:
        item["vector"] = np.array(item["vector"], dtype=np.float32)
    return db

def extract_northwest_geo_hints(query: str):
    query_norm = query.lower().replace("-", " ")
    if "калининрад" in query_norm:
        query_norm = query_norm.replace("калининрад", "калининград")
    matches = []
    for city in NORTHWEST_CITIES:
        city_norm = city.lower().replace("-", " ")
        if city_norm in query_norm:
            matches.append(city)
    return matches

def contains_keyword(text: str, keyword: str) -> bool:
    pattern = r'\b' + re.escape(keyword)
    return bool(re.search(pattern, text, re.IGNORECASE))

def apply_strict_type_filter(query: str, event_text: str) -> bool:
    query_lower = query.lower()
    for kw in STRICT_KEYWORDS:
        if kw in query_lower:
            if not contains_keyword(event_text, kw):
                return False
    return True

def search_events(query: str, db_path: str, top_k: int, use_geo: bool = True):
    db = load_vector_db(db_path)
    if not db:
        return []
    query_vec = model.encode(query, normalize_embeddings=True)
    vectors = np.array([item["vector"] for item in db])
    if query_vec.shape[0] != vectors.shape[1]:
        raise ValueError(f"Несовместимые размерности: {query_vec.shape[0]} vs {vectors.shape[1]}")
    similarities = np.dot(vectors, query_vec)
    top_indices = np.argsort(similarities)[::-1]
    results = []
    geo_hints = extract_northwest_geo_hints(query) if use_geo else []
    for idx in top_indices:
        item = db[idx]
        full_text = item["text"]
        if not apply_strict_type_filter(query, full_text):
            continue
        if geo_hints:
            event_context = (item["date"] + " " + full_text).lower()
            if not any(city.lower() in event_context for city in geo_hints):
                continue
        results.append({
            "date": item["date"],
            "text": full_text,
            "score": float(similarities[idx])
        })
        if len(results) >= top_k:
            break
    return results

# === Заявки ===
REQUESTS_FILE = "registration_requests.json"

def load_requests():
    if not os.path.exists(REQUESTS_FILE):
        return []
    with open(REQUESTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_requests(reqs):
    with open(REQUESTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(reqs, f, ensure_ascii=False, indent=2)

# === Email уведомление ===
def send_approval_email(user_fio, event_text, manager_fio):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "✅ Заявка на мероприятие одобрена"
        msg["From"] = SMTP_LOGIN
        msg["To"] = ADMIN_EMAIL

        html = f"""
        <html>
        <body>
          <p>Руководитель <b>{manager_fio}</b> одобрил заявку:</p>
          <div style="background:#f0f0f0; padding:12px; margin:12px 0; border-left:4px solid #2ed573;">
            <p><b>Пользователь:</b> {user_fio}</p>
            <p><b>Мероприятие:</b> {event_text}</p>
          </div>
          <p>Система СберКалендарь</p>
        </body>
        </html>
        """
        part = MIMEText(html, "html")
        msg.attach(part)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_LOGIN, SMTP_PASSWORD.replace(" ", ""))
            server.send_message(msg)
        print(f"✅ Письмо отправлено админу: {ADMIN_EMAIL}")
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки email админу: {e}")
        return False

# === Роуты ===

@app.route('/')
def index():
    if 'user_login' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', user_type=session['user_type'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login = request.form.get('login', '').strip()
        password = request.form.get('password', '').strip()
        user = get_user_from_db(login)
        if user and user['password'] == password:
            session['user_login'] = user['login']
            session['user_type'] = user['type']
            session['user_fio'] = user.get('fio', login)
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Неверный логин или пароль")
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/send_message', methods=['POST'])
def send_message():
    if 'user_login' not in session:
        return jsonify({"success": False, "response": "Не авторизован"}), 401
    data = request.get_json()
    user_query = data.get("message", "").strip()
    if not user_query or user_query == "📎 загрузка файла":
        return jsonify({
            "success": True,
            "response": "Пожалуйста, введите запрос о мероприятии.",
            "events": []
        })
    try:
        if not is_it_related(user_query):
            return jsonify({
                "success": True,
                "response": "Ваш запрос не относится к теме IT-мероприятий...",
                "events": []
            })
        candidates = search_events(user_query, DB_PATH, TOP_K * 3, use_geo=True)
        future_candidates = [ev for ev in candidates if is_future_or_today(ev["date"])]
        if not candidates:
            response_text = "К сожалению, по вашему запросу ничего не найдено."
        elif not future_candidates:
            response_text = "По вашему запросу найдены только мероприятия, которые уже прошли. Актуальных событий нет."
        else:
            future_candidates = future_candidates[:TOP_K]
            lines = [f"{i+1}. {item['date']} — {item['text']}" for i, item in enumerate(future_candidates)]
            response_text = "Вот подходящие мероприятия:\n" + "\n".join(lines)
        events_for_calendar = []
        for ev in future_candidates:
            d_obj = parse_date_to_date_obj(ev["date"])
            if d_obj:
                iso_date = d_obj.strftime("%Y-%m-%d")
                events_for_calendar.append({"date": iso_date, "text": ev["text"]})
        return jsonify({
            "success": True,
            "response": response_text,
            "events": events_for_calendar
        })
    except Exception as e:
        print(f"Ошибка в /send_message: {e}")
        return jsonify({
            "success": True,
            "response": "Ошибка при обработке запроса.",
            "events": []
        })

@app.route('/send_filters', methods=['POST'])
def send_filters():
    if 'user_login' not in session:
        return jsonify({"success": False, "response": "Не авторизован"}), 401
    data = request.get_json()
    filters = data.get("filters", {})
    parts = []
    if filters.get("type"): parts.append(filters["type"])
    if filters.get("city"): parts.append(filters["city"])
    if filters.get("date"): parts.append(f"дата {filters['date']}")
    if filters.get("guests"): parts.append(f"гостей {filters['guests']}")
    if filters.get("speakers"): parts.append(f"спикеров {filters['speakers']}")
    if not parts:
        return jsonify({
            "success": True,
            "response": "Выберите хотя бы один фильтр.",
            "events": []
        })
    user_friendly_query = " ".join(parts)
    if len(parts) == 1 and filters.get("city") and not filters.get("type"):
        user_friendly_query = f"Мероприятия в {filters['city']}"
    try:
        if not is_it_related(user_friendly_query):
            return jsonify({
                "success": True,
                "response": "Ваш запрос не относится к теме IT-мероприятий...",
                "events": []
            })
        candidates = search_events(user_friendly_query, DB_PATH, TOP_K * 3, use_geo=True)
        future_candidates = [ev for ev in candidates if is_future_or_today(ev["date"])]
        if not candidates:
            response_text = "К сожалению, по вашему запросу ничего не найдено."
        elif not future_candidates:
            response_text = "По вашему запросу найдены только мероприятия, которые уже прошли. Актуальных событий нет."
        else:
            future_candidates = future_candidates[:TOP_K]
            lines = [f"{i+1}. {item['date']} — {item['text']}" for i, item in enumerate(future_candidates)]
            response_text = "Вот подходящие мероприятия:\n" + "\n".join(lines)
        events_for_calendar = []
        for ev in future_candidates:
            d_obj = parse_date_to_date_obj(ev["date"])
            if d_obj:
                iso_date = d_obj.strftime("%Y-%m-%d")
                events_for_calendar.append({"date": iso_date, "text": ev["text"]})
        return jsonify({
            "success": True,
            "response": response_text,
            "events": events_for_calendar
        })
    except Exception as e:
        print(f"Ошибка в /send_filters: {e}")
        return jsonify({
            "success": True,
            "response": "Ошибка при обработке фильтров.",
            "events": []
        })

@app.route('/get_future_events')
def get_future_events():
    if 'user_login' not in session:
        return jsonify({"success": True, "events": []})
    try:
        if not os.path.exists(DB_PATH):
            return jsonify({"success": True, "events": []})
        with open(DB_PATH, "r", encoding="utf-8") as f:
            db = json.load(f)
        events = []
        for item in db:
            d_obj = parse_date_to_date_obj(item.get("date", ""))
            if d_obj and d_obj >= date.today():
                events.append({
                    "date": d_obj.strftime("%Y-%m-%d"),
                    "text": item.get("text", "").strip()
                })
        return jsonify({"success": True, "events": events})
    except Exception as e:
        print("Ошибка в /get_future_events:", e)
        return jsonify({"success": False, "events": []})

@app.route('/get_all_events')
def get_all_events():
    if 'user_login' not in session:
        return jsonify({"success": False, "error": "Не авторизован"}), 401
    try:
        if not os.path.exists(DB_PATH):
            return jsonify({"success": True, "active": [], "past": []})
        with open(DB_PATH, "r", encoding="utf-8") as f:
            db = json.load(f)
        today = date.today()
        active_events = []
        past_events = []
        for item in db:
            raw_date = item.get("date", "")
            event_text = item.get("text", "").strip()
            event_date_obj = parse_date_to_date_obj(raw_date)
            event_type = ""
            for kw in STRICT_KEYWORDS:
                if kw.lower() in event_text.lower():
                    event_type = kw
                    break
            city = ""
            text_lower = event_text.lower()
            for c in NORTHWEST_CITIES:
                if c in text_lower:
                    city = c.capitalize()
                    break
            display_date = raw_date
            if event_date_obj:
                display_date = event_date_obj.strftime("%d.%m.%y")
            event_data = {
                "title": event_text,
                "description": "",
                "date": display_date,
                "city": city,
                "type": event_type,
                "guests_count": 0,
                "speakers_count": 0
            }
            if event_date_obj and event_date_obj >= today:
                active_events.append(event_data)
            else:
                past_events.append(event_data)
        return jsonify({"success": True, "active": active_events, "past": past_events})
    except Exception as e:
        print("Ошибка в /get_all_events:", e)
        return jsonify({"success": False, "error": "Не удалось загрузить мероприятия"}), 500

# === ЗАЯВКИ ===
@app.route('/request_registration', methods=['POST'])
def request_registration():
    if 'user_login' not in session:
        return jsonify({"success": False, "message": "Не авторизован"}), 401

    data = request.get_json()
    event_date = data.get("event_date")
    event_text = data.get("event_text")

    if not event_date or not event_text:
        return jsonify({"success": False, "message": "Не указаны данные мероприятия."})

    user_type = session['user_type']
    user = get_user_from_db(session['user_login'])

    # Руководитель регистрируется сразу
    if user_type in ('руководитель', 'admin'):
        return jsonify({"success": True, "message": "Вы успешно зарегистрированы на мероприятие."})

    # Обычный пользователь — отправляет заявку
    if user_type == 'user':
        manager_login = user.get('manager_login')
        if not manager_login:
            return jsonify({"success": False, "message": "У вас нет назначенного руководителя."})

        req = {
            "user_login": session['user_login'],
            "user_fio": session['user_fio'],
            "manager_login": manager_login,
            "event_date": event_date,
            "event_text": event_text,
            "status": "pending",
            "timestamp": datetime.now().isoformat()
        }
        requests = load_requests()
        requests.append(req)
        save_requests(requests)
        return jsonify({"success": True, "message": "Заявка отправлена вашему руководителю."})
    
    return jsonify({"success": False, "message": "Недопустимый тип пользователя."})

@app.route('/get_manager_requests')
def get_manager_requests():
    if 'user_login' not in session:
        return jsonify({"requests": []})
    if session['user_type'] not in ('руководитель', 'admin'):
        return jsonify({"requests": []})
    requests = load_requests()
    my_requests = [r for r in requests if r.get('manager_login') == session['user_login'] and r.get('status') == 'pending']
    return jsonify({"requests": my_requests})

@app.route('/update_request', methods=['POST'])
def update_request():
    if 'user_login' not in session:
        return jsonify({"success": False})
    if session['user_type'] not in ('руководитель', 'admin'):
        return jsonify({"success": False})

    data = request.get_json()
    user_login = data.get('user_login')
    event_date = data.get('event_date')
    status = data.get('status')

    if status not in ('approved', 'rejected'):
        return jsonify({"success": False})

    requests = load_requests()
    manager_fio = session['user_fio']
    for r in requests:
        if r.get('user_login') == user_login and r.get('event_date') == event_date and r.get('manager_login') == session['user_login']:
            r['status'] = status
            r['handled_by'] = session['user_login']
            r['handled_at'] = datetime.now().isoformat()
            if status == 'approved':
                send_approval_email(r['user_fio'], r['event_text'], manager_fio)
            break
    save_requests(requests)
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
