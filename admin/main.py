from flask import Flask, request, render_template, redirect, url_for, flash
import pandas as pd
import os
import re
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = 'sber-admin-secret-key'

EXCEL_FILE = r"G:\IT_P\log.xlsx"

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_LOGIN = "v1asovd4ny@gmail.com"     
SMTP_PASSWORD = "fild pggg xbjc acba"      

def init_excel():
    if not os.path.exists(EXCEL_FILE):
        df = pd.DataFrame(columns=['login', 'pasword', 'type', 'fio', 'email', 'manager'])
        df.to_excel(EXCEL_FILE, index=False)

def load_users():
    try:
        df = pd.read_excel(EXCEL_FILE, dtype=str).fillna('')
        df['login'] = df['login'].astype(str).str.strip()
        df['pasword'] = df['pasword'].astype(str).str.strip()
        df['type'] = df['type'].astype(str).str.strip().str.lower()
        return df
    except Exception as e:
        print(f"Ошибка загрузки Excel: {e}")
        return pd.DataFrame(columns=['login', 'pasword', 'type', 'fio', 'email', 'manager'])

def save_users(df):
    df.to_excel(EXCEL_FILE, index=False)

def generate_login(fio: str) -> str:
    parts = fio.strip().split()
    if len(parts) < 2:
        return re.sub(r'[^a-zа-яё0-9]', '', fio.lower())[:20]
    last, first = parts[0], parts[1]
    login = (last + first[0]).lower()
    login = re.sub(r'[^a-zа-яё0-9]', '', login)
    return login[:20]

def send_welcome_email(to_email, fio, user_type, login, password):
    """Отправляет красивое письмо через Gmail на ЛЮБУЮ почту."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Добро пожаловать в СберКалендарь!"
        msg["From"] = SMTP_LOGIN
        msg["To"] = to_email

        position = "Руководитель" if user_type == "руководитель" else "Сотрудник"

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

              <a href="http://127.0.0.1:5000/" class="btn">Перейти в СберКалендарь</a>
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

        print(f"✅ Письмо отправлено на {to_email} через Gmail")
        return True

    except Exception as e:
        print(f"❌ Ошибка Gmail: {e}")
        return False

init_excel()

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_input = request.form.get('login', '').strip()
        password_input = request.form.get('password', '').strip()

        df = load_users()
        user_row = df[df['login'] == login_input]

        if not user_row.empty:
            stored_password = user_row.iloc[0]['pasword']
            user_type = user_row.iloc[0]['type']
            if stored_password == password_input:
                if user_type == 'admin':
                    return redirect(url_for('admin'))
                else:
                    flash('Доступ разрешён только администраторам.', 'error')
            else:
                flash('Неверный пароль.', 'error')
        else:
            flash('Пользователь не найден.', 'error')
    return render_template('login.html')

@app.route('/admin')
def admin():
    df = load_users()
    users = df.to_dict(orient='records')
    managers = df[df['type'] == 'руководитель'][['login', 'fio']].to_dict(orient='records')
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

    df = load_users()

    base_login = generate_login(fio)
    login = base_login
    counter = 1
    while not df[df['login'] == login].empty:
        login = f"{base_login}{counter}"
        counter += 1

    password = secrets.token_urlsafe(8)

    if user_type == 'user':
        if not manager_login:
            flash('Выберите руководителя для обычного пользователя.', 'error')
            return redirect(url_for('admin'))
        if df[(df['login'] == manager_login) & (df['type'] == 'руководитель')].empty:
            flash('Выбранный руководитель не найден.', 'error')
            return redirect(url_for('admin'))

    new_user = pd.DataFrame([{
        'login': login,
        'pasword': password,
        'type': user_type,
        'fio': fio,
        'email': email,
        'manager': manager_login if user_type == 'user' else ''
    }])

    df = pd.concat([df, new_user], ignore_index=True)
    save_users(df) 

    send_welcome_email(email, fio, user_type, login, password)

    flash(f'Пользователь создан! Пароль отправлен на почту {email}.', 'success')
    return redirect(url_for('admin'))

@app.route('/delete_user', methods=['POST'])
def delete_user():
    login_to_delete = request.form.get('login')
    if not login_to_delete:
        flash('Не указан логин.', 'error')
        return redirect(url_for('admin'))

    df = load_users()
    if df[df['login'] == login_to_delete].empty:
        flash('Пользователь не найден.', 'error')
        return redirect(url_for('admin'))

    if df.loc[df['login'] == login_to_delete, 'type'].iloc[0] == 'admin':
        flash('Нельзя удалить администратора.', 'error')
        return redirect(url_for('admin'))

    df = df[df['login'] != login_to_delete]
    save_users(df)
    flash('Пользователь удалён.', 'success')
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)