import os
import json
import re
from datetime import datetime, date, timedelta
from sentence_transformers import SentenceTransformer
import numpy as np

# === Настройки ===
DB_PATH = "events_vector_db.json"
MODEL_NAME = "cointegrated/LaBSE-en-ru"
GIGACHAT_CREDENTIALS = "MDE5YTlkYTItODZjYi03MjVjLTkwMjYtZjZmNWE3ZmIxNTBjOmViZmVkYTc0LWJhNjMtNGFmZS05MmY3LTdmOWVkODExZWE3Zg=="

# Ключевые слова для фильтрации
IT_KEYWORDS = [
    "хакатон", "митап", "конференция", "форум", "семинар", "лекция", "воркшоп",
    "ai", "ml", "искусственный интеллект", "машинное обучение",
    "программирование", "data science", "нейросети", "devops",
    "кибербезопасность", "big data", "blockchain"
]

NW_CITIES = [
    "санкт-петербург", "спб", "петербург", "питер", "ленинградская",
    "мурманск", "архангельск", "калининград", "вологда",
    "новгород", "псков", "карелия", "северо-запад",
    "выборг", "гатчина", "петрозаводск", "череповец"
]

# Инициализация модели
print("🧠 Загрузка модели векторизации...")
model = SentenceTransformer(MODEL_NAME, device="cpu")


# === ФИЛЬТРАЦИЯ ===
def is_it_related(text):
    return any(kw in text.lower() for kw in IT_KEYWORDS)

def is_nw_related(text):
    return any(city in text.lower() for city in NW_CITIES)


# === ПАРСИНГ ТАБЛИЦЫ ИЗ ОТВЕТА GIGACHAT ===
def parse_gigachat_response(text):
    """Извлекает мероприятия из табличного ответа GigaChat"""
    events = []
    lines = text.strip().split('\n')
    in_table = False
    
    for line in lines:
        line = line.strip()
        if line.startswith('|') and '|' in line[1:]:
            if '---' in line:
                in_table = True
                continue
            if not in_table:
                continue
                
            parts = [p.strip() for p in line.split('|') if p.strip()]
            if len(parts) >= 4:
                date_str, event_name, city, description, *_ = parts
                # Пропускаем заголовки
                if 'дата' in date_str.lower() or 'мероприятие' in event_name.lower():
                    continue
                # Извлекаем дату в формате YYYY-MM-DD
                date_match = re.search(r'\d{4}-\d{2}-\d{2}', date_str)
                if not date_match:
                    print(f"⚠️ Пропущена строка без корректной даты: {line}")
                    continue
                event_date = date_match.group(0)
                full_text = f"{city}. {event_name}. {description}"
                events.append({
                    "text": full_text,
                    "date": event_date
                })
                print(f"📋 Найдено: {event_name} | {city} | {event_date}")
    return events


# === ЗАПРОС К GIGACHAT ЗА СПИСКОМ МЕРОПРИЯТИЙ ===
def fetch_raw_events_from_gigachat():
    """Возвращает список событий в формате [{'text': '...', 'date': 'YYYY-MM-DD'}]"""
    try:
        from gigachat import GigaChat
        today = date.today()
        end_date = today + timedelta(days=180)  # 6 месяцев
        
        prompt = f"""
Ты — организатор IT-мероприятий в СЗФО. Придумай 12–15 **вымышленных, но правдоподобных** мероприятий 
в период с {today.strftime('%Y-%m-%d')} по {end_date.strftime('%Y-%m-%d')}.

Правила:
1. Каждое мероприятие — уникальное, с конкретной датой.
2. Дата проведения — **один день**, в формате "YYYY-MM-DD".
3. Города только из СЗФО: СПб, Калининград, Мурманск, Архангельск, Вологда, Новгород, Псков, Петрозаводск.
4. Темы: AI, ML, хакатоны, митапы, конференции, кибербезопасность, веб-разработка.
5. Названия — реалистичные, как настоящие события.

Верни ТОЛЬКО таблицу в формате:

| Дата | Мероприятие | Город | Описание |
|------|-------------|-------|----------|

Без пояснений, без markdown-обрамления.
"""
        with GigaChat(credentials=GIGACHAT_CREDENTIALS, verify_ssl_certs=False, timeout=30) as giga:
            resp = giga.chat(prompt)
            return parse_gigachat_response(resp.choices[0].message.content)
    except Exception as e:
        print(f"❌ Ошибка запроса к GigaChat: {e}")
        return []


# === ОСНОВНАЯ ФУНКЦИЯ ===
def main():
    print("🔍 Запрос мероприятий у GigaChat...")
    raw_events = fetch_raw_events_from_gigachat()
    print(f"✅ Получено {len(raw_events)} мероприятий")

    # Загрузка существующей базы
    if os.path.exists(DB_PATH):
        with open(DB_PATH, "r", encoding="utf-8") as f:
            db = json.load(f)
        print(f"📁 Загружено {len(db)} существующих мероприятий")
    else:
        db = []
        print("📁 Создана новая база")

    today = date.today()
    six_months = today + timedelta(days=180)
    added = 0

    print(f"\n🔄 Обработка {len(raw_events)} мероприятий...")
    for i, ev in enumerate(raw_events, 1):
        print(f"\n--- [{i}/{len(raw_events)}] ---")
        text = ev["text"]
        clarified_date = ev.get("date")

        print(f"📝 Текст: {text[:70]}...")

        # Проверка корректности даты
        if not clarified_date or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', clarified_date):
            print("❌ Пропущено: отсутствует или некорректна дата")
            continue

        # Проверка актуальности
        try:
            event_date = datetime.strptime(clarified_date, "%Y-%m-%d").date()
            if event_date < today or event_date > six_months:
                print(f"❌ Пропущено: дата вне диапазона ({event_date})")
                continue
        except Exception as e:
            print(f"❌ Пропущено: ошибка парсинга даты {clarified_date} — {e}")
            continue

        # Проверка дубликатов по вектору
        is_duplicate = False
        new_vec = model.encode(text, normalize_embeddings=True)
        for item in db:
            sim = float(np.dot(np.array(item["vector"]), new_vec))
            if sim >= 0.92:
                is_duplicate = True
                break
        if is_duplicate:
            print("❌ Пропущено: дубликат")
            continue

        # Добавление в базу
        db.append({
            "date": clarified_date,
            "text": text,
            "vector": new_vec.tolist()
        })
        added += 1
        print(f"✅ ДОБАВЛЕНО: {text[:60]}... | {clarified_date}")

    # Сохранение
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    print(f"\n🎯 ИТОГ: Добавлено {added} мероприятий. Всего в базе: {len(db)}")
    print(f"📁 Файл сохранён: {os.path.abspath(DB_PATH)}")


if __name__ == "__main__":
    main()