import json
import numpy as np
import re
import urllib3
from sentence_transformers import SentenceTransformer

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============== Настройки ==============
QUERY = "Хакатон в Петербурге"
DB_PATH = "events_vector_db.json"
TOP_K = 10
MODEL_NAME = "cointegrated/LaBSE-en-ru"  # точная модель для RU
USE_GEO_FILTER = False

# Слова, по которым применяется строгий фильтр: событие должно содержать это слово
STRICT_KEYWORDS = [
    "хакатон", "митап", "форум", "конференция", "семинар",
    "лекция", "премия", "сессия", "встреча", "круглый стол"
]

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

# ============== Вспомогательные функции ==============

def load_vector_db(path):
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
    """Проверяет, содержит ли текст слово keyword как отдельное слово (с поддержкой падежей)."""
    pattern = r'\b' + re.escape(keyword)
    return bool(re.search(pattern, text, re.IGNORECASE))

def apply_strict_type_filter(query: str, event_text: str) -> bool:
    """Возвращает True, если событие проходит фильтр по типу мероприятия."""
    query_lower = query.lower()
    for kw in STRICT_KEYWORDS:
        if kw in query_lower:
            if not contains_keyword(event_text, kw):
                return False
    return True

def search_events(query: str, db_path: str, top_k: int, use_geo: bool = True):
    # 1. Загрузка модели и базы
    model = SentenceTransformer(MODEL_NAME, device="cpu")
    db = load_vector_db(db_path)

    # 2. Векторизация запроса
    query_vec = model.encode(query, normalize_embeddings=True)

    # 3. Вычисление сходства
    vectors = np.array([item["vector"] for item in db])
    similarities = np.dot(vectors, query_vec)

    # 4. Сортировка по убыванию
    top_indices = np.argsort(similarities)[::-1]

    # 5. Фильтрация и сбор результатов
    results = []
    geo_hints = extract_northwest_geo_hints(query) if use_geo else []

    for idx in top_indices:
        item = db[idx]
        full_text = item["text"]

        # Строгий фильтр по типу мероприятия
        if not apply_strict_type_filter(query, full_text):
            continue

        # Гео-фильтр (если город указан в запросе)
        if geo_hints:
            event_context = (item["date"] + " " + full_text).lower()
            if not any(city.lower() in event_context for city in geo_hints):
                continue

        results.append({
            "date": item["date"],
            "text": full_text,
            "score": round(float(similarities[idx]), 4)
        })

        if len(results) >= top_k:
            break

    return results

# ============== Запуск ==============
if __name__ == "__main__":
    results = search_events(QUERY, DB_PATH, TOP_K, use_geo=USE_GEO_FILTER)

    print(f"Найдено {len(results)} событий по запросу: «{QUERY}»\n")
    for i, item in enumerate(results, 1):
        print(f"{i}. [{item['score']:.4f}] {item['date']} — {item['text']}")

    # Для интеграции на сайт (чистый JSON без score)
    final_output = [{"date": item["date"], "text": item["text"]} for item in results]
    # print("\n" + json.dumps(final_output, ensure_ascii=False, indent=2))