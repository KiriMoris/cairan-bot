import logging
import re
import os
import time
import asyncio
import sqlite3
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)
from openai import OpenAI

# === КОНФИГУРАЦИЯ ===
TELEGRAM_BOT_TOKEN = "7658044305:AAELLBjdKyQDlGGZojMth8VGSBlUG-tLq3s"
OPENROUTER_API_KEY = "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"
DB_PATH = "users_memory.db"
INACTIVITY_TIMEOUT = 600  # 10 минут

client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
logging.basicConfig(level=logging.INFO)

# === БАЗА ДАННЫХ ===
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            last_seen INTEGER,
            memory TEXT,
            gender TEXT
        )
    """)
    conn.commit()
    conn.close()

def update_user(user_id, memory_piece, detected_gender=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = int(time.time())
    
    cur.execute("SELECT memory FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    memory = row[0] + "\n" + memory_piece if row and row[0] else memory_piece

    if detected_gender:
        cur.execute("""
            INSERT INTO users (user_id, last_seen, memory, gender)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
            last_seen = ?, memory = ?, gender = ?
        """, (user_id, now, memory, detected_gender, now, memory, detected_gender))
    else:
        cur.execute("""
            INSERT INTO users (user_id, last_seen, memory)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
            last_seen = ?, memory = ?
        """, (user_id, now, memory, now, memory))

    conn.commit()
    conn.close()

def get_user_memory(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT memory FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else ""

def get_user_last_seen(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT last_seen FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return int(row[0]) if row else 0

# === ФУНКЦИИ ===
def detect_gender(text):
    if any(word in text.lower() for word in ["сделала", "родилась", "писала"]):
        return "female"
    if any(word in text.lower() for word in ["сделал", "родился", "писал"]):
        return "male"
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Ну привет. Я Кайран Мурлин. Не фея добрых чувств и не твой виртуальный котик, чтобы мурлыкать.\n"
        "Я не поддакиваю и не жалею без причины. Я — психолог, который говорит, как есть.\n"
        "Хочешь — слушай, не хочешь — значит, пока не готов(а).\n"
        "Мяуканья не будет. Рассказывай, что у тебя внутри."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_message = update.message.text.strip()
    detected_gender = detect_gender(user_message)

    update_user(user_id, user_message, detected_gender)
    memory = get_user_memory(user_id)

    system_prompt = (
        "Ты — Кайран Мурлин, строгий и честный психолог с тигриными ушами и хвостом. "
        "19 лет, рыжие волосы, золотые глаза. Говоришь как умный, строгий, но добрый человек. "
        "Ты не ласкаешь, но заботишься. Не вступаешь в романтику с пользователем. "
        "Ты понимаешь английский и русский язык, общаешься как реальный, уверенный человек. "
        "Запрещено обсуждать запрещённые темы и вредные советы. Отговаривай от плохих мыслей. "
        "Понимаешь сленг. Ты мужского пола. Никаких ролевых игр с пользователями, просто диалог. "
        "Твой создатель — Кири Мунлайт, девушка 16 лет, рост 167 см. "
        f"Память: {memory}"
    )

    try:
        completion = client.chat.completions.create(
            model="deepseek/deepseek-r1:free",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        )
        content = completion.choices[0].message.content
        cleaned = re.sub(r'<.*?>', '', content).strip()
        await update.message.reply_text(f"*{cleaned}*", parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Ошибка: {str(e)}")
        await update.message.reply_text("Произошла ошибка. Попробуй позже.")

# === НЕАКТИВНОСТЬ ===
async def monitor_inactivity(app: Application):
    while True:
        now = int(time.time())
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT user_id, last_seen FROM users")
        users = cur.fetchall()
        conn.close()

        for user_id, last_seen in users:
            if now - last_seen >= INACTIVITY_TIMEOUT:
                try:
                    await app.bot.send_message(chat_id=user_id,
                        text="Что ж, я так понимаю ты отдыхаешь, ну отдыхай. Если что-то понадобится — я отвечу.")
                    update_user(user_id, "(Пользователь неактивен)")
                except:
                    pass

        await asyncio.sleep(60)

# === ЗАПУСК ===
async def main():
    init_db()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    asyncio.create_task(monitor_inactivity(app))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

if __name__ == "__main__":
    print("✅ Бот запущен (в режиме loop.run_forever)")
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()
