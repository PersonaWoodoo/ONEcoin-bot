# onemi_bot/bot.py — часть 1 из 6
import asyncio
import random
import re
import sqlite3
import time
import json
import string
import html
from datetime import datetime
from typing import Optional, Tuple, Dict, List, Any
from functools import wraps

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton,
    FSInputFile, URLInputFile
)

# ========================= КОНФИГУРАЦИЯ БОТА =========================
BOT_TOKEN = "8754529808:AAE5IEhizXS1sj6nm1n42KvdBN5XcdLm5dk"
ADMIN_IDS = [8478884644, 6016437346]   # добавлен новый админ
CURRENCY = "ONEmi"
START_BALANCE = 100.0
MIN_BET = 10.0
BONUS_COOLDOWN = 12 * 60 * 60           # 12 часов
BONUS_MIN = 50
BONUS_MAX = 250
TRANSFER_COMMISSION = 0.03             # 3%
TRANSFER_MAX_AMOUNT = 10_000_000        # 10kk
DB_PATH = "onemi_bot.db"

# Статусы игроков (красивые названия + множитель выигрышей)
USER_STATUSES = {
    0: {"name": "🟢 Обычный", "emoji": "🟢", "multiplier": 1.00},
    1: {"name": "🟡 Продвинутый", "emoji": "🟡", "multiplier": 1.05},
    2: {"name": "🔴 VIP", "emoji": "🔴", "multiplier": 1.10},
    3: {"name": "🟣 Премиум", "emoji": "🟣", "multiplier": 1.15},
    4: {"name": "👑 Легенда", "emoji": "👑", "multiplier": 1.25},
    5: {"name": "⚡ Создатель", "emoji": "⚡", "multiplier": 1.50},
}

BANK_TERMS = {
    7:  {"rate": 0.03, "name": "7 дней (+3%)"},
    14: {"rate": 0.07, "name": "14 дней (+7%)"},
    30: {"rate": 0.18, "name": "30 дней (+18%)"},
}

RED_NUMBERS = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
CRASH_MAX = 10.0
# ====================================================================

# ========================= ФОРМАТ ВАЛЮТЫ (к, кк, ккк, кккк, ккккк) ==
def parse_amount(text: str) -> float:
    """Преобразует 500, 1к, 2.5кк, 1ккк, 100кккк в число"""
    raw = text.lower().replace(" ", "").replace(",", ".")
    mult = 1.0
    if raw.endswith("ккккк"):
        mult = 100_000_000_000_000  # 10^14
        raw = raw[:-5]
    elif raw.endswith("кккк"):
        mult = 1_000_000_000_000     # 10^12
        raw = raw[:-4]
    elif raw.endswith("ккк"):
        mult = 1_000_000_000          # 10^9
        raw = raw[:-3]
    elif raw.endswith("кк"):
        mult = 1_000_000              # 1kk
        raw = raw[:-2]
    elif raw.endswith("к"):
        mult = 1_000                  # 1k
        raw = raw[:-1]
    # дополнительно миллионы/миллиарды на английском
    elif raw.endswith("b"):
        mult = 1_000_000_000
        raw = raw[:-1]
    elif raw.endswith("m"):
        mult = 1_000_000
        raw = raw[:-1]
    val = float(raw) if raw else 0
    return round(val * mult, 2)

def fmt_amount(value: float) -> str:
    """Красивый вывод: 1 500 000 -> 1.5кк"""
    if value >= 1_000_000_000_000:
        return f"{value/1_000_000_000_000:.2f}ккккк"
    if value >= 1_000_000_000:
        return f"{value/1_000_000_000:.2f}ккк"
    if value >= 1_000_000:
        return f"{value/1_000_000:.2f}кк"
    if value >= 1_000:
        return f"{value/1_000:.2f}к"
    return f"{value:.2f}".rstrip('0').rstrip('.') if value == int(value) else f"{value:.2f}"

def fmt_money(value: float) -> str:
    return f"{fmt_amount(value)} {CURRENCY}"
# ====================================================================

# ========================= СОСТОЯНИЯ ---------------------------------
class GameStates(StatesGroup):
    waiting_bet = State()
    waiting_choice = State()
    waiting_number = State()
    waiting_crash_target = State()

class CheckCreate(StatesGroup):
    amount = State()
    count = State()

class CheckClaim(StatesGroup):
    code = State()

class PromoRedeem(StatesGroup):
    code = State()

class BankOpen(StatesGroup):
    amount = State()

class TransferState(StatesGroup):
    target = State()
    amount = State()

class AdminGive(StatesGroup):
    target = State()
    amount = State()

class AdminStatus(StatesGroup):
    target = State()
    status = State()
# ====================================================================

# ========================= БАЗА ДАННЫХ (полная) =====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT,
        balance REAL DEFAULT 100,
        status INTEGER DEFAULT 0,
        total_bets INTEGER DEFAULT 0,
        total_wins INTEGER DEFAULT 0,
        total_losses INTEGER DEFAULT 0,
        total_win_amount REAL DEFAULT 0,
        joined_at INTEGER,
        last_active INTEGER,
        is_banned INTEGER DEFAULT 0,
        ban_reason TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS bets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        game TEXT,
        bet REAL,
        win REAL,
        multiplier REAL,
        ts INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS checks (
        code TEXT PRIMARY KEY,
        creator_id TEXT,
        amount REAL,
        remaining INTEGER,
        claimed TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS promos (
        code TEXT PRIMARY KEY,
        reward REAL,
        remaining INTEGER,
        claimed TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        amount REAL,
        term_days INTEGER,
        rate REAL,
        opened_at INTEGER,
        status TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS daily_bonus (
        user_id TEXT PRIMARY KEY,
        last_claim INTEGER,
        streak INTEGER DEFAULT 1
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id TEXT,
        action TEXT,
        target TEXT,
        details TEXT,
        ts INTEGER
    )''')
    conn.commit()
    conn.close()

def now_ts() -> int:
    return int(time.time())

def get_user(user_id: int, name: str = None) -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (str(user_id),))
    row = c.fetchone()
    if not row:
        ts = now_ts()
        uname = name or f"User{user_id}"
        c.execute('''INSERT INTO users (id, name, balance, joined_at, last_active) 
                     VALUES (?, ?, ?, ?, ?)''',
                  (str(user_id), uname, START_BALANCE, ts, ts))
        conn.commit()
        c.execute("SELECT * FROM users WHERE id = ?", (str(user_id),))
        row = c.fetchone()
    conn.close()
    return {
        "id": row[0], "name": row[1], "balance": row[2], "status": row[3],
        "total_bets": row[4], "total_wins": row[5], "total_losses": row[6],
        "total_win_amount": row[7], "joined_at": row[8], "last_active": row[9],
        "is_banned": row[10], "ban_reason": row[11]
    }

def update_balance(user_id: int, delta: float) -> float:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (round(delta,2), str(user_id)))
    c.execute("UPDATE users SET last_active = ? WHERE id = ?", (now_ts(), str(user_id)))
    conn.commit()
    c.execute("SELECT balance FROM users WHERE id = ?", (str(user_id),))
    bal = c.fetchone()[0]
    conn.close()
    return bal

def set_balance(user_id: int, amount: float):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET balance = ? WHERE id = ?", (round(amount,2), str(user_id)))
    conn.commit()
    conn.close()

def get_status_multiplier(user_id: int) -> float:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT status FROM users WHERE id = ?", (str(user_id),))
    row = c.fetchone()
    conn.close()
    st = row[0] if row else 0
    return USER_STATUSES.get(st, USER_STATUSES[0])["multiplier"]

def set_user_status(user_id: int, status: int) -> bool:
    if status not in USER_STATUSES:
        return False
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET status = ? WHERE id = ?", (status, str(user_id)))
    conn.commit()
    conn.close()
    return True

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def add_bet(user_id: int, game: str, bet: float, win: float, multiplier: float):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO bets (user_id, game, bet, win, multiplier, ts)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (str(user_id), game, bet, win, multiplier, now_ts()))
    c.execute("UPDATE users SET total_bets = total_bets + 1 WHERE id = ?", (str(user_id),))
    if win > 0:
        c.execute("UPDATE users SET total_wins = total_wins + 1, total_win_amount = total_win_amount + ? WHERE id = ?",
                  (win, str(user_id)))
    else:
        c.execute("UPDATE users SET total_losses = total_losses + 1 WHERE id = ?", (str(user_id),))
    conn.commit()
    conn.close()

def log_admin(admin_id: int, action: str, target: str = None, details: str = ""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO admin_logs (admin_id, action, target, details, ts)
                 VALUES (?, ?, ?, ?, ?)''',
              (str(admin_id), action, target, details, now_ts()))
    conn.commit()
    conn.close()

def get_top_users(limit=10) -> List[dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT id, name, balance, status FROM users 
                 WHERE is_banned = 0 ORDER BY balance DESC LIMIT ?''', (limit,))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "balance": r[2], "status": r[3]} for r in rows]

def get_all_users() -> List[dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, balance, status, is_banned FROM users")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "balance": r[2], "status": r[3], "is_banned": r[4]} for r in rows]

def ban_user(user_id: int, reason: str = "") -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET is_banned = 1, ban_reason = ? WHERE id = ?", (reason, str(user_id)))
    conn.commit()
    conn.close()
    return True

def unban_user(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET is_banned = 0, ban_reason = NULL WHERE id = ?", (str(user_id),))
    conn.commit()
    conn.close()
    return True
# ====================================================================

# ========================= ЧЕКИ (с кнопками копировать/поделиться) ==
def generate_check_code() -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def create_check(creator_id: int, amount: float, count: int) -> Tuple[bool, str]:
    total = amount * count
    user = get_user(creator_id)
    if user["balance"] < total:
        return False, "Недостаточно средств"
    update_balance(creator_id, -total)
    code = generate_check_code()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO checks (code, creator_id, amount, remaining, claimed) 
                 VALUES (?, ?, ?, ?, ?)''',
              (code, str(creator_id), amount, count, "[]"))
    conn.commit()
    conn.close()
    return True, code

def claim_check(user_id: int, code: str) -> Tuple[bool, str, float]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM checks WHERE code = ?", (code.upper(),))
    row = c.fetchone()
    if not row:
        conn.close(); return False, "Чек не найден", 0
    if row[3] <= 0:
        conn.close(); return False, "Чек использован", 0
    claimed = json.loads(row[4])
    if str(user_id) in claimed:
        conn.close(); return False, "Вы уже активировали этот чек", 0
    claimed.append(str(user_id))
    c.execute("UPDATE checks SET remaining = ?, claimed = ? WHERE code = ?",
              (row[3]-1, json.dumps(claimed), code.upper()))
    conn.commit()
    conn.close()
    update_balance(user_id, row[2])
    return True, "Чек активирован", row[2]

def get_my_checks(user_id: int) -> List[dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT code, amount, remaining FROM checks WHERE creator_id = ?", (str(user_id),))
    rows = c.fetchall()
    conn.close()
    return [{"code": r[0], "amount": r[1], "remaining": r[2]} for r in rows]

def check_share_kb(code: str) -> InlineKeyboardMarkup:
    share_link = f"https://t.me/share/url?url=Чек%20{code}%20на%20{fmt_money(amount)}&text=Забери%20свой%20бонус!"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Скопировать", callback_data=f"copy_check:{code}")],
        [InlineKeyboardButton(text="📤 Поделиться в Telegram", url=share_link)],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:checks")]
    ])

# ========================= ПРОМОКОДЫ ================================
def create_promo(code: str, reward: float, activations: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO promos (code, reward, remaining, claimed) 
                     VALUES (?, ?, ?, ?)''',
                  (code.upper(), reward, activations, "[]"))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def claim_promo(user_id: int, code: str) -> Tuple[bool, str, float]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM promos WHERE code = ?", (code.upper(),))
    row = c.fetchone()
    if not row:
        conn.close(); return False, "Промокод не найден", 0
    if row[2] <= 0:
        conn.close(); return False, "Промокод использован", 0
    claimed = json.loads(row[3])
    if str(user_id) in claimed:
        conn.close(); return False, "Вы уже активировали промокод", 0
    claimed.append(str(user_id))
    c.execute("UPDATE promos SET remaining = ?, claimed = ? WHERE code = ?",
              (row[2]-1, json.dumps(claimed), code.upper()))
    conn.commit()
    conn.close()
    update_balance(user_id, row[1])
    return True, "Промокод активирован", row[1]

# ========================= БАНК (депозиты) =========================
def open_deposit(user_id: int, amount: float, term_days: int) -> Tuple[bool, str]:
    if term_days not in BANK_TERMS:
        return False, "Неверный срок"
    if amount < 100:
        return False, "Минимальный депозит 100"
    user = get_user(user_id)
    if user["balance"] < amount:
        return False, "Недостаточно средств"
    update_balance(user_id, -amount)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO deposits (user_id, amount, term_days, rate, opened_at, status)
                 VALUES (?, ?, ?, ?, ?, 'active')''',
              (str(user_id), amount, term_days, BANK_TERMS[term_days]["rate"], now_ts()))
    conn.commit()
    conn.close()
    return True, f"Депозит {term_days} дней открыт"

def get_active_deposits(user_id: int) -> List[dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT id, amount, term_days, rate, opened_at FROM deposits 
                 WHERE user_id = ? AND status = 'active' ''', (str(user_id),))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "amount": r[1], "term_days": r[2], "rate": r[3], "opened_at": r[4]} for r in rows]

def close_matured_deposits(user_id: int) -> Tuple[int, float]:
    now = now_ts()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT id, amount, rate, term_days, opened_at FROM deposits 
                 WHERE user_id = ? AND status = 'active' ''', (str(user_id),))
    deps = c.fetchall()
    total = 0.0
    count = 0
    for dep in deps:
        maturity = dep[4] + dep[3] * 86400
        if now >= maturity:
            payout = dep[1] * (1 + dep[2])
            total += payout
            count += 1
            c.execute("UPDATE deposits SET status = 'closed' WHERE id = ?", (dep[0],))
    if total > 0:
        update_balance(user_id, total)
    conn.commit()
    conn.close()
    return count, total

# ========================= ПЕРЕВОДЫ (3% комиссия, лимит 10кк) =======
def transfer_coins(from_id: int, to_id: int, amount: float) -> Tuple[bool, str]:
    if amount <= 0:
        return False, "Сумма должна быть >0"
    if amount > TRANSFER_MAX_AMOUNT:
        return False, f"Максимальная сумма перевода {fmt_money(TRANSFER_MAX_AMOUNT)}"
    if from_id == to_id:
        return False, "Нельзя перевести самому себе"
    sender = get_user(from_id)
    if sender["balance"] < amount:
        return False, "Недостаточно средств"
    commission = amount * TRANSFER_COMMISSION
    after_com = amount - commission
    update_balance(from_id, -amount)
    update_balance(to_id, after_com)
    # комиссия уходит в "банк", просто теряется
    log_admin(from_id, "transfer", str(to_id), f"{amount} -> {after_com} (комиссия {commission})")
    return True, f"Переведено {fmt_money(after_com)} пользователю {get_user(to_id)['name']} (комиссия {fmt_money(commission)})"

# ========================= ЕЖЕДНЕВНЫЙ БОНУС ========================
def claim_daily_bonus(user_id: int) -> Tuple[bool, int, float, int]:
    now = now_ts()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT last_claim, streak FROM daily_bonus WHERE user_id = ?", (str(user_id),))
    row = c.fetchone()
    if row:
        last = row[0]
        streak = row[1]
        if now - last < BONUS_COOLDOWN:
            rem = BONUS_COOLDOWN - (now - last)
            conn.close(); return False, rem, 0, streak
        if now - last > BONUS_COOLDOWN + 86400:
            streak = 1
        else:
            streak += 1
    else:
        streak = 1
    bonus = random.randint(BONUS_MIN, BONUS_MAX)
    # бонус за стрик
    bonus = int(bonus * min(1.5, 1 + streak * 0.05))
    update_balance(user_id, bonus)
    c.execute("INSERT OR REPLACE INTO daily_bonus (user_id, last_claim, streak) VALUES (?, ?, ?)",
              (str(user_id), now, streak))
    conn.commit()
    conn.close()
    return True, 0, bonus, streak
# ====================================================================# onemi_bot/bot.py — часть 2 из 6

# ========================= КЛАВИАТУРЫ (красивые) ===================
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Баланс", callback_data="menu:balance"),
         InlineKeyboardButton(text="🎁 Бонус", callback_data="menu:bonus")],
        [InlineKeyboardButton(text="🎮 Игры", callback_data="menu:games"),
         InlineKeyboardButton(text="🏆 Топ", callback_data="menu:top")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile"),
         InlineKeyboardButton(text="🏦 Банк", callback_data="menu:bank")],
        [InlineKeyboardButton(text="🧾 Чеки", callback_data="menu:checks"),
         InlineKeyboardButton(text="🎟 Промо", callback_data="menu:promo")],
        [InlineKeyboardButton(text="💸 Перевести", callback_data="menu:transfer"),
         InlineKeyboardButton(text="❓ Помощь", callback_data="menu:help")],
    ])

def games_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎡 Рулетка", callback_data="game:roulette"),
         InlineKeyboardButton(text="📈 Краш", callback_data="game:crash")],
        [InlineKeyboardButton(text="🎲 Кубик", callback_data="game:cube"),
         InlineKeyboardButton(text="🎯 Кости", callback_data="game:dice")],
        [InlineKeyboardButton(text="⚽ Футбол", callback_data="game:football"),
         InlineKeyboardButton(text="🏀 Баскет", callback_data="game:basket")],
        [InlineKeyboardButton(text="🗼 Башня", callback_data="game:tower"),
         InlineKeyboardButton(text="💎 Алмазы", callback_data="game:diamond")],
        [InlineKeyboardButton(text="💣 Мины", callback_data="game:mines"),
         InlineKeyboardButton(text="🎴 Очко", callback_data="game:blackjack")],
        [InlineKeyboardButton(text="🥇 Золото", callback_data="game:gold")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:back_to_main")],
    ])

def roulette_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Красное (x2)", callback_data="roulette:red"),
         InlineKeyboardButton(text="⚫ Чёрное (x2)", callback_data="roulette:black")],
        [InlineKeyboardButton(text="2️⃣ Чёт (x2)", callback_data="roulette:even"),
         InlineKeyboardButton(text="1️⃣ Нечёт (x2)", callback_data="roulette:odd")],
        [InlineKeyboardButton(text="0️⃣ Зеро (x35)", callback_data="roulette:zero")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="game:back")],
    ])

def crash_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1.5x", callback_data="crash:1.5"),
         InlineKeyboardButton(text="2x", callback_data="crash:2"),
         InlineKeyboardButton(text="3x", callback_data="crash:3")],
        [InlineKeyboardButton(text="5x", callback_data="crash:5"),
         InlineKeyboardButton(text="10x", callback_data="crash:10")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="game:back")],
    ])

def cube_kb():
    kb = []
    row = []
    for i in range(1, 7):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"cube:{i}"))
        if len(row) == 3:
            kb.append(row); row = []
    if row: kb.append(row)
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="game:back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def dice_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬆️ Больше 7 (x1.9)", callback_data="dice:more"),
         InlineKeyboardButton(text="⬇️ Меньше 7 (x1.9)", callback_data="dice:less")],
        [InlineKeyboardButton(text="7️⃣ Ровно 7 (x5)", callback_data="dice:seven")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="game:back")],
    ])

def football_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚽ ГОЛ (x1.85)", callback_data="football:goal"),
         InlineKeyboardButton(text="❌ МИМО (x1.85)", callback_data="football:miss")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="game:back")],
    ])

def basket_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏀 ПОПАЛ (x2.2)", callback_data="basket:hit"),
         InlineKeyboardButton(text="❌ ПРОМАХ (x2.2)", callback_data="basket:miss")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="game:back")],
    ])

def bank_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Открыть депозит", callback_data="bank:open")],
        [InlineKeyboardButton(text="📋 Мои депозиты", callback_data="bank:list")],
        [InlineKeyboardButton(text="💰 Забрать депозиты", callback_data="bank:claim")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:back_to_main")],
    ])

def bank_terms_kb():
    kb = []
    for days, info in BANK_TERMS.items():
        kb.append([InlineKeyboardButton(text=info["name"], callback_data=f"bank:term:{days}")])
    kb.append([InlineKeyboardButton(text="❌ Отмена", callback_data="bank:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def checks_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать чек", callback_data="checks:create")],
        [InlineKeyboardButton(text="💸 Активировать чек", callback_data="checks:claim")],
        [InlineKeyboardButton(text="📋 Мои чеки", callback_data="checks:my")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:back_to_main")],
    ])

def admin_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Выдать", callback_data="admin:give"),
         InlineKeyboardButton(text="👑 Сменить статус", callback_data="admin:status")],
        [InlineKeyboardButton(text="👥 Все игроки", callback_data="admin:users"),
         InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats"),
         InlineKeyboardButton(text="🎟 Промокоды", callback_data="admin:promos")],
        [InlineKeyboardButton(text="🧾 Чеки (все)", callback_data="admin:checks"),
         InlineKeyboardButton(text="🚫 Бан/Разбан", callback_data="admin:ban")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin:close")],
    ])

def admin_status_kb():
    kb = []
    for st, info in USER_STATUSES.items():
        kb.append([InlineKeyboardButton(text=f"{info['emoji']} {info['name']} (x{info['multiplier']})",
                                        callback_data=f"admin:set_status:{st}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def play_again_kb(game: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть снова", callback_data=f"again:{game}")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:games")],
    ])

def share_check_kb(code: str, amount: float):
    share_text = f"Чек {code} на {fmt_money(amount)}! Забирай бонус в @onemi_bot"
    share_url = f"https://t.me/share/url?url={share_text}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Скопировать код", callback_data=f"copy:{code}")],
        [InlineKeyboardButton(text="📤 Поделиться", url=share_url)],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="checks:my")],
    ])

# ========================= ОБЩИЕ ИГРОВЫЕ ФУНКЦИИ ===================
def roulette_spin(choice: str) -> Tuple[bool, float, int, str]:
    num = random.randint(0, 36)
    if num == 0:
        color = "green"
    elif num in RED_NUMBERS:
        color = "red"
    else:
        color = "black"
    win = False
    mult = 0
    if choice == "red" and color == "red":
        win, mult = True, 2.0
    elif choice == "black" and color == "black":
        win, mult = True, 2.0
    elif choice == "even" and num != 0 and num % 2 == 0:
        win, mult = True, 2.0
    elif choice == "odd" and num != 0 and num % 2 == 1:
        win, mult = True, 2.0
    elif choice == "zero" and num == 0:
        win, mult = True, 35.0
    color_ru = {"red": "🔴 красное", "black": "⚫ чёрное", "green": "🟢 зеро"}[color]
    return win, mult, num, color_ru

def crash_roll() -> float:
    u = random.random()
    raw = 0.99 / (1.0 - u)
    return round(max(1.0, min(CRASH_MAX, raw)), 2)

def roll_dice() -> int:
    return random.randint(1, 6)

def roll_two_dice() -> int:
    return random.randint(1, 6) + random.randint(1, 6)

def football_kick() -> Tuple[str, int]:
    val = random.randint(1, 6)
    return ("ГОЛ" if val >= 4 else "МИМО"), val

def basketball_shot() -> Tuple[str, int]:
    val = random.randint(1, 6)
    return ("ПОПАЛ" if val >= 4 else "ПРОМАХ"), val

# ========================= ОБРАБОТЧИКИ МЕНЮ ========================
dp = Dispatcher(storage=MemoryStorage())

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = get_user(message.from_user.id, message.from_user.full_name)
    await message.answer(
        f"🎮 Добро пожаловать в <b>ONEmi Game Bot</b>\n\n"
        f"👤 {user['name']}\n"
        f"💰 Баланс: {fmt_money(user['balance'])}\n"
        f"🎭 Статус: {USER_STATUSES[user['status']]['emoji']} {USER_STATUSES[user['status']]['name']}\n\n"
        f"Используй кнопки ниже 👇",
        reply_markup=main_menu_kb()
    )

@dp.callback_query(F.data == "menu:back_to_main")
@dp.callback_query(F.data == "menu:back")
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text("🎮 Главное меню", reply_markup=main_menu_kb())
    await callback.answer()

@dp.callback_query(F.data == "menu:balance")
async def menu_balance(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    await callback.message.answer(f"💰 Ваш баланс: <b>{fmt_money(user['balance'])}</b>")
    await callback.answer()

@dp.callback_query(F.data == "menu:bonus")
async def menu_bonus(callback: CallbackQuery):
    ok, left, reward, streak = claim_daily_bonus(callback.from_user.id)
    if not ok:
        await callback.message.answer(f"🎁 Бонус через {left//3600}ч {(left%3600)//60}мин")
    else:
        await callback.message.answer(
            f"🎁 Вы получили {fmt_money(reward)}!\n"
            f"🔥 Стрик: {streak} дней\n"
            f"💰 Баланс: {fmt_money(get_user(callback.from_user.id)['balance'])}"
        )
    await callback.answer()

@dp.callback_query(F.data == "menu:games")
async def menu_games(callback: CallbackQuery):
    await callback.message.edit_text("🎮 Выбери игру:", reply_markup=games_kb())
    await callback.answer()

@dp.callback_query(F.data == "menu:top")
async def menu_top(callback: CallbackQuery):
    top = get_top_users(10)
    if not top:
        await callback.message.answer("🏆 Топ пока пуст")
    else:
        medals = ["🥇", "🥈", "🥉"]
        text = "🏆 Топ игроков ONEmi\n\n"
        for i, u in enumerate(top, 1):
            medal = medals[i-1] if i <= 3 else f"{i}."
            st_emoji = USER_STATUSES[u["status"]]["emoji"]
            text += f"{medal} {st_emoji} {u['name']} — {fmt_money(u['balance'])}\n"
        await callback.message.answer(text)
    await callback.answer()

@dp.callback_query(F.data == "menu:profile")
async def menu_profile(callback: CallbackQuery):
    u = get_user(callback.from_user.id)
    st = USER_STATUSES[u["status"]]
    wr = (u["total_wins"] / u["total_bets"] * 100) if u["total_bets"] else 0
    await callback.message.answer(
        f"👤 Профиль {st['emoji']} {st['name']}\n\n"
        f"💰 Баланс: {fmt_money(u['balance'])}\n"
        f"🎲 Ставок: {u['total_bets']}\n"
        f"✅ Побед: {u['total_wins']} ({wr:.1f}%)\n"
        f"🏆 Выиграно: {fmt_money(u['total_win_amount'])}\n"
        f"📅 В игре с: {datetime.fromtimestamp(u['joined_at']).strftime('%d.%m.%Y')}"
    )
    await callback.answer()

@dp.callback_query(F.data == "menu:transfer")
async def menu_transfer(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TransferState.target)
    await callback.message.answer(
        "💸 Перевести монеты\n\n"
        "Введите ник или ID получателя.\n"
        "Пример: @durov или 123456789"
    )
    await callback.answer()

@dp.message(TransferState.target)
async def transfer_target(message: Message, state: FSMContext):
    text = message.text.strip()
    target_id = None
    if text.startswith("@"):
        name = text[1:]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE name = ?", (name,))
        row = c.fetchone()
        conn.close()
        if not row:
            await message.answer("❌ Пользователь не найден")
            return
        target_id = int(row[0])
    else:
        try:
            target_id = int(text)
        except:
            await message.answer("❌ Неверный формат")
            return
    await state.update_data(target=target_id)
    await state.set_state(TransferState.amount)
    await message.answer(f"Введите сумму для перевода (макс. {fmt_money(TRANSFER_MAX_AMOUNT)})")

@dp.message(TransferState.amount)
async def transfer_amount(message: Message, state: FSMContext):
    try:
        amount = parse_amount(message.text)
    except:
        await message.answer("❌ Неверная сумма")
        return
    if amount <= 0:
        await message.answer("❌ Сумма >0")
        return
    if amount > TRANSFER_MAX_AMOUNT:
        await message.answer(f"❌ Максимум {fmt_money(TRANSFER_MAX_AMOUNT)}")
        return
    data = await state.get_data()
    target_id = data["target"]
    ok, msg = transfer_coins(message.from_user.id, target_id, amount)
    await message.answer(msg)
    await state.clear()

@dp.callback_query(F.data == "menu:bank")
async def menu_bank(callback: CallbackQuery):
    await callback.message.edit_text("🏦 Банк ONEmi", reply_markup=bank_kb())
    await callback.answer()

@dp.callback_query(F.data == "menu:checks")
async def menu_checks(callback: CallbackQuery):
    await callback.message.edit_text("🧾 Чеки", reply_markup=checks_menu_kb())
    await callback.answer()

@dp.callback_query(F.data == "menu:promo")
async def menu_promo(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PromoRedeem.code)
    await callback.message.answer("🎟 Введите код промокода:")
    await callback.answer()

@dp.message(PromoRedeem.code)
async def promo_redeem(message: Message, state: FSMContext):
    ok, msg, _ = claim_promo(message.from_user.id, message.text.strip())
    await message.answer(msg)
    await state.clear()

# ========================= РУЛЕТКА =================================
@dp.callback_query(F.data == "game:roulette")
async def roulette_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="roulette")
    await callback.message.answer("🎡 Рулетка\nВведи ставку (например 100, 50к, 2кк):")
    await callback.answer()

@dp.message(GameStates.waiting_bet)
async def game_bet(message: Message, state: FSMContext):
    try:
        bet = parse_amount(message.text)
        if bet < MIN_BET:
            await message.answer(f"❌ Минимум {fmt_money(MIN_BET)}")
            return
    except:
        await message.answer("❌ Введи число")
        return
    user = get_user(message.from_user.id)
    if user["balance"] < bet:
        await message.answer(f"❌ Не хватает. Баланс {fmt_money(user['balance'])}")
        return
    await state.update_data(bet=bet)
    data = await state.get_data()
    game = data.get("game")
    if game == "roulette":
        await state.set_state(GameStates.waiting_choice)
        await message.answer(f"💰 Ставка {fmt_money(bet)}\nВыбери:", reply_markup=roulette_kb())
    elif game == "crash_menu":
        await state.set_state(GameStates.waiting_crash_target)
        await message.answer(f"💰 Ставка {fmt_money(bet)}\nВыбери множитель:", reply_markup=crash_menu_kb())
    elif game == "cube":
        await state.set_state(GameStates.waiting_choice)
        await message.answer(f"💰 Ставка {fmt_money(bet)}\nУгадай число:", reply_markup=cube_kb())
    elif game == "dice":
        await state.set_state(GameStates.waiting_choice)
        await message.answer(f"💰 Ставка {fmt_money(bet)}\nВыбери условие:", reply_markup=dice_kb())
    elif game == "football":
        await state.set_state(GameStates.waiting_choice)
        await message.answer(f"💰 Ставка {fmt_money(bet)}\nВыбери исход:", reply_markup=football_kb())
    elif game == "basket":
        await state.set_state(GameStates.waiting_choice)
        await message.answer(f"💰 Ставка {fmt_money(bet)}\nВыбери исход:", reply_markup=basket_kb())
    else:
        await message.answer("❌ Ошибка")
        await state.clear()

@dp.callback_query(GameStates.waiting_choice, F.data.startswith("roulette:"))
async def roulette_play(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split(":")[1]
    data = await state.get_data()
    bet = data["bet"]
    uid = callback.from_user.id
    update_balance(uid, -bet)
    win, mult, num, color = roulette_spin(choice)
    if win:
        win_amount = bet * mult * get_status_multiplier(uid)
        update_balance(uid, win_amount)
        add_bet(uid, "roulette", bet, win_amount, mult)
        text = f"🎡 Выпало {num} {color}\n✅ Вы выиграли {fmt_money(win_amount)}"
    else:
        add_bet(uid, "roulette", bet, 0, 0)
        text = f"🎡 Выпало {num} {color}\n❌ Проигрыш {fmt_money(bet)}"
    text += f"\n💰 Баланс: {fmt_money(get_user(uid)['balance'])}"
    await callback.message.answer(text, reply_markup=play_again_kb("roulette"))
    await state.clear()
    await callback.answer()

# ========================= КРАШ (команда + меню) ===================
@dp.callback_query(F.data == "game:crash")
async def crash_menu(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="crash_menu")
    await callback.message.answer("📈 Краш\nВведи ставку (например 100, 50к, 2кк):")
    await callback.answer()

@dp.callback_query(GameStates.waiting_crash_target, F.data.startswith("crash:"))
async def crash_choice_play(callback: CallbackQuery, state: FSMContext):
    target = float(callback.data.split(":")[1])
    data = await state.get_data()
    bet = data["bet"]
    uid = callback.from_user.id
    update_balance(uid, -bet)
    crash_point = crash_roll()
    if target <= crash_point:
        win_amount = bet * target * get_status_multiplier(uid)
        update_balance(uid, win_amount)
        add_bet(uid, "crash", bet, win_amount, target)
        text = f"📈 Краш точка x{crash_point}\n✅ Выигрыш {fmt_money(win_amount)}"
    else:
        add_bet(uid, "crash", bet, 0, 0)
        text = f"📈 Краш точка x{crash_point}\n❌ Проигрыш {fmt_money(bet)}"
    text += f"\n💰 Баланс: {fmt_money(get_user(uid)['balance'])}"
    await callback.message.answer(text, reply_markup=play_again_kb("crash"))
    await state.clear()
    await callback.answer()

# текстовый краш 100к 4
@dp.message(lambda m: m.text and m.text.lower().startswith("краш"))
async def crash_text_command(message: Message, state: FSMContext):
    parts = message.text.lower().split()
    if len(parts) != 3:
        await message.answer("❌ Используй: краш 50кк 4")
        return
    try:
        bet = parse_amount(parts[1])
        target = float(parts[2])
    except:
        await message.answer("❌ Неверный формат")
        return
    if bet < MIN_BET:
        await message.answer(f"❌ Минимум {fmt_money(MIN_BET)}")
        return
    user = get_user(message.from_user.id)
    if user["balance"] < bet:
        await message.answer(f"❌ Не хватает")
        return
    update_balance(message.from_user.id, -bet)
    crash_point = crash_roll()
    if target <= crash_point:
        win_amount = bet * target * get_status_multiplier(message.from_user.id)
        update_balance(message.from_user.id, win_amount)
        add_bet(message.from_user.id, "crash", bet, win_amount, target)
        await message.answer(f"📈 Краш x{crash_point}\n✅ Выигрыш {fmt_money(win_amount)}")
    else:
        add_bet(message.from_user.id, "crash", bet, 0, 0)
        await message.answer(f"📈 Краш x{crash_point}\n❌ Проигрыш {fmt_money(bet)}")
    bal = get_user(message.from_user.id)["balance"]
    await message.answer(f"💰 Баланс: {fmt_money(bal)}")

# ========================= КУБИК ===================================
@dp.callback_query(F.data == "game:cube")
async def cube_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="cube")
    await callback.message.answer("🎲 Кубик\nВведи ставку:")
    await callback.answer()

@dp.callback_query(GameStates.waiting_choice, F.data.startswith("cube:"))
async def cube_play(callback: CallbackQuery, state: FSMContext):
    guess = int(callback.data.split(":")[1])
    data = await state.get_data()
    bet = data["bet"]
    uid = callback.from_user.id
    update_balance(uid, -bet)
    roll = roll_dice()
    if guess == roll:
        win_amount = bet * 5.8 * get_status_multiplier(uid)
        update_balance(uid, win_amount)
        add_bet(uid, "cube", bet, win_amount, 5.8)
        text = f"🎲 Выпало {roll}\n✅ Выигрыш {fmt_money(win_amount)}"
    else:
        add_bet(uid, "cube", bet, 0, 0)
        text = f"🎲 Выпало {roll}\n❌ Проигрыш {fmt_money(bet)}"
    text += f"\n💰 Баланс: {fmt_money(get_user(uid)['balance'])}"
    await callback.message.answer(text, reply_markup=play_again_kb("cube"))
    await state.clear()
    await callback.answer()

# текстовый кубик
@dp.message(lambda m: m.text and m.text.lower().startswith("кубик"))
async def cube_text_command(message: Message):
    parts = message.text.lower().split()
    if len(parts) != 3:
        await message.answer("❌ кубик 50кк 5")
        return
    try:
        bet = parse_amount(parts[1])
        guess = int(parts[2])
    except:
        await message.answer("❌ Неверно")
        return
    if guess < 1 or guess > 6:
        await message.answer("❌ 1-6")
        return
    user = get_user(message.from_user.id)
    if user["balance"] < bet:
        await message.answer("❌ Не хватает")
        return
    update_balance(message.from_user.id, -bet)
    roll = roll_dice()
    if guess == roll:
        win = bet * 5.8 * get_status_multiplier(message.from_user.id)
        update_balance(message.from_user.id, win)
        add_bet(message.from_user.id, "cube", bet, win, 5.8)
        await message.answer(f"🎲 Выпало {roll}\n✅ {fmt_money(win)}")
    else:
        add_bet(message.from_user.id, "cube", bet, 0, 0)
        await message.answer(f"🎲 Выпало {roll}\n❌ {fmt_money(bet)}")
    bal = get_user(message.from_user.id)["balance"]
    await message.answer(f"💰 {fmt_money(bal)}")# onemi_bot/bot.py — часть 3 из 6 (кости, футбол, баскет, башня)

# ========================= КОСТИ ===================================
@dp.callback_query(F.data == "game:dice")
async def dice_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="dice")
    await callback.message.answer("🎯 Кости (сумма двух кубиков)\nВведи ставку:")
    await callback.answer()

@dp.callback_query(GameStates.waiting_choice, F.data.startswith("dice:"))
async def dice_play(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split(":")[1]
    data = await state.get_data()
    bet = data["bet"]
    uid = callback.from_user.id
    update_balance(uid, -bet)
    total = roll_two_dice()
    win = False
    mult = 0
    if choice == "more" and total > 7:
        win, mult = True, 1.9
    elif choice == "less" and total < 7:
        win, mult = True, 1.9
    elif choice == "seven" and total == 7:
        win, mult = True, 5.0
    choice_names = {"more": "больше 7", "less": "меньше 7", "seven": "ровно 7"}
    if win:
        win_amount = bet * mult * get_status_multiplier(uid)
        update_balance(uid, win_amount)
        add_bet(uid, "dice", bet, win_amount, mult)
        text = f"🎯 Сумма {total}\n✅ {fmt_money(win_amount)}"
    else:
        add_bet(uid, "dice", bet, 0, 0)
        text = f"🎯 Сумма {total}\n❌ {fmt_money(bet)}"
    text += f"\n💰 Баланс: {fmt_money(get_user(uid)['balance'])}"
    await callback.message.answer(text, reply_markup=play_again_kb("dice"))
    await state.clear()
    await callback.answer()

# текстовые кости
@dp.message(lambda m: m.text and m.text.lower().startswith("кости"))
async def dice_text_command(message: Message):
    parts = message.text.lower().split()
    if len(parts) != 3:
        await message.answer("❌ кости 50кк м | б | равно")
        return
    try:
        bet = parse_amount(parts[1])
    except:
        await message.answer("❌ Сумма")
        return
    choice = parts[2]
    if choice not in ["м", "б", "равно"]:
        await message.answer("❌ м / б / равно")
        return
    user = get_user(message.from_user.id)
    if user["balance"] < bet:
        await message.answer("❌ Не хватает")
        return
    update_balance(message.from_user.id, -bet)
    total = roll_two_dice()
    win = False
    mult = 0
    if choice == "м" and total < 7:
        win, mult = True, 1.9
    elif choice == "б" and total > 7:
        win, mult = True, 1.9
    elif choice == "равно" and total == 7:
        win, mult = True, 5.0
    if win:
        win_amount = bet * mult * get_status_multiplier(message.from_user.id)
        update_balance(message.from_user.id, win_amount)
        add_bet(message.from_user.id, "dice", bet, win_amount, mult)
        await message.answer(f"🎯 Сумма {total}\n✅ {fmt_money(win_amount)}")
    else:
        add_bet(message.from_user.id, "dice", bet, 0, 0)
        await message.answer(f"🎯 Сумма {total}\n❌ {fmt_money(bet)}")
    bal = get_user(message.from_user.id)["balance"]
    await message.answer(f"💰 {fmt_money(bal)}")

# ========================= ФУТБОЛ =================================
@dp.callback_query(F.data == "game:football")
async def football_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="football")
    await callback.message.answer("⚽ Футбол\nВведи ставку:")
    await callback.answer()

@dp.callback_query(GameStates.waiting_choice, F.data.startswith("football:"))
async def football_play(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split(":")[1]
    data = await state.get_data()
    bet = data["bet"]
    uid = callback.from_user.id
    update_balance(uid, -bet)
    result, val = football_kick()
    win = (choice == "goal" and result == "ГОЛ") or (choice == "miss" and result == "МИМО")
    mult = 1.85
    if win:
        win_amount = bet * mult * get_status_multiplier(uid)
        update_balance(uid, win_amount)
        add_bet(uid, "football", bet, win_amount, mult)
        text = f"⚽ {result}\n✅ {fmt_money(win_amount)}"
    else:
        add_bet(uid, "football", bet, 0, 0)
        text = f"⚽ {result}\n❌ {fmt_money(bet)}"
    text += f"\n💰 {fmt_money(get_user(uid)['balance'])}"
    await callback.message.answer(text, reply_markup=play_again_kb("football"))
    await state.clear()
    await callback.answer()

# текстовый футбол
@dp.message(lambda m: m.text and m.text.lower().startswith("футбол"))
async def football_text_command(message: Message):
    parts = message.text.lower().split()
    if len(parts) != 3:
        await message.answer("❌ футбол 50кк гол|мимо")
        return
    try:
        bet = parse_amount(parts[1])
    except:
        await message.answer("❌ Сумма")
        return
    choice = parts[2]
    if choice not in ["гол", "мимо"]:
        await message.answer("❌ гол / мимо")
        return
    user = get_user(message.from_user.id)
    if user["balance"] < bet:
        await message.answer("❌ Не хватает")
        return
    update_balance(message.from_user.id, -bet)
    result, val = football_kick()
    win = (choice == "гол" and result == "ГОЛ") or (choice == "мимо" and result == "МИМО")
    if win:
        win_amount = bet * 1.85 * get_status_multiplier(message.from_user.id)
        update_balance(message.from_user.id, win_amount)
        add_bet(message.from_user.id, "football", bet, win_amount, 1.85)
        await message.answer(f"⚽ {result}\n✅ {fmt_money(win_amount)}")
    else:
        add_bet(message.from_user.id, "football", bet, 0, 0)
        await message.answer(f"⚽ {result}\n❌ {fmt_money(bet)}")
    bal = get_user(message.from_user.id)["balance"]
    await message.answer(f"💰 {fmt_money(bal)}")

# ========================= БАСКЕТБОЛ ==============================
@dp.callback_query(F.data == "game:basket")
async def basket_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="basket")
    await callback.message.answer("🏀 Баскетбол\nВведи ставку:")
    await callback.answer()

@dp.callback_query(GameStates.waiting_choice, F.data.startswith("basket:"))
async def basket_play(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split(":")[1]
    data = await state.get_data()
    bet = data["bet"]
    uid = callback.from_user.id
    update_balance(uid, -bet)
    result, val = basketball_shot()
    win = (choice == "hit" and result == "ПОПАЛ") or (choice == "miss" and result == "ПРОМАХ")
    mult = 2.2
    if win:
        win_amount = bet * mult * get_status_multiplier(uid)
        update_balance(uid, win_amount)
        add_bet(uid, "basketball", bet, win_amount, mult)
        text = f"🏀 {result}\n✅ {fmt_money(win_amount)}"
    else:
        add_bet(uid, "basketball", bet, 0, 0)
        text = f"🏀 {result}\n❌ {fmt_money(bet)}"
    text += f"\n💰 {fmt_money(get_user(uid)['balance'])}"
    await callback.message.answer(text, reply_markup=play_again_kb("basket"))
    await state.clear()
    await callback.answer()

# текстовый баскет
@dp.message(lambda m: m.text and m.text.lower().startswith("баскет"))
async def basket_text_command(message: Message):
    parts = message.text.lower().split()
    if len(parts) != 3:
        await message.answer("❌ баскет 50кк попал|промах")
        return
    try:
        bet = parse_amount(parts[1])
    except:
        await message.answer("❌ Сумма")
        return
    choice = parts[2]
    if choice not in ["попал", "промах"]:
        await message.answer("❌ попал / промах")
        return
    user = get_user(message.from_user.id)
    if user["balance"] < bet:
        await message.answer("❌ Не хватает")
        return
    update_balance(message.from_user.id, -bet)
    result, val = basketball_shot()
    win = (choice == "попал" and result == "ПОПАЛ") or (choice == "промах" and result == "ПРОМАХ")
    if win:
        win_amount = bet * 2.2 * get_status_multiplier(message.from_user.id)
        update_balance(message.from_user.id, win_amount)
        add_bet(message.from_user.id, "basketball", bet, win_amount, 2.2)
        await message.answer(f"🏀 {result}\n✅ {fmt_money(win_amount)}")
    else:
        add_bet(message.from_user.id, "basketball", bet, 0, 0)
        await message.answer(f"🏀 {result}\n❌ {fmt_money(bet)}")
    bal = get_user(message.from_user.id)["balance"]
    await message.answer(f"💰 {fmt_money(bal)}")

# ========================= БАШНЯ ==================================
TOWER_MULTIPLIERS = [1.20, 1.48, 1.86, 2.35, 2.95, 3.75, 4.85, 6.15]
active_towers = {}

class TowerGame:
    def __init__(self, bet):
        self.bet = bet
        self.level = 0
    def play(self, choice):
        safe = random.randint(1, 3)
        if choice == safe:
            self.level += 1
            if self.level >= len(TOWER_MULTIPLIERS):
                return True, TOWER_MULTIPLIERS[-1], True
            return True, TOWER_MULTIPLIERS[self.level-1], False
        return False, 0, True
    def cashout(self):
        if self.level > 0:
            return self.bet * TOWER_MULTIPLIERS[self.level-1]
        return self.bet

def tower_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1️⃣", callback_data="tower:1"),
         InlineKeyboardButton(text="2️⃣", callback_data="tower:2"),
         InlineKeyboardButton(text="3️⃣", callback_data="tower:3")],
        [InlineKeyboardButton(text="💰 Забрать", callback_data="tower:cash")],
        [InlineKeyboardButton(text="❌ Сдаться", callback_data="tower:cancel")],
    ])

@dp.callback_query(F.data == "game:tower")
async def tower_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="tower")
    await callback.message.answer("🗼 Башня\nВведи ставку:")
    await callback.answer()

@dp.message(GameStates.waiting_bet)
async def tower_bet(message: Message, state: FSMContext):
    try:
        bet = parse_amount(message.text)
        if bet < MIN_BET:
            await message.answer(f"❌ Мин {fmt_money(MIN_BET)}")
            return
    except:
        await message.answer("❌ Сумма")
        return
    user = get_user(message.from_user.id)
    if user["balance"] < bet:
        await message.answer(f"❌ Не хватает")
        return
    update_balance(message.from_user.id, -bet)
    game = TowerGame(bet)
    active_towers[message.from_user.id] = game
    await state.clear()
    await message.answer(
        f"🗼 Башня | {fmt_money(bet)}\n"
        f"Уровень 1 → x{TOWER_MULTIPLIERS[0]}\n"
        f"Выбери секцию:",
        reply_markup=tower_kb()
    )

@dp.callback_query(F.data.startswith("tower:"))
async def tower_action(callback: CallbackQuery):
    uid = callback.from_user.id
    game = active_towers.get(uid)
    if not game:
        await callback.answer("Нет игры")
        return
    act = callback.data.split(":")[1]
    if act == "cash":
        win_amount = game.cashout() * get_status_multiplier(uid)
        update_balance(uid, win_amount)
        add_bet(uid, "tower", game.bet, win_amount, win_amount/game.bet if game.bet else 0)
        del active_towers[uid]
        await callback.message.answer(f"🗼 Выигрыш {fmt_money(win_amount)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("tower"))
    elif act == "cancel":
        if game.level == 0:
            update_balance(uid, game.bet)
            await callback.message.answer(f"🗼 Отмена, ставка возвращена.\n💰 {fmt_money(get_user(uid)['balance'])}")
        else:
            await callback.message.answer("❌ Нельзя отменить после хода")
        del active_towers[uid]
    else:
        try:
            choice = int(act)
        except:
            await callback.answer()
            return
        win, mult, finished = game.play(choice)
        if not win:
            add_bet(uid, "tower", game.bet, 0, 0)
            del active_towers[uid]
            await callback.message.answer(f"🗼 Ловушка! Проигрыш {fmt_money(game.bet)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("tower"))
        elif finished:
            win_amount = game.bet * mult * get_status_multiplier(uid)
            update_balance(uid, win_amount)
            add_bet(uid, "tower", game.bet, win_amount, mult)
            del active_towers[uid]
            await callback.message.answer(f"🗼 ПРОХОД! {fmt_money(win_amount)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("tower"))
        else:
            next_mult = TOWER_MULTIPLIERS[game.level] if game.level < len(TOWER_MULTIPLIERS) else TOWER_MULTIPLIERS[-1]
            await callback.message.edit_text(
                f"🗼 Уровень {game.level} пройден!\n"
                f"Текущий множитель x{mult}\n"
                f"Следующий x{next_mult}\n"
                f"💰 {fmt_money(game.bet * mult)}\n"
                f"Выбери дальше:",
                reply_markup=tower_kb()
            )
    await callback.answer()# onemi_bot/bot.py — часть 4 из 6 (алмазы, мины, очко, золото)

# ========================= АЛМАЗЫ =================================
DIAMOND_MULTIPLIERS = [1.12, 1.28, 1.48, 1.72, 2.02, 2.4, 2.92, 3.6]
active_diamonds = {}

class DiamondGame:
    def __init__(self, bet, mines):
        self.bet = bet
        self.mines = mines
        self.level = 0
    def play(self, choice):
        safe = random.randint(1, 5)
        if choice == safe:
            self.level += 1
            if self.level >= len(DIAMOND_MULTIPLIERS):
                return True, DIAMOND_MULTIPLIERS[-1], True
            return True, DIAMOND_MULTIPLIERS[self.level-1], False
        return False, 0, True
    def cashout(self):
        if self.level > 0:
            return self.bet * DIAMOND_MULTIPLIERS[self.level-1]
        return self.bet

def diamond_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎1", callback_data="diamond:1"),
         InlineKeyboardButton(text="💎2", callback_data="diamond:2"),
         InlineKeyboardButton(text="💎3", callback_data="diamond:3")],
        [InlineKeyboardButton(text="💎4", callback_data="diamond:4"),
         InlineKeyboardButton(text="💎5", callback_data="diamond:5")],
        [InlineKeyboardButton(text="💰 Забрать", callback_data="diamond:cash")],
    ])

@dp.callback_query(F.data == "game:diamond")
async def diamond_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="diamond")
    await callback.message.answer("💎 Алмазы\nВведи ставку:")
    await callback.answer()

@dp.message(GameStates.waiting_bet)
async def diamond_bet(message: Message, state: FSMContext):
    try:
        bet = parse_amount(message.text)
        if bet < MIN_BET:
            await message.answer(f"❌ Мин {fmt_money(MIN_BET)}")
            return
    except:
        await message.answer("❌ Сумма")
        return
    user = get_user(message.from_user.id)
    if user["balance"] < bet:
        await message.answer("❌ Не хватает")
        return
    update_balance(message.from_user.id, -bet)
    game = DiamondGame(bet, 1)
    active_diamonds[message.from_user.id] = game
    await state.clear()
    await message.answer(f"💎 Алмазы | {fmt_money(bet)}\nВыбери ячейку:", reply_markup=diamond_kb())

@dp.callback_query(F.data.startswith("diamond:"))
async def diamond_action(callback: CallbackQuery):
    uid = callback.from_user.id
    game = active_diamonds.get(uid)
    if not game:
        await callback.answer("Нет игры")
        return
    act = callback.data.split(":")[1]
    if act == "cash":
        win_amount = game.cashout() * get_status_multiplier(uid)
        update_balance(uid, win_amount)
        add_bet(uid, "diamond", game.bet, win_amount, win_amount/game.bet if game.bet else 0)
        del active_diamonds[uid]
        await callback.message.answer(f"💎 Выигрыш {fmt_money(win_amount)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("diamond"))
    else:
        try:
            choice = int(act)
        except:
            await callback.answer()
            return
        win, mult, finished = game.play(choice)
        if not win:
            add_bet(uid, "diamond", game.bet, 0, 0)
            del active_diamonds[uid]
            await callback.message.answer(f"💎 Бракованный алмаз! Проигрыш {fmt_money(game.bet)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("diamond"))
        elif finished:
            win_amount = game.bet * mult * get_status_multiplier(uid)
            update_balance(uid, win_amount)
            add_bet(uid, "diamond", game.bet, win_amount, mult)
            del active_diamonds[uid]
            await callback.message.answer(f"💎 ПОЛНЫЙ ПРОХОД! {fmt_money(win_amount)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("diamond"))
        else:
            await callback.message.edit_text(f"💎 Уровень {game.level} пройден! x{mult}\nСледующий уровень:", reply_markup=diamond_kb())
    await callback.answer()

# ========================= МИНЫ ===================================
active_mines = {}

class MinesGame:
    def __init__(self, bet, mines):
        self.bet = bet
        self.mines = mines
        self.opened = set()
        self.all_cells = list(range(1,10))
        self.bomb_cells = set(random.sample(self.all_cells, mines))
    def open(self, cell):
        if cell in self.bomb_cells:
            return False, 0
        self.opened.add(cell)
        safe_needed = 9 - self.mines
        mult = (9 / safe_needed) ** len(self.opened) * 0.95 if len(self.opened) > 0 else 1.0
        if len(self.opened) >= safe_needed:
            return True, mult
        return True, mult
    def get_mult(self):
        if len(self.opened) == 0:
            return 1.0
        safe_needed = 9 - self.mines
        return (9 / safe_needed) ** len(self.opened) * 0.95
    def get_potential(self):
        return self.bet * self.get_mult()

def mines_kb(game):
    kb = []
    row = []
    for i in range(1,10):
        if i in game.opened:
            row.append(InlineKeyboardButton(text="✅", callback_data="mines:noop"))
        else:
            row.append(InlineKeyboardButton(text=str(i), callback_data=f"mines:cell:{i}"))
        if len(row) == 3:
            kb.append(row); row = []
    kb.append([InlineKeyboardButton(text=f"💰 Забрать {fmt_money(game.get_potential())}", callback_data="mines:cash")])
    kb.append([InlineKeyboardButton(text="❌ Сдаться", callback_data="mines:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.callback_query(F.data == "game:mines")
async def mines_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="mines")
    await callback.message.answer("💣 Мины 3x3\nВведи ставку:")
    await callback.answer()

@dp.message(GameStates.waiting_bet)
async def mines_bet(message: Message, state: FSMContext):
    try:
        bet = parse_amount(message.text)
        if bet < MIN_BET:
            await message.answer(f"❌ Мин {fmt_money(MIN_BET)}")
            return
    except:
        await message.answer("❌ Сумма")
        return
    user = get_user(message.from_user.id)
    if user["balance"] < bet:
        await message.answer(f"❌ Не хватает")
        return
    update_balance(message.from_user.id, -bet)
    await state.update_data(bet=bet)
    await state.set_state(GameStates.waiting_number)
    await message.answer(f"Сколько мин? (1-5)")

@dp.message(GameStates.waiting_number)
async def mines_mines(message: Message, state: FSMContext):
    try:
        mines = int(message.text)
        if mines < 1 or mines > 5:
            await message.answer("❌ 1-5")
            return
    except:
        await message.answer("❌ Число")
        return
    data = await state.get_data()
    bet = data["bet"]
    uid = message.from_user.id
    game = MinesGame(bet, mines)
    active_mines[uid] = game
    await state.clear()
    await message.answer(f"💣 Мины | {fmt_money(bet)} | мин:{mines}\nОткрывай клетки:", reply_markup=mines_kb(game))

@dp.callback_query(F.data.startswith("mines:"))
async def mines_action(callback: CallbackQuery):
    uid = callback.from_user.id
    game = active_mines.get(uid)
    if not game:
        await callback.answer("Нет игры")
        return
    act = callback.data.split(":")[1]
    if act == "cash":
        if len(game.opened) == 0:
            await callback.answer("Сначала открой клетку")
            return
        win_amount = game.bet * game.get_mult() * get_status_multiplier(uid)
        update_balance(uid, win_amount)
        add_bet(uid, "mines", game.bet, win_amount, game.get_mult())
        del active_mines[uid]
        await callback.message.answer(f"💣 Забрано {fmt_money(win_amount)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("mines"))
    elif act == "cancel":
        if len(game.opened) == 0:
            update_balance(uid, game.bet)
            await callback.message.answer(f"💣 Отмена, возврат {fmt_money(game.bet)}")
        else:
            await callback.message.answer("❌ Нельзя отменить после хода")
        del active_mines[uid]
    elif act == "cell":
        cell = int(act.split(":")[-1])
        if cell in game.opened:
            await callback.answer("Уже открыто")
            return
        win, mult = game.open(cell)
        if not win:
            add_bet(uid, "mines", game.bet, 0, 0)
            del active_mines[uid]
            await callback.message.answer(f"💣 МИНА! Проигрыш {fmt_money(game.bet)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("mines"))
        else:
            if len(game.opened) >= (9 - game.mines):
                win_amount = game.bet * mult * get_status_multiplier(uid)
                update_balance(uid, win_amount)
                add_bet(uid, "mines", game.bet, win_amount, mult)
                del active_mines[uid]
                await callback.message.answer(f"💣 ВСЕ КЛЕТКИ! {fmt_money(win_amount)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("mines"))
            else:
                await callback.message.edit_text(f"💣 Безопасно! Множитель x{mult:.2f}\nПотенциал {fmt_money(game.get_potential())}", reply_markup=mines_kb(game))
    elif act == "noop":
        await callback.answer()
    await callback.answer()

# ========================= ОЧКО (BLACKJACK) =======================
active_ochko = {}

def make_deck():
    suits = ["♠","♥","♦","♣"]
    ranks = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
    deck = [f"{r}{s}" for r in ranks for s in suits]
    random.shuffle(deck)
    return deck

def card_value(card):
    r = card[:-1]
    if r in ["J","Q","K"]:
        return 10
    if r == "A":
        return 11
    return int(r)

def calc_hand(hand):
    val = sum(card_value(c) for c in hand)
    aces = sum(1 for c in hand if c[:-1] == "A")
    while val > 21 and aces:
        val -= 10
        aces -= 1
    return val

@dp.callback_query(F.data == "game:blackjack")
async def ochko_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="blackjack")
    await callback.message.answer("🎴 Очко (блэкджек)\nВведи ставку:")
    await callback.answer()

@dp.message(GameStates.waiting_bet)
async def ochko_bet(message: Message, state: FSMContext):
    try:
        bet = parse_amount(message.text)
        if bet < MIN_BET:
            await message.answer(f"❌ Мин {fmt_money(MIN_BET)}")
            return
    except:
        await message.answer("❌ Сумма")
        return
    user = get_user(message.from_user.id)
    if user["balance"] < bet:
        await message.answer(f"❌ Не хватает")
        return
    update_balance(message.from_user.id, -bet)
    deck = make_deck()
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]
    pv = calc_hand(player)
    dv = calc_hand(dealer)
    game_data = {"bet": bet, "deck": deck, "player": player, "dealer": dealer, "pv": pv, "dv": dv}
    active_ochko[message.from_user.id] = game_data
    if pv == 21:
        if dv == 21:
            update_balance(message.from_user.id, bet)
            add_bet(message.from_user.id, "blackjack", bet, bet, 1)
            await message.answer(f"🎴 Ничья 21!\n💰 {fmt_money(get_user(message.from_user.id)['balance'])}", reply_markup=play_again_kb("blackjack"))
        else:
            win_amount = bet * 2.5 * get_status_multiplier(message.from_user.id)
            update_balance(message.from_user.id, win_amount)
            add_bet(message.from_user.id, "blackjack", bet, win_amount, 2.5)
            await message.answer(f"🎴 BLACKJACK! {fmt_money(win_amount)}\n💰 {fmt_money(get_user(message.from_user.id)['balance'])}", reply_markup=play_again_kb("blackjack"))
        del active_ochko[message.from_user.id]
    else:
        await state.clear()
        await message.answer(
            f"🎴 Ставка {fmt_money(bet)}\n"
            f"Дилер: {dealer[0]} ?\n"
            f"Вы: {player} ({pv})\n"
            f"Ход:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Взять", callback_data="ochko:hit"),
                 InlineKeyboardButton(text="✋ Стоп", callback_data="ochko:stand")]
            ])
        )

@dp.callback_query(F.data.startswith("ochko:"))
async def ochko_action(callback: CallbackQuery):
    uid = callback.from_user.id
    game = active_ochko.get(uid)
    if not game:
        await callback.answer("Нет игры")
        return
    if callback.data == "ochko:hit":
        if not game["deck"]:
            game["deck"] = make_deck()
        card = game["deck"].pop()
        game["player"].append(card)
        game["pv"] = calc_hand(game["player"])
        if game["pv"] > 21:
            add_bet(uid, "blackjack", game["bet"], 0, 0)
            del active_ochko[uid]
            await callback.message.answer(f"🎴 Перебор {game['pv']}\nПроигрыш {fmt_money(game['bet'])}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("blackjack"))
        else:
            await callback.message.edit_text(
                f"🎴 Дилер: {game['dealer'][0]} ?\n"
                f"Вы: {game['player']} ({game['pv']})\n"
                f"Ход:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="➕ Взять", callback_data="ochko:hit"),
                     InlineKeyboardButton(text="✋ Стоп", callback_data="ochko:stand")]
                ])
            )
    elif callback.data == "ochko:stand":
        while game["dv"] < 17:
            if not game["deck"]:
                game["deck"] = make_deck()
            game["dealer"].append(game["deck"].pop())
            game["dv"] = calc_hand(game["dealer"])
        if game["dv"] > 21 or game["pv"] > game["dv"]:
            win_amount = game["bet"] * 2 * get_status_multiplier(uid)
            update_balance(uid, win_amount)
            add_bet(uid, "blackjack", game["bet"], win_amount, 2)
            await callback.message.answer(f"🎴 Вы {game['pv']} : {game['dv']} дилер\n✅ {fmt_money(win_amount)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("blackjack"))
        elif game["pv"] == game["dv"]:
            update_balance(uid, game["bet"])
            add_bet(uid, "blackjack", game["bet"], game["bet"], 1)
            await callback.message.answer(f"🎴 Ничья\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("blackjack"))
        else:
            add_bet(uid, "blackjack", game["bet"], 0, 0)
            await callback.message.answer(f"🎴 Проигрыш {fmt_money(game['bet'])}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("blackjack"))
        del active_ochko[uid]
    await callback.answer()

# ========================= ЗОЛОТО ================================
GOLD_MULTIPLIERS = [1.15, 1.35, 1.62, 2.0, 2.55, 3.25, 4.2]
active_gold = {}

class GoldGame:
    def __init__(self, bet):
        self.bet = bet
        self.level = 0
    def play(self, choice):
        safe = random.randint(1,2)
        if choice == safe:
            self.level += 1
            if self.level >= len(GOLD_MULTIPLIERS):
                return True, GOLD_MULTIPLIERS[-1], True
            return True, GOLD_MULTIPLIERS[self.level-1], False
        return False, 0, True
    def cashout(self):
        if self.level > 0:
            return self.bet * GOLD_MULTIPLIERS[self.level-1]
        return self.bet

def gold_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🥇 1", callback_data="gold:1"),
         InlineKeyboardButton(text="🥇 2", callback_data="gold:2")],
        [InlineKeyboardButton(text="💰 Забрать", callback_data="gold:cash")],
    ])

@dp.callback_query(F.data == "game:gold")
async def gold_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="gold")
    await callback.message.answer("🥇 Золото\nВведи ставку:")
    await callback.answer()

@dp.message(GameStates.waiting_bet)
async def gold_bet(message: Message, state: FSMContext):
    try:
        bet = parse_amount(message.text)
        if bet < MIN_BET:
            await message.answer(f"❌ Мин {fmt_money(MIN_BET)}")
            return
    except:
        await message.answer("❌ Сумма")
        return
    user = get_user(message.from_user.id)
    if user["balance"] < bet:
        await message.answer(f"❌ Не хватает")
        return
    update_balance(message.from_user.id, -bet)
    game = GoldGame(bet)
    active_gold[message.from_user.id] = game
    await state.clear()
    await message.answer(f"🥇 Золото | {fmt_money(bet)}\nВыбери ячейку:", reply_markup=gold_kb())

@dp.callback_query(F.data.startswith("gold:"))
async def gold_action(callback: CallbackQuery):
    uid = callback.from_user.id
    game = active_gold.get(uid)
    if not game:
        await callback.answer("Нет игры")
        return
    act = callback.data.split(":")[1]
    if act == "cash":
        win_amount = game.cashout() * get_status_multiplier(uid)
        update_balance(uid, win_amount)
        add_bet(uid, "gold", game.bet, win_amount, win_amount/game.bet if game.bet else 0)
        del active_gold[uid]
        await callback.message.answer(f"🥇 Выигрыш {fmt_money(win_amount)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("gold"))
    else:
        try:
            choice = int(act)
        except:
            await callback.answer()
            return
        win, mult, finished = game.play(choice)
        if not win:
            add_bet(uid, "gold", game.bet, 0, 0)
            del active_gold[uid]
            await callback.message.answer(f"🥇 Ловушка! Проигрыш {fmt_money(game.bet)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("gold"))
        elif finished:
            win_amount = game.bet * mult * get_status_multiplier(uid)
            update_balance(uid, win_amount)
            add_bet(uid, "gold", game.bet, win_amount, mult)
            del active_gold[uid]
            await callback.message.answer(f"🥇 ПОЛНЫЙ ПРОХОД! {fmt_money(win_amount)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("gold"))
        else:
            next_mult = GOLD_MULTIPLIERS[game.level] if game.level < len(GOLD_MULTIPLIERS) else GOLD_MULTIPLIERS[-1]
            await callback.message.edit_text(f"🥇 Уровень {game.level} пройден! x{mult}\nСледующий x{next_mult}\nВыбери:", reply_markup=gold_kb())
    await callback.answer()# onemi_bot/bot.py — часть 5 из 6 (банк, переводы, чеки с кнопками)

# ========================= БАНК (ДЕПОЗИТЫ) =======================
@dp.callback_query(F.data == "bank:open")
async def bank_open(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BankOpen.amount)
    await callback.message.answer("🏦 Введи сумму депозита (мин 100):")
    await callback.answer()

@dp.message(BankOpen.amount)
async def bank_amount(message: Message, state: FSMContext):
    try:
        amount = parse_amount(message.text)
        if amount < 100:
            await message.answer("❌ Мин 100")
            return
    except:
        await message.answer("❌ Сумма")
        return
    user = get_user(message.from_user.id)
    if user["balance"] < amount:
        await message.answer(f"❌ Не хватает")
        return
    await state.update_data(amount=amount)
    await message.answer("Выбери срок:", reply_markup=bank_terms_kb())

@dp.callback_query(F.data.startswith("bank:term:"))
async def bank_term(callback: CallbackQuery, state: FSMContext):
    term = int(callback.data.split(":")[2])
    data = await state.get_data()
    amount = data.get("amount")
    if not amount:
        await callback.message.answer("❌ Ошибка")
        await state.clear()
        return
    ok, msg = open_deposit(callback.from_user.id, amount, term)
    await callback.message.answer(msg)
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "bank:list")
async def bank_list(callback: CallbackQuery):
    deps = get_active_deposits(callback.from_user.id)
    if not deps:
        await callback.message.answer("📭 Нет активных депозитов")
    else:
        text = "🏦 Ваши депозиты:\n"
        for d in deps:
            text += f"#{d['id']} | {fmt_money(d['amount'])} | {d['term_days']} дн | +{int(d['rate']*100)}%\n"
        await callback.message.answer(text)
    await callback.answer()

@dp.callback_query(F.data == "bank:claim")
async def bank_claim(callback: CallbackQuery):
    cnt, total = close_matured_deposits(callback.from_user.id)
    if cnt == 0:
        await callback.message.answer("📭 Нет созревших депозитов")
    else:
        await callback.message.answer(f"✅ Закрыто {cnt} депозитов, получено {fmt_money(total)}")
    await callback.answer()

@dp.callback_query(F.data == "bank:cancel")
async def bank_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("🛑 Отменено")
    await callback.answer()

# ========================= ЧЕКИ (С КНОПКАМИ) =====================
@dp.callback_query(F.data == "checks:create")
async def create_check_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CheckCreate.amount)
    await callback.message.answer("🧾 Сумма на 1 активацию (мин 10):")
    await callback.answer()

@dp.message(CheckCreate.amount)
async def create_check_amount(message: Message, state: FSMContext):
    try:
        amount = parse_amount(message.text)
        if amount < 10:
            await message.answer("❌ Мин 10")
            return
    except:
        await message.answer("❌ Сумма")
        return
    await state.update_data(amount=amount)
    await state.set_state(CheckCreate.count)
    await message.answer("Количество активаций (1-100):")

@dp.message(CheckCreate.count)
async def create_check_count(message: Message, state: FSMContext):
    try:
        count = int(message.text)
        if count < 1 or count > 100:
            await message.answer("❌ 1-100")
            return
    except:
        await message.answer("❌ Число")
        return
    data = await state.get_data()
    amount = data["amount"]
    ok, code = create_check(message.from_user.id, amount, count)
    if not ok:
        await message.answer(ok)
    else:
        await message.answer(
            f"✅ Чек {code}\n"
            f"Сумма {fmt_money(amount)} x {count} = {fmt_money(amount*count)}\n"
            f"Твой баланс: {fmt_money(get_user(message.from_user.id)['balance'])}",
            reply_markup=share_check_kb(code, amount)
        )
    await state.clear()

@dp.callback_query(F.data == "checks:claim")
async def claim_check_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CheckClaim.code)
    await callback.message.answer("Введи код чека:")
    await callback.answer()

@dp.message(CheckClaim.code)
async def claim_check_code(message: Message, state: FSMContext):
    ok, msg, _ = claim_check(message.from_user.id, message.text.strip())
    await message.answer(msg)
    await state.clear()

@dp.callback_query(F.data == "checks:my")
async def my_checks(callback: CallbackQuery):
    checks = get_my_checks(callback.from_user.id)
    if not checks:
        await callback.message.answer("📭 У тебя нет созданных чеков")
    else:
        txt = "🧾 Твои чеки:\n"
        for ch in checks:
            txt += f"🔑 {ch['code']} | {fmt_money(ch['amount'])} | осталось {ch['remaining']}\n"
        await callback.message.answer(txt)
    await callback.answer()

@dp.callback_query(F.data.startswith("copy_check:"))
async def copy_check(callback: CallbackQuery):
    code = callback.data.split(":")[1]
    await callback.answer(f"✅ Код скопирован: {code}", show_alert=True)
    await callback.message.answer(f"📋 Код: `{code}`", parse_mode="Markdown")

# ========================= ПРОМОКОДЫ =============================
@dp.callback_query(F.data == "admin:create_promo")
async def admin_create_promo_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔")
        return
    await state.set_state(NewPromoStates.waiting_code)
    await callback.message.answer("🎟 Введи код промокода (A-Z,0-9,_,-):")
    await callback.answer()

@dp.message(NewPromoStates.waiting_code)
async def admin_promo_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    if not code or len(code) < 3:
        await message.answer("❌ 3+ символа")
        return
    await state.update_data(code=code)
    await state.set_state(NewPromoStates.waiting_reward)
    await message.answer("💰 Награда (число):")

@dp.message(NewPromoStates.waiting_reward)
async def admin_promo_reward(message: Message, state: FSMContext):
    try:
        reward = parse_amount(message.text)
    except:
        await message.answer("❌ Сумма")
        return
    await state.update_data(reward=reward)
    await state.set_state(NewPromoStates.waiting_activations)
    await message.answer("🎯 Количество активаций:")

@dp.message(NewPromoStates.waiting_activations)
async def admin_promo_acts(message: Message, state: FSMContext):
    try:
        acts = int(message.text)
        if acts <= 0:
            await message.answer("❌ >0")
            return
    except:
        await message.answer("❌ Число")
        return
    data = await state.get_data()
    ok = create_promo(data["code"], data["reward"], acts)
    if ok:
        await message.answer(f"✅ Промокод {data['code']} создан\nНаграда {fmt_money(data['reward'])} | {acts} активаций")
        log_admin(message.from_user.id, "create_promo", None, f"{data['code']} {data['reward']} {acts}")
    else:
        await message.answer("❌ Такой код уже есть")
    await state.clear()# onemi_bot/bot.py — часть 6 из 6 (админка, топ с никами, запуск)

# ========================= АДМИН-ПАНЕЛЬ =========================
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    await message.answer("👑 Админ-панель", reply_markup=admin_main_kb())

@dp.callback_query(F.data == "admin:give")
async def admin_give(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔")
        return
    await state.set_state(AdminGive.target)
    await callback.message.answer("💰 Введи ID пользователя и сумму:\n123456789 500кк")
    await callback.answer()

@dp.message(AdminGive.target)
async def admin_give_execute(message: Message, state: FSMContext):
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ ID сумма")
        return
    try:
        uid = int(parts[0])
        amount = parse_amount(parts[1])
    except:
        await message.answer("❌ Ошибка")
        return
    update_balance(uid, amount)
    log_admin(message.from_user.id, "give", str(uid), f"{amount}")
    await message.answer(f"✅ Выдано {fmt_money(amount)} пользователю {get_user(uid)['name']}")
    await state.clear()

@dp.callback_query(F.data == "admin:status")
async def admin_status(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔")
        return
    await state.set_state(AdminStatus.target)
    await callback.message.answer("👑 Введи ID пользователя:")
    await callback.answer()

@dp.message(AdminStatus.target)
async def admin_status_target(message: Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
    except:
        await message.answer("❌ ID")
        return
    await state.update_data(target=uid)
    await state.set_state(AdminStatus.status)
    await message.answer("Выбери новый статус:", reply_markup=admin_status_kb())

@dp.callback_query(AdminStatus.status, F.data.startswith("admin:set_status:"))
async def admin_set_status(callback: CallbackQuery, state: FSMContext):
    status = int(callback.data.split(":")[2])
    data = await state.get_data()
    uid = data["target"]
    set_user_status(uid, status)
    log_admin(callback.from_user.id, "set_status", str(uid), str(status))
    await callback.message.answer(f"✅ Статус {uid} изменён на {USER_STATUSES[status]['name']}")
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "admin:users")
async def admin_list_users(callback: CallbackQuery):
    users = get_all_users()
    text = "👥 Игроки:\n"
    for u in users[:20]:
        text += f"{u['name']} ({u['id']}) — {fmt_money(u['balance'])}\n"
    await callback.message.answer(text)
    await callback.answer()

@dp.callback_query(F.data == "admin:broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔")
        return
    await state.set_state(AdminBroadcastStates.waiting_message)
    await callback.message.answer("📢 Введи текст рассылки:")
    await callback.answer()

@dp.message(AdminBroadcastStates.waiting_message)
async def admin_broadcast_send(message: Message, state: FSMContext):
    text = message.html_text
    users = get_all_users()
    sent = 0
    for u in users:
        if u["is_banned"]:
            continue
        try:
            await message.bot.send_message(int(u["id"]), f"📢 Рассылка\n\n{text}")
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass
    log_admin(message.from_user.id, "broadcast", None, f"sent={sent}")
    await message.answer(f"✅ Отправлено {sent} пользователям")
    await state.clear()

@dp.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT SUM(balance) FROM users")
    total_bal = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM bets")
    bets = c.fetchone()[0]
    conn.close()
    await callback.message.answer(
        f"📊 Статистика:\n"
        f"👥 {users} игроков\n"
        f"💰 {fmt_money(total_bal)} в обороте\n"
        f"🎲 {bets} ставок"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin:promos")
async def admin_promos_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔")
        return
    await callback.message.answer("🎟 Управление промо:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать", callback_data="admin:create_promo")],
        [InlineKeyboardButton(text="📋 Список", callback_data="admin:list_promos")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back")],
    ]))
    await callback.answer()

@dp.callback_query(F.data == "admin:list_promos")
async def admin_list_promos(callback: CallbackQuery):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT code, reward, remaining FROM promos")
    rows = c.fetchall()
    conn.close()
    if not rows:
        await callback.message.answer("📭 Нет промокодов")
    else:
        txt = "🎟 Промокоды:\n"
        for r in rows:
            txt += f"{r[0]} | {fmt_money(r[1])} | осталось {r[2]}\n"
        await callback.message.answer(txt)
    await callback.answer()

@dp.callback_query(F.data == "admin:checks")
async def admin_all_checks(callback: CallbackQuery):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT code, creator_id, amount, remaining FROM checks ORDER BY rowid DESC LIMIT 20")
    rows = c.fetchall()
    conn.close()
    if not rows:
        await callback.message.answer("📭 Нет чеков")
    else:
        txt = "🧾 Последние чеки:\n"
        for r in rows:
            txt += f"{r[0]} | {fmt_money(r[2])} | ост:{r[3]} | от {r[1]}\n"
        await callback.message.answer(txt)
    await callback.answer()

@dp.callback_query(F.data == "admin:ban")
async def admin_ban_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔")
        return
    await state.set_state(AdminStatus.target)
    await state.update_data(action="ban")
    await callback.message.answer("🚫 Введи ID для бана:\n(причина через пробел)")
    await callback.answer()

@dp.message(AdminStatus.target)
async def admin_ban_execute(message: Message, state: FSMContext):
    data = await state.get_data()
    act = data.get("action")
    if act == "ban":
        parts = message.text.strip().split(maxsplit=1)
        uid = int(parts[0])
        reason = parts[1] if len(parts) > 1 else ""
        ban_user(uid, reason)
        log_admin(message.from_user.id, "ban", str(uid), reason)
        await message.answer(f"🚫 Пользователь {uid} забанен")
    elif act == "unban":
        uid = int(message.text.strip())
        unban_user(uid)
        log_admin(message.from_user.id, "unban", str(uid), "")
        await message.answer(f"✅ Пользователь {uid} разбанен")
    await state.clear()

@dp.callback_query(F.data == "admin:close")
async def admin_close(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(F.data == "admin:back")
async def admin_back(callback: CallbackQuery):
    await callback.message.edit_text("👑 Админ-панель", reply_markup=admin_main_kb())
    await callback.answer()

# ========================= ЗАПУСК БОТА ===========================
async def main():
    init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    print("✅ ONEmi Game Bot запущен")
    print(f"👑 Админы: {ADMIN_IDS}")
    print(f"💰 Валюта: {CURRENCY}")
    print("🎮 Все игры активны: рулетка, краш, кубик, кости, футбол, баскет, башня, алмазы, мины, очко, золото")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
