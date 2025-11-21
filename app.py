from flask import Flask, request, jsonify, render_template
import json
import numpy as np
import re
import os
import urllib3
from sentence_transformers import SentenceTransformer
import pandas as pd

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DB_PATH = "events_vector_db.json"
MODEL_NAME = "cointegrated/LaBSE-en-ru"
TOP_K = 10
GIGACHAT_CREDENTIALS = "MDE5YTlkYTItODZjYi03MjVjLTkwMjYtZjZmNWE3ZmIxNTBjOmViZmVkYTc0LWJhNjMtNGFmZS05MmY3LTdmOWVkODExZWE3Zg=="

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
model = SentenceTransformer(MODEL_NAME, device="cpu")

def load_users():
    try:
        df = pd.read_excel('log.xlsx')
        users = {}
        for _, row in df.iterrows():
            login = str(row['login']).strip() if pd.notna(row['login']) else ''
            password = str(row['pasword']).strip() if pd.notna(row['pasword']) else ''
            user_type = str(row['type']).strip() if pd.notna(row['type']) else 'user'
            if login and password:
                users[login] = {'password': password, 'type': user_type}
        return users
    except Exception as e:
        print(f"Ошибка загрузки пользователей: {e}")
        return {}

USERS = load_users()

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

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login = request.form.get('login', '').strip()
        password = request.form.get('password', '').strip()
        user = USERS.get(login)
        if user and user['password'] == password:
            return render_template('index.html')
        else:
            return render_template('login.html', error="Неверный логин или пароль")
    return render_template('login.html')

@app.route('/send_message', methods=['POST'])
def send_message():
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
                "response": "Ваш запрос не относится к теме IT-мероприятий...\nОбратитесь к GigaChat для общих вопросов.",
                "events": []
            })

        candidates = search_events(user_query, DB_PATH, TOP_K, use_geo=True)

        if not candidates:
            response_text = "К сожалению, по вашему запросу ничего не найдено."
        else:
            lines = [f"{i+1}. {item['date']} — {item['text']}" for i, item in enumerate(candidates)]
            response_text = "Вот подходящие мероприятия:\n" + "\n".join(lines)

        events_for_calendar = [{"date": ev["date"], "text": ev["text"]} for ev in candidates]

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
                "response": "Ваш запрос не относится к теме IT-мероприятий...\nОбратитесь к GigaChat для общих вопросов.",
                "events": []
            })

        candidates = search_events(user_friendly_query, DB_PATH, TOP_K, use_geo=True)

        if not candidates:
            response_text = "К сожалению, по вашему запросу ничего не найдено."
        else:
            lines = [f"{i+1}. {item['date']} — {item['text']}" for i, item in enumerate(candidates)]
            response_text = "Вот подходящие мероприятия:\n" + "\n".join(lines)

        events_for_calendar = [{"date": ev["date"], "text": ev["text"]} for ev in candidates]

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)