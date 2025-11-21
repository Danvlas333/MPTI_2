from gigachat import GigaChat

# 🔑 Вставь сюда свой токен из SberCloud
TOKEN = "MDE5YTlkYTItODZjYi03MjVjLTkwMjYtZjZmNWE3ZmIxNTBjOmViZmVkYTc0LWJhNjMtNGFmZS05MmY3LTdmOWVkODExZWE3Zg=="

# Инициализация с токеном
with GigaChat(credentials=TOKEN, verify_ssl_certs=False) as giga:

    # Отправляем запрос
    response = giga.chat("Сколько время")
    
    # Выводим ответ
    print("GigaChat отвечает:")
    print(response.choices[0].message.content)