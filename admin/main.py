from flask import Flask, request, render_template, redirect, url_for, flash
import os
import re
import secrets
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = 'sber-admin-secret-key'

# База данных пользователей
DATABASE = "users.db"

# Настройки email
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_LOGIN = "v1asovd4ny@gmail.com"
SMTP_PASSWORD = "fild pggg xbjc acba"

# URL основного приложения (порт 5000 — чат и мероприятия)
MAIN_APP_URL = "http://127.0.0.1:5000"


def init_db():
    if os.path.exists(DATABASE):
        return
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'user',
            fio TEXT,
            email TEXT,
            manager_login TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_login ON users(login);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_type ON users(type);")

    # Админ по умолчанию
    cursor.execute("""
        INSERT INTO users (login, password, type, fio, email)
        VALUES (?, ?, ?, ?, ?)
    """, ("admin", "admin123", "admin", "Администратор Системы", "admin@example.com"))

    conn.commit()
    conn.close()
    print("✅ База данных users.db инициализирована.")


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def generate_login(fio: str) -> str:
    parts = fio.strip().split()
    if len(parts) < 2:
        return re.sub(r'[^a-zа-яё0-9]', '', fio.lower())[:20]
    last, first = parts[0], parts[1]
    login = (last + first[0]).lower()
    return re.sub(r'[^a-zа-яё0-9]', '', login)[:20]


def user_exists(login: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE login = ?", (login,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def get_all_users():
    conn = get_db_connection()
    users = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return [dict(row) for row in users]


def get_user_by_login(login: str):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE login = ?", (login,)).fetchone()
    conn.close()
    return dict(user) if user else None


def get_managers():
    conn = get_db_connection()
    managers = conn.execute("SELECT login, fio FROM users WHERE type = 'руководитель'").fetchall()
    conn.close()
    return [dict(row) for row in managers]


def create_user_in_db(fio, user_type, email, manager_login=None):
    base_login = generate_login(fio)
    login = base_login
    counter = 1
    while user_exists(login):
        login = f"{base_login}{counter}"
        counter += 1

    password = secrets.token_urlsafe(8)

    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO users (login, password, type, fio, email, manager_login)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (login, password, user_type, fio, email, manager_login or ''))
        conn.commit()
    finally:
        conn.close()

    return login, password


def delete_user_from_db(login: str):
    if login == 'admin':
        raise ValueError("Нельзя удалить администратора")
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM users WHERE login = ?", (login,))
        conn.commit()
    finally:
        conn.close()


def send_welcome_email(to_email, fio, user_type, login, password):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Добро пожаловать в СберКалендарь!"
        msg["From"] = SMTP_LOGIN
        msg["To"] = to_email

        position = "Руководитель" if user_type == "руководитель" else "Сотрудник"

        # Используем MAIN_APP_URL — ссылка на основное приложение (порт 5000)
        html = f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
          <meta charset="UTF-8">
          <style>
            body {{ 
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
              background: #f9fafb;
              margin: 0;
              padding: 0;
            }}
            .container {{
              max-width: 650px;
              margin: 40px auto;
              background: white;
              border-radius: 16px;
              overflow: hidden;
              box-shadow: 0 10px 30px rgba(0,0,0,0.08);
            }}
            .header {{
              background: linear-gradient(135deg, #005FAD 0%, #00A884 100%);
              padding: 32px 24px;
              text-align: center;
            }}
            .logo {{
              font-size: 28px;
              font-weight: 800;
              color: white;
              letter-spacing: -0.5px;
            }}
            .content {{
              padding: 36px;
              color: #1e293b;
            }}
            .greeting {{
              font-size: 20px;
              margin-bottom: 24px;
              line-height: 1.4;
            }}
            .card {{
              background: #f0fdf7;
              border: 1px solid #bbf7d0;
              border-radius: 12px;
              padding: 20px;
              margin: 24px 0;
            }}
            .row {{
              display: flex;
              margin: 10px 0;
            }}
            .label {{
              font-weight: 600;
              color: #007a5d;
              min-width: 120px;
            }}
            .value {{
              color: #0f172a;
              word-break: break-all;
            }}
            .btn {{
              display: inline-block;
              background: #00A884;
              color: white;
              text-decoration: none;
              padding: 12px 28px;
              border-radius: 10px;
              font-weight: 600;
              margin-top: 20px;
            }}
            .footer {{
              text-align: center;
              padding: 24px;
              color: #64748b;
              font-size: 14px;
              border-top: 1px solid #e2e8f0;
            }}
          </style>
        </head>
        <body>
          <div class="container">
            <div class="header">
              <div class="logo">СБЕРКАЛЕНДАРЬ</div>
            </div>
            <div class="content">
              <p class="greeting">Здравствуйте, {fio}!</p>
              <p>Вам создана учётная запись в системе <strong>СберКалендарь</strong>. Используйте данные ниже для входа:</p>
              
              <div class="card">
                <div class="row">
                  <span class="label">Должность:</span>
                  <span class="value">{position}</span>
                </div>
                <div class="row">
                  <span class="label">Логин:</span>
                  <span class="value">{login}</span>
                </div>
                <div class="row">
                  <span class="label">Пароль:</span>
                  <span class="value">{password}</span>
                </div>
              </div>

              <a href="{MAIN_APP_URL}" class="btn">Перейти в СберКалендарь</a>
            </div>
            <div class="footer">
              Это письмо сгенерировано автоматически. Не отвечайте на него.
            </div>
          </div>
        </body>
        </html>
        """

        part = MIMEText(html, "html")
        msg.attach(part)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_LOGIN, SMTP_PASSWORD.replace(" ", ""))
            server.send_message(msg)

        print(f"✅ Письмо отправлено на {to_email}")
        return True

    except Exception as e:
        print(f"❌ Ошибка отправки email: {e}")
        return False


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_input = request.form.get('login', '').strip()
        password_input = request.form.get('password', '').strip()
        user = get_user_by_login(login_input)
        if user and user['password'] == password_input:
            if user['type'] == 'admin':
                return redirect(url_for('admin'))
            else:
                flash('Доступ разрешён только администраторам.', 'error')
        else:
            flash('Неверный логин или пароль.', 'error')
    return render_template('login.html')


@app.route('/admin')
def admin():
    users = get_all_users()
    managers = get_managers()
    return render_template('admin.html', users=users, managers=managers)


@app.route('/create_user', methods=['POST'])
def create_user():
    fio = request.form.get('fio', '').strip()
    user_type = request.form.get('type', '').strip()
    email = request.form.get('email', '').strip().lower()
    manager_login = request.form.get('manager', '').strip()

    if not fio or not user_type or not email:
        flash('Все поля обязательны.', 'error')
        return redirect(url_for('admin'))

    if user_type == 'user' and not manager_login:
        flash('Выберите руководителя для обычного пользователя.', 'error')
        return redirect(url_for('admin'))

    if user_type == 'user':
        manager = get_user_by_login(manager_login)
        if not manager or manager['type'] != 'руководитель':
            flash('Выбранный руководитель не найден или не является руководителем.', 'error')
            return redirect(url_for('admin'))

    try:
        login, password = create_user_in_db(fio, user_type, email, manager_login if user_type == 'user' else None)
        send_welcome_email(email, fio, user_type, login, password)
        flash(f'Пользователь создан! Пароль отправлен на почту {email}.', 'success')
    except Exception as e:
        flash(f'Ошибка при создании пользователя: {e}', 'error')

    return redirect(url_for('admin'))


@app.route('/delete_user', methods=['POST'])
def delete_user():
    login_to_delete = request.form.get('login')
    if not login_to_delete:
        flash('Не указан логин.', 'error')
        return redirect(url_for('admin'))

    try:
        delete_user_from_db(login_to_delete)
        flash('Пользователь успешно удалён.', 'success')
    except ValueError as ve:
        flash(str(ve), 'error')
    except Exception as e:
        flash(f'Ошибка при удалении: {e}', 'error')

    return redirect(url_for('admin'))


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5001, debug=True)
