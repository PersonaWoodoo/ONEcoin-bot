import asyncio
import random
import sqlite3
import time
import json
import string
from datetime import datetime
from typing import Optional, Tuple, Dict, List

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "8754529808:AAE5IEhizXS1sj6nm1n42KvdBN5XcdLm5dk"
ADMIN_IDS = [8478884644, 6016437346]
CURRENCY = "ONEmi"
START_BALANCE = 100.0
MIN_BET = 10.0
MAX_BET = 100_000_000_000
BONUS_COOLDOWN = 12 * 60 * 60
BONUS_MIN = 50
BONUS_MAX = 250
TRANSFER_COMMISSION = 0.03
TRANSFER_MAX = 10_000_000
DB_PATH = "onemi_bot.db"

# ==================== СТАТУСЫ ИГРОКОВ ====================
STATUSES = {
    0: {"name": "🟢 Обычный", "emoji": "🟢", "mult": 1.00},
    1: {"name": "🟡 Продвинутый", "emoji": "🟡", "mult": 1.05},
    2: {"name": "🔴 VIP", "emoji": "🔴", "mult": 1.10},
    3: {"name": "🟣 Премиум", "emoji": "🟣", "mult": 1.15},
    4: {"name": "👑 Легенда", "emoji": "👑", "mult": 1.25},
    5: {"name": "⚡ Создатель", "emoji": "⚡", "mult": 1.50},
}

# ==================== БАНКОВСКИЕ ПРОЦЕНТЫ ====================
BANK_TERMS = {
    7:  {"rate": 0.03, "name": "7 дней (+3%)"},
    14: {"rate": 0.07, "name": "14 дней (+7%)"},
    30: {"rate": 0.18, "name": "30 дней (+18%)"},
}

# ==================== ИГРОВЫЕ МНОЖИТЕЛИ ====================
RED_NUMBERS = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
TOWER_MULT = [1.20, 1.48, 1.86, 2.35, 2.95, 3.75, 4.85, 6.15]
DIAMOND_MULT = [1.12, 1.28, 1.48, 1.72, 2.02, 2.4, 2.92, 3.6]
GOLD_MULT = [1.15, 1.35, 1.62, 2.0, 2.55, 3.25, 4.2]

# ==================== СОСТОЯНИЯ FSM ====================
class GameStates(StatesGroup):
    waiting_bet = State()
    waiting_crash_target = State()
    waiting_mines_count = State()

class CreateCheck(StatesGroup):
    amount = State()
    count = State()

class ClaimCheck(StatesGroup):
    code = State()

class PromoRedeem(StatesGroup):
    code = State()

class NewPromoStates(StatesGroup):
    code = State()
    reward = State()
    activations = State()

class BankDeposit(StatesGroup):
    amount = State()

class TransferState(StatesGroup):
    target = State()
    amount = State()

class AdminGive(StatesGroup):
    target = State()
    amount = State()

class AdminStatus(StatesGroup):
    target = State()

class AdminBan(StatesGroup):
    target = State()

class AdminBroadcast(StatesGroup):
    text = State()

# ==================== ФОРМАТ ВАЛЮТЫ ====================
def parse_amount(text: str) -> float:
    raw = text.lower().replace(" ", "").replace(",", ".")
    mult = 1.0
    if raw.endswith("ккккк"): mult, raw = 100_000_000_000_000, raw[:-5]
    elif raw.endswith("кккк"): mult, raw = 1_000_000_000_000, raw[:-4]
    elif raw.endswith("ккк"): mult, raw = 1_000_000_000, raw[:-3]
    elif raw.endswith("кк"): mult, raw = 1_000_000, raw[:-2]
    elif raw.endswith("к"): mult, raw = 1_000, raw[:-1]
    elif raw.endswith("b"): mult, raw = 1_000_000_000, raw[:-1]
    elif raw.endswith("m"): mult, raw = 1_000_000, raw[:-1]
    try:
        val = float(raw) if raw else 0
    except:
        val = 0
    return round(val * mult, 2)

def fmt_amount(v: float) -> str:
    if v >= 1_000_000_000_000: return f"{v/1_000_000_000_000:.2f}ккккк".rstrip('0').rstrip('.').rstrip('0').rstrip('.')
    if v >= 1_000_000_000: return f"{v/1_000_000_000:.2f}ккк".rstrip('0').rstrip('.').rstrip('0').rstrip('.')
    if v >= 1_000_000: return f"{v/1_000_000:.2f}кк".rstrip('0').rstrip('.').rstrip('0').rstrip('.')
    if v >= 1_000: return f"{v/1_000:.2f}к".rstrip('0').rstrip('.').rstrip('0').rstrip('.')
    return f"{v:.2f}".rstrip('0').rstrip('.') if v == int(v) else f"{v:.2f}"

def fmt_money(v: float) -> str:
    return f"{fmt_amount(v)} {CURRENCY}"

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, name TEXT, balance REAL, status INTEGER,
        total_bets INTEGER, total_wins INTEGER, total_win REAL,
        joined_at INTEGER, last_active INTEGER, is_banned INTEGER, ban_reason TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS bets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, game TEXT,
        bet REAL, win REAL, mult REAL, ts INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS checks (
        code TEXT PRIMARY KEY, creator_id TEXT, amount REAL, remaining INTEGER, claimed TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS promos (
        code TEXT PRIMARY KEY, reward REAL, remaining INTEGER, claimed TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, amount REAL,
        term INTEGER, rate REAL, opened_at INTEGER, status TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS daily_bonus (
        user_id TEXT PRIMARY KEY, last_claim INTEGER, streak INTEGER DEFAULT 1
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id TEXT, action TEXT,
        target TEXT, details TEXT, ts INTEGER
    )''')
    conn.commit()
    conn.close()

def now_ts() -> int:
    return int(time.time())

def get_user(uid: int, name: str = None) -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (str(uid),))
    row = c.fetchone()
    if not row:
        ts = now_ts()
        uname = name or f"User{uid}"
        c.execute("INSERT INTO users (id,name,balance,joined_at,last_active) VALUES (?,?,?,?,?)",
                  (str(uid), uname, START_BALANCE, ts, ts))
        conn.commit()
        c.execute("SELECT * FROM users WHERE id = ?", (str(uid),))
        row = c.fetchone()
    conn.close()
    return {
        "id": row[0], "name": row[1], "balance": row[2], "status": row[3],
        "total_bets": row[4], "total_wins": row[5], "total_win": row[6],
        "joined_at": row[7], "last_active": row[8], "is_banned": row[9]
    }

def update_balance(uid: int, delta: float) -> float:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ?, last_active = ? WHERE id = ?",
              (round(delta,2), now_ts(), str(uid)))
    conn.commit()
    c.execute("SELECT balance FROM users WHERE id = ?", (str(uid),))
    bal = c.fetchone()[0]
    conn.close()
    return bal

def get_multiplier(uid: int) -> float:
    user = get_user(uid)
    return STATUSES.get(user["status"], STATUSES[0])["mult"]

def add_bet(uid: int, game: str, bet: float, win: float, mult: float):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO bets (user_id,game,bet,win,mult,ts) VALUES (?,?,?,?,?,?)",
              (str(uid), game, round(bet,2), round(win,2), mult, now_ts()))
    c.execute("UPDATE users SET total_bets = total_bets + 1 WHERE id = ?", (str(uid),))
    if win > 0:
        c.execute("UPDATE users SET total_wins = total_wins + 1, total_win = total_win + ? WHERE id = ?",
                  (round(win,2), str(uid)))
    conn.commit()
    conn.close()

def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS

def log_admin(aid: int, action: str, target: str = None, details: str = ""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO admin_logs (admin_id,action,target,details,ts) VALUES (?,?,?,?,?)",
              (str(aid), action, target, details, now_ts()))
    conn.commit()
    conn.close()

def set_user_status(uid: int, status: int):
    if status in STATUSES:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET status = ? WHERE id = ?", (status, str(uid)))
        conn.commit()
        conn.close()

def ban_user(uid: int, reason: str = ""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET is_banned = 1, ban_reason = ? WHERE id = ?", (reason, str(uid)))
    conn.commit()
    conn.close()

def unban_user(uid: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET is_banned = 0, ban_reason = NULL WHERE id = ?", (str(uid),))
    conn.commit()
    conn.close()

def is_banned(uid: int) -> bool:
    user = get_user(uid)
    return user.get("is_banned", 0) == 1

def get_top_users(limit: int = 10) -> List[dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, balance, status FROM users WHERE is_banned = 0 ORDER BY balance DESC LIMIT ?", (limit,))
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

def get_total_stats() -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT SUM(balance) FROM users")
    total = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM bets")
    bets = c.fetchone()[0]
    conn.close()
    return {"users": users, "total_balance": total, "total_bets": bets}

# ==================== БОНУС ====================
def claim_bonus(uid: int):
    now = now_ts()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT last_claim, streak FROM daily_bonus WHERE user_id = ?", (str(uid),))
    row = c.fetchone()
    if row and now - row[0] < BONUS_COOLDOWN:
        rem = BONUS_COOLDOWN - (now - row[0])
        conn.close()
        return False, rem, 0, row[1]
    streak = 1 if not row else (row[1] + 1 if now - row[0] < BONUS_COOLDOWN + 86400 else 1)
    bonus = random.randint(BONUS_MIN, BONUS_MAX)
    bonus = int(bonus * min(1.5, 1 + streak * 0.05))
    update_balance(uid, bonus)
    c.execute("INSERT OR REPLACE INTO daily_bonus (user_id, last_claim, streak) VALUES (?,?,?)",
              (str(uid), now, streak))
    conn.commit()
    conn.close()
    return True, 0, bonus, streak

# ==================== ПЕРЕВОДЫ ====================
def transfer_coins(from_id: int, to_id: int, amount: float):
    if amount <= 0 or amount > TRANSFER_MAX:
        return False, f"Сумма от 1 до {fmt_money(TRANSFER_MAX)}"
    if from_id == to_id:
        return False, "Нельзя перевести самому себе"
    sender = get_user(from_id)
    if sender["balance"] < amount:
        return False, "Недостаточно средств"
    com = round(amount * TRANSFER_COMMISSION, 2)
    net = round(amount - com, 2)
    update_balance(from_id, -amount)
    update_balance(to_id, net)
    log_admin(from_id, "transfer", str(to_id), f"{amount} -> {net}")
    return True, f"✅ Переведено {fmt_money(net)} → {get_user(to_id)['name']} (ком {fmt_money(com)})"# ==================== ЧЕКИ ====================
def gen_code(): return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def create_check(uid: int, amount: float, cnt: int):
    total = amount * cnt
    if get_user(uid)["balance"] < total:
        return False, "Недостаточно средств"
    update_balance(uid, -total)
    code = gen_code()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO checks (code, creator_id, amount, remaining, claimed) VALUES (?,?,?,?,?)",
              (code, str(uid), amount, cnt, "[]"))
    conn.commit()
    conn.close()
    return True, code

def claim_check(uid: int, code: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM checks WHERE code = ?", (code.upper(),))
    row = c.fetchone()
    if not row: return False, "Чек не найден", 0
    if row[3] <= 0: return False, "Чек уже использован", 0
    claimed = json.loads(row[4])
    if str(uid) in claimed: return False, "Вы уже активировали этот чек", 0
    claimed.append(str(uid))
    c.execute("UPDATE checks SET remaining = ?, claimed = ? WHERE code = ?",
              (row[3]-1, json.dumps(claimed), code.upper()))
    conn.commit()
    conn.close()
    update_balance(uid, row[2])
    return True, "Чек активирован", row[2]

def get_my_checks(uid: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT code, amount, remaining FROM checks WHERE creator_id = ?", (str(uid),))
    rows = c.fetchall()
    conn.close()
    return [{"code": r[0], "amount": r[1], "remaining": r[2]} for r in rows]

# ==================== ПРОМОКОДЫ ====================
def create_promo(code: str, reward: float, acts: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO promos (code, reward, remaining, claimed) VALUES (?,?,?,?)",
                  (code.upper(), reward, acts, "[]"))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def claim_promo(uid: int, code: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM promos WHERE code = ?", (code.upper(),))
    row = c.fetchone()
    if not row: return False, "Промокод не найден", 0
    if row[2] <= 0: return False, "Промокод использован", 0
    claimed = json.loads(row[3])
    if str(uid) in claimed: return False, "Вы уже активировали этот промокод", 0
    claimed.append(str(uid))
    c.execute("UPDATE promos SET remaining = ?, claimed = ? WHERE code = ?",
              (row[2]-1, json.dumps(claimed), code.upper()))
    conn.commit()
    conn.close()
    update_balance(uid, row[1])
    return True, "Промокод активирован", row[1]

def get_all_promos():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT code, reward, remaining FROM promos")
    rows = c.fetchall()
    conn.close()
    return rows

# ==================== БАНК ====================
def open_deposit(uid: int, amount: float, term: int):
    if term not in BANK_TERMS:
        return False, "Неверный срок"
    if amount < 100:
        return False, "Минимальный депозит 100"
    if get_user(uid)["balance"] < amount:
        return False, "Недостаточно средств"
    update_balance(uid, -amount)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO deposits (user_id, amount, term, rate, opened_at, status) VALUES (?,?,?,?,?,?)",
              (str(uid), amount, term, BANK_TERMS[term]["rate"], now_ts(), "active"))
    conn.commit()
    conn.close()
    return True, f"Депозит открыт на {term} дней"

def get_deposits(uid: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, amount, term, rate, opened_at FROM deposits WHERE user_id = ? AND status = 'active'",
              (str(uid),))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "amount": r[1], "term": r[2], "rate": r[3], "opened": r[4]} for r in rows]

def claim_deposits(uid: int):
    now = now_ts()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, amount, rate, term, opened_at FROM deposits WHERE user_id = ? AND status = 'active'",
              (str(uid),))
    deps = c.fetchall()
    total, cnt = 0, 0
    for d in deps:
        if now >= d[4] + d[3] * 86400:
            payout = round(d[1] * (1 + d[2]), 2)
            total += payout
            cnt += 1
            c.execute("UPDATE deposits SET status = 'closed' WHERE id = ?", (d[0],))
    if total > 0:
        update_balance(uid, total)
    conn.commit()
    conn.close()
    return cnt, total

# ==================== ИГРОВАЯ ЛОГИКА ====================
def roulette_spin(choice: str):
    num = random.randint(0,36)
    if num == 0: col = "green"
    elif num in RED_NUMBERS: col = "red"
    else: col = "black"
    win, mult = False, 0
    if choice == "red" and col == "red": win, mult = True, 2
    elif choice == "black" and col == "black": win, mult = True, 2
    elif choice == "even" and num != 0 and num%2==0: win, mult = True, 2
    elif choice == "odd" and num != 0 and num%2==1: win, mult = True, 2
    elif choice == "zero" and num == 0: win, mult = True, 35
    col_ru = {"red":"🔴 красное","black":"⚫ чёрное","green":"🟢 зеро"}[col]
    return win, mult, num, col_ru

def crash_roll(): return round(max(1.0, min(10.0, 0.99/(1.0-random.random()))), 2)
def roll_dice(): return random.randint(1,6)
def two_dice(): return random.randint(1,6)+random.randint(1,6)
def football_kick(): val=random.randint(1,6); return ("ГОЛ" if val>=4 else "МИМО"), val
def basketball_shot(): val=random.randint(1,6); return ("ПОПАЛ" if val>=4 else "ПРОМАХ"), val

# ==================== ИГРЫ С СОСТОЯНИЕМ (башня, алмазы, золото, мины, очко) ====================
active_tower = {}
active_diamond = {}
active_gold = {}
active_mines = {}
active_blackjack = {}

class MinesGame:
    def __init__(self, bet, mines):
        self.bet = bet
        self.mines = mines
        self.opened = set()
        self.bombs = set(random.sample(range(1,10), mines))
    def open(self, cell):
        if cell in self.bombs:
            return False, 0
        self.opened.add(cell)
        safe = 9 - self.mines
        mult = (9 / safe) ** len(self.opened) * 0.95 if len(self.opened) > 0 else 1
        if len(self.opened) >= safe:
            return True, mult
        return True, mult
    def get_mult(self):
        if len(self.opened) == 0: return 1
        safe = 9 - self.mines
        return (9 / safe) ** len(self.opened) * 0.95
    def potential(self):
        return self.bet * self.get_mult()

def make_deck():
    suits = ["♠","♥","♦","♣"]
    ranks = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
    deck = [f"{r}{s}" for r in ranks for s in suits]
    random.shuffle(deck)
    return deck

def card_val(card):
    r = card[:-1]
    if r in ["J","Q","K"]: return 10
    if r == "A": return 11
    return int(r)

def hand_val(cards):
    val = sum(card_val(c) for c in cards)
    aces = sum(1 for c in cards if c[:-1]=="A")
    while val > 21 and aces:
        val -= 10
        aces -= 1
    return val# ==================== КЛАВИАТУРЫ ====================
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Баланс", callback_data="bal"),
         InlineKeyboardButton(text="🎁 Бонус", callback_data="bonus")],
        [InlineKeyboardButton(text="🎮 Игры", callback_data="games"),
         InlineKeyboardButton(text="🏆 Топ", callback_data="top")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🏦 Банк", callback_data="bank")],
        [InlineKeyboardButton(text="🧾 Чеки", callback_data="checks"),
         InlineKeyboardButton(text="💸 Перевести", callback_data="transfer")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
    ])

def games_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎡 Рулетка", callback_data="g:roulette"),
         InlineKeyboardButton(text="📈 Краш", callback_data="g:crash")],
        [InlineKeyboardButton(text="🎲 Кубик", callback_data="g:cube"),
         InlineKeyboardButton(text="🎯 Кости", callback_data="g:dice")],
        [InlineKeyboardButton(text="⚽ Футбол", callback_data="g:football"),
         InlineKeyboardButton(text="🏀 Баскет", callback_data="g:basket")],
        [InlineKeyboardButton(text="🗼 Башня", callback_data="g:tower"),
         InlineKeyboardButton(text="💎 Алмазы", callback_data="g:diamond")],
        [InlineKeyboardButton(text="💣 Мины", callback_data="g:mines"),
         InlineKeyboardButton(text="🎴 Очко", callback_data="g:blackjack")],
        [InlineKeyboardButton(text="🥇 Золото", callback_data="g:gold"),
         InlineKeyboardButton(text="🔙 Назад", callback_data="back")],
    ])

def roulette_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Красное", callback_data="rl:red"),
         InlineKeyboardButton(text="⚫ Чёрное", callback_data="rl:black")],
        [InlineKeyboardButton(text="2️⃣ Чёт", callback_data="rl:even"),
         InlineKeyboardButton(text="1️⃣ Нечёт", callback_data="rl:odd")],
        [InlineKeyboardButton(text="0️⃣ Зеро (x35)", callback_data="rl:zero")],
    ])

def crash_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1.5x", callback_data="cr:1.5"),
         InlineKeyboardButton(text="2x", callback_data="cr:2"),
         InlineKeyboardButton(text="3x", callback_data="cr:3")],
        [InlineKeyboardButton(text="5x", callback_data="cr:5"),
         InlineKeyboardButton(text="10x", callback_data="cr:10")],
    ])

def cube_kb():
    kb = []
    for i in range(1,7,3):
        kb.append([InlineKeyboardButton(text=str(j), callback_data=f"cb:{j}") for j in range(i,min(i+3,7))])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def dice_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬆️ >7 (x1.9)", callback_data="dc:more"),
         InlineKeyboardButton(text="⬇️ <7 (x1.9)", callback_data="dc:less")],
        [InlineKeyboardButton(text="7️⃣ =7 (x5)", callback_data="dc:seven")],
    ])

def football_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚽ ГОЛ (x1.85)", callback_data="fb:goal"),
         InlineKeyboardButton(text="❌ МИМО (x1.85)", callback_data="fb:miss")],
    ])

def basket_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏀 ПОПАЛ (x2.2)", callback_data="bs:hit"),
         InlineKeyboardButton(text="❌ ПРОМАХ (x2.2)", callback_data="bs:miss")],
    ])

def tower_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1️⃣", callback_data="tw:1"),
         InlineKeyboardButton(text="2️⃣", callback_data="tw:2"),
         InlineKeyboardButton(text="3️⃣", callback_data="tw:3")],
        [InlineKeyboardButton(text="💰 Забрать", callback_data="tw:cash")],
    ])

def diamond_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1️⃣", callback_data="dm:1"),
         InlineKeyboardButton(text="2️⃣", callback_data="dm:2"),
         InlineKeyboardButton(text="3️⃣", callback_data="dm:3")],
        [InlineKeyboardButton(text="4️⃣", callback_data="dm:4"),
         InlineKeyboardButton(text="5️⃣", callback_data="dm:5")],
        [InlineKeyboardButton(text="💰 Забрать", callback_data="dm:cash")],
    ])

def gold_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🥇 1", callback_data="gd:1"),
         InlineKeyboardButton(text="🥇 2", callback_data="gd:2")],
        [InlineKeyboardButton(text="💰 Забрать", callback_data="gd:cash")],
    ])

def mines_kb(game):
    kb = []
    row = []
    for i in range(1,10):
        if i in game.opened:
            row.append(InlineKeyboardButton(text="✅", callback_data="mn:noop"))
        else:
            row.append(InlineKeyboardButton(text=str(i), callback_data=f"mn:cell:{i}"))
        if len(row) == 3:
            kb.append(row); row = []
    kb.append([InlineKeyboardButton(text=f"💰 {fmt_money(game.potential())}", callback_data="mn:cash")])
    kb.append([InlineKeyboardButton(text="❌ Сдаться", callback_data="mn:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def blackjack_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Взять", callback_data="bj:hit"),
         InlineKeyboardButton(text="✋ Стоп", callback_data="bj:stand")],
    ])

def bank_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Открыть депозит", callback_data="bank:open")],
        [InlineKeyboardButton(text="📋 Мои депозиты", callback_data="bank:list")],
        [InlineKeyboardButton(text="💰 Забрать депозиты", callback_data="bank:claim")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")],
    ])

def bank_terms_kb():
    kb = []
    for days, info in BANK_TERMS.items():
        kb.append([InlineKeyboardButton(text=info["name"], callback_data=f"bank:term:{days}")])
    kb.append([InlineKeyboardButton(text="❌ Отмена", callback_data="bank:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def checks_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать чек", callback_data="ch:create")],
        [InlineKeyboardButton(text="💸 Активировать", callback_data="ch:claim")],
        [InlineKeyboardButton(text="📋 Мои чеки", callback_data="ch:my")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")],
    ])

def share_check_kb(code: str, amount: float):
    share = f"https://t.me/share/url?url=Чек {code} на {fmt_money(amount)}! Забери бонус"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Скопировать", callback_data=f"copy:{code}")],
        [InlineKeyboardButton(text="📤 Поделиться", url=share)],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="checks")],
    ])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Выдать", callback_data="adm:give"),
         InlineKeyboardButton(text="👑 Статус", callback_data="adm:status")],
        [InlineKeyboardButton(text="👥 Игроки", callback_data="adm:users"),
         InlineKeyboardButton(text="📢 Рассылка", callback_data="adm:broadcast")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats"),
         InlineKeyboardButton(text="🎟 Промо", callback_data="adm:promos")],
        [InlineKeyboardButton(text="🚫 Бан", callback_data="adm:ban"),
         InlineKeyboardButton(text="❌ Закрыть", callback_data="adm:close")],
    ])

def admin_status_kb():
    kb = []
    for st, info in STATUSES.items():
        kb.append([InlineKeyboardButton(text=f"{info['name']} (x{info['mult']})", callback_data=f"set_st:{st}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="adm:back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def play_again_kb(game: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Ещё раз", callback_data=f"again:{game}")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="games")],
    ])# ==================== ДИСПЕТЧЕР ====================
dp = Dispatcher(storage=MemoryStorage())

# ==================== ОСНОВНЫЕ ТЕКСТОВЫЕ КОМАНДЫ ====================
@dp.message(CommandStart())
async def cmd_start(m: Message):
    u = get_user(m.from_user.id, m.from_user.full_name)
    st = STATUSES[u["status"]]
    await m.answer(
        f"🎮 Добро пожаловать в ONEmi Game Bot!\n\n"
        f"{st['emoji']} {st['name']}\n"
        f"💰 Баланс: {fmt_money(u['balance'])}\n\n"
        f"📋 Основные команды:\n"
        f"• <code>б</code> или <code>баланс</code>\n"
        f"• <code>бонус</code>\n"
        f"• <code>игры</code>\n"
        f"• <code>топ</code>\n"
        f"• <code>профиль</code>\n"
        f"• <code>банк</code>\n"
        f"• <code>чеки</code>\n"
        f"• <code>промо КОД</code>\n"
        f"• <code>помощь</code>\n\n"
        f"👇 Используй кнопки ниже",
        reply_markup=main_kb()
    )

@dp.message(Command("admin"))
async def cmd_admin(m: Message):
    if is_admin(m.from_user.id):
        await m.answer("👑 Админ-панель", reply_markup=admin_kb())
    else:
        await m.answer("⛔ Нет доступа")

@dp.message(lambda m: m.text and m.text.lower() in ["б", "баланс"])
async def balance_txt(m: Message):
    u = get_user(m.from_user.id)
    await m.answer(f"💰 Баланс: {fmt_money(u['balance'])}")

@dp.message(lambda m: m.text and m.text.lower() in ["бонус"])
async def bonus_txt(m: Message):
    ok, rem, reward, streak = claim_bonus(m.from_user.id)
    if not ok:
        await m.answer(f"🎁 Бонус через {rem//3600}ч {(rem%3600)//60}мин")
    else:
        await m.answer(f"🎁 +{fmt_money(reward)}\n🔥 Стрик: {streak}\n💰 {fmt_money(get_user(m.from_user.id)['balance'])}")

@dp.message(lambda m: m.text and m.text.lower() in ["игры"])
async def games_txt(m: Message):
    await m.answer("🎮 Список игр:\n"
                   "• краш 100к 4\n"
                   "• кубик 10к 5\n"
                   "• кости 50к м|б|равно\n"
                   "• футбол 100к гол|мимо\n"
                   "• баскет 100к попал|промах\n"
                   "• рулетка, башня, алмазы, мины, очко, золото — через меню",
                   reply_markup=games_kb())

@dp.message(lambda m: m.text and m.text.lower() in ["топ"])
async def top_txt(m: Message):
    top = get_top_users(10)
    if not top:
        await m.answer("🏆 Топ пуст")
        return
    medals = ["🥇","🥈","🥉"]
    text = "🏆 Топ ONEmi\n\n"
    for i, u in enumerate(top,1):
        medal = medals[i-1] if i<=3 else f"{i}."
        st_emoji = STATUSES[u["status"]]["emoji"]
        text += f"{medal} {st_emoji} {u['name']} — {fmt_money(u['balance'])}\n"
    await m.answer(text)

@dp.message(lambda m: m.text and m.text.lower() in ["профиль"])
async def profile_txt(m: Message):
    u = get_user(m.from_user.id)
    st = STATUSES[u["status"]]
    wr = (u["total_wins"] / u["total_bets"] * 100) if u["total_bets"] else 0
    await m.answer(
        f"👤 {u['name']}\n"
        f"🎭 {st['name']} (x{st['mult']})\n"
        f"💰 {fmt_money(u['balance'])}\n"
        f"🎲 Ставок: {u['total_bets']} | Побед: {u['total_wins']} ({wr:.1f}%)\n"
        f"🏆 Выиграно: {fmt_money(u['total_win'])}"
    )

@dp.message(lambda m: m.text and m.text.lower() in ["банк"])
async def bank_txt(m: Message):
    await m.answer("🏦 Банк ONEmi\nДепозиты на 7/14/30 дней", reply_markup=bank_kb())

@dp.message(lambda m: m.text and m.text.lower() in ["чеки"])
async def checks_txt(m: Message):
    await m.answer("🧾 Чеки", reply_markup=checks_kb())

@dp.message(lambda m: m.text and m.text.lower().startswith("промо"))
async def promo_txt(m: Message, state: FSMContext):
    parts = m.text.split(maxsplit=1)
    if len(parts) == 2:
        ok, msg, _ = claim_promo(m.from_user.id, parts[1])
        await m.answer(msg)
    else:
        await state.set_state(PromoRedeem.code)
        await m.answer("🎟 Введите код промокода:")

@dp.message(PromoRedeem.code)
async def promo_code(m: Message, state: FSMContext):
    ok, msg, _ = claim_promo(m.from_user.id, m.text.strip())
    await m.answer(msg)
    await state.clear()

@dp.message(lambda m: m.text and m.text.lower() in ["помощь"])
async def help_txt(m: Message):
    await m.answer(
        "❓ <b>Помощь по боту ONEmi</b>\n\n"
        "<b>📋 Основные команды:</b>\n"
        "• <code>б</code> или <code>баланс</code> - Проверить баланс\n"
        "• <code>бонус</code> - Получить ежедневный бонус\n"
        "• <code>игры</code> - Список всех игр\n"
        "• <code>топ</code> - Топ игроков по балансу\n"
        "• <code>профиль</code> - Твоя статистика\n"
        "• <code>банк</code> - Управление депозитами\n"
        "• <code>чеки</code> - Создать/активировать чек\n"
        "• <code>промо КОД</code> - Активировать промокод\n"
        "• <code>помощь</code> - Это сообщение\n\n"
        "<b>🎮 Игры:</b>\n"
        "• 🗼 Башня - выбери безопасный этаж\n"
        "• 🥇 Золото - найди золото среди ловушек\n"
        "• 💎 Алмазы - собери все алмазы\n"
        "• 💣 Мины - открывай безопасные клетки\n"
        "• 🎴 Очко - играй против дилера\n"
        "• 🎡 Рулетка - угадай цвет/число\n"
        "• 📈 Краш - угадай множитель\n"
        "• 🎲 Кубик - угадай число\n"
        "• 🎯 Кости - угадай сумму двух кубиков\n"
        "• ⚽ Футбол - удар по воротам\n"
        "• 🏀 Баскет - бросок в кольцо\n\n"
        "<b>📝 Примеры команд:</b>\n"
        "<code>краш 300 2.5</code>\n"
        "<code>кубик 300 5</code>\n"
        "<code>кости 300 м</code>\n"
        "<code>футбол 300 гол</code>\n"
        "<code>баскет 300 попал</code>\n\n"
        "<b>💰 Статусы и множители:</b>\n"
        "• 🟢 Обычный - x1.0 к выигрышам\n"
        "• 🟡 Продвинутый - x1.05\n"
        "• 🔴 VIP - x1.10\n"
        "• 🟣 Премиум - x1.15\n"
        "• 👑 Легенда - x1.25\n\n"
        "Отмена действия: <code>отмена</code>",
        parse_mode="HTML"
    )

@dp.message(lambda m: m.text and m.text.lower() in ["отмена", "/cancel"])
async def cancel_cmd(m: Message, state: FSMContext):
    await state.clear()
    active_tower.pop(m.from_user.id, None)
    active_diamond.pop(m.from_user.id, None)
    active_gold.pop(m.from_user.id, None)
    active_mines.pop(m.from_user.id, None)
    active_blackjack.pop(m.from_user.id, None)
    await m.answer("🛑 Действие отменено")

# ==================== ТЕКСТОВЫЕ КОМАНДЫ ДЛЯ ИГР ====================
@dp.message(lambda m: m.text and m.text.lower().startswith("краш "))
async def crash_text_cmd(m: Message):
    if is_banned(m.from_user.id):
        await m.answer("🚫 Вы забанены")
        return
    parts = m.text.lower().split()
    if len(parts) != 3:
        await m.answer("❌ краш 100к 4")
        return
    try:
        bet = parse_amount(parts[1])
        target = float(parts[2])
    except:
        await m.answer("❌ Неверный формат")
        return
    if bet < MIN_BET or bet > MAX_BET:
        await m.answer(f"❌ Ставка от {fmt_money(MIN_BET)} до {fmt_money(MAX_BET)}")
        return
    u = get_user(m.from_user.id)
    if u["balance"] < bet:
        await m.answer("❌ Недостаточно средств")
        return
    update_balance(m.from_user.id, -bet)
    point = crash_roll()
    if target <= point:
        win_amount = round(bet * target * get_multiplier(m.from_user.id), 2)
        update_balance(m.from_user.id, win_amount)
        add_bet(m.from_user.id, "crash", bet, win_amount, target)
        await m.answer(f"📈 Краш x{point}\n✅ +{fmt_money(win_amount)}")
    else:
        add_bet(m.from_user.id, "crash", bet, 0, 0)
        await m.answer(f"📈 Краш x{point}\n❌ -{fmt_money(bet)}")
    await m.answer(f"💰 {fmt_money(get_user(m.from_user.id)['balance'])}")

@dp.message(lambda m: m.text and m.text.lower().startswith("кубик "))
async def cube_text_cmd(m: Message):
    if is_banned(m.from_user.id):
        await m.answer("🚫 Вы забанены")
        return
    parts = m.text.lower().split()
    if len(parts) != 3:
        await m.answer("❌ кубик 10к 5")
        return
    try:
        bet = parse_amount(parts[1])
        guess = int(parts[2])
    except:
        await m.answer("❌ Неверный формат")
        return
    if guess < 1 or guess > 6:
        await m.answer("❌ Число от 1 до 6")
        return
    if bet < MIN_BET or bet > MAX_BET:
        await m.answer(f"❌ Ставка от {fmt_money(MIN_BET)} до {fmt_money(MAX_BET)}")
        return
    u = get_user(m.from_user.id)
    if u["balance"] < bet:
        await m.answer("❌ Недостаточно средств")
        return
    update_balance(m.from_user.id, -bet)
    res = roll_dice()
    if guess == res:
        win_amount = round(bet * 5.8 * get_multiplier(m.from_user.id), 2)
        update_balance(m.from_user.id, win_amount)
        add_bet(m.from_user.id, "cube", bet, win_amount, 5.8)
        await m.answer(f"🎲 Выпало {res}\n✅ +{fmt_money(win_amount)}")
    else:
        add_bet(m.from_user.id, "cube", bet, 0, 0)
        await m.answer(f"🎲 Выпало {res}\n❌ -{fmt_money(bet)}")
    await m.answer(f"💰 {fmt_money(get_user(m.from_user.id)['balance'])}")

@dp.message(lambda m: m.text and m.text.lower().startswith("кости "))
async def dice_text_cmd(m: Message):
    if is_banned(m.from_user.id):
        await m.answer("🚫 Вы забанены")
        return
    parts = m.text.lower().split()
    if len(parts) != 3:
        await m.answer("❌ кости 50к м|б|равно")
        return
    try:
        bet = parse_amount(parts[1])
    except:
        await m.answer("❌ Неверная сумма")
        return
    choix = parts[2]
    if choix not in ["м","б","равно"]:
        await m.answer("❌ м / б / равно")
        return
    if bet < MIN_BET or bet > MAX_BET:
        await m.answer(f"❌ Ставка от {fmt_money(MIN_BET)} до {fmt_money(MAX_BET)}")
        return
    u = get_user(m.from_user.id)
    if u["balance"] < bet:
        await m.answer("❌ Недостаточно средств")
        return
    update_balance(m.from_user.id, -bet)
    total = two_dice()
    win = (choix == "м" and total < 7) or (choix == "б" and total > 7) or (choix == "равно" and total == 7)
    mult = 1.9 if win and total != 7 else 5.0 if win and total == 7 else 0
    if win:
        win_amount = round(bet * mult * get_multiplier(m.from_user.id), 2)
        update_balance(m.from_user.id, win_amount)
        add_bet(m.from_user.id, "dice", bet, win_amount, mult)
        await m.answer(f"🎯 Сумма {total}\n✅ +{fmt_money(win_amount)}")
    else:
        add_bet(m.from_user.id, "dice", bet, 0, 0)
        await m.answer(f"🎯 Сумма {total}\n❌ -{fmt_money(bet)}")
    await m.answer(f"💰 {fmt_money(get_user(m.from_user.id)['balance'])}")

@dp.message(lambda m: m.text and m.text.lower().startswith("футбол "))
async def football_text_cmd(m: Message):
    if is_banned(m.from_user.id):
        await m.answer("🚫 Вы забанены")
        return
    parts = m.text.lower().split()
    if len(parts) != 3:
        await m.answer("❌ футбол 100к гол|мимо")
        return
    try:
        bet = parse_amount(parts[1])
    except:
        await m.answer("❌ Неверная сумма")
        return
    choix = parts[2]
    if choix not in ["гол","мимо"]:
        await m.answer("❌ гол / мимо")
        return
    if bet < MIN_BET or bet > MAX_BET:
        await m.answer(f"❌ Ставка от {fmt_money(MIN_BET)} до {fmt_money(MAX_BET)}")
        return
    u = get_user(m.from_user.id)
    if u["balance"] < bet:
        await m.answer("❌ Недостаточно средств")
        return
    update_balance(m.from_user.id, -bet)
    res, _ = football_kick()
    win = (choix == "гол" and res == "ГОЛ") or (choix == "мимо" and res == "МИМО")
    if win:
        win_amount = round(bet * 1.85 * get_multiplier(m.from_user.id), 2)
        update_balance(m.from_user.id, win_amount)
        add_bet(m.from_user.id, "football", bet, win_amount, 1.85)
        await m.answer(f"⚽ {res}\n✅ +{fmt_money(win_amount)}")
    else:
        add_bet(m.from_user.id, "football", bet, 0, 0)
        await m.answer(f"⚽ {res}\n❌ -{fmt_money(bet)}")
    await m.answer(f"💰 {fmt_money(get_user(m.from_user.id)['balance'])}")

@dp.message(lambda m: m.text and m.text.lower().startswith("баскет"))
async def basket_text_cmd(m: Message):
    if is_banned(m.from_user.id):
        await m.answer("🚫 Вы забанены")
        return
    parts = m.text.lower().split()
    if len(parts) != 3:
        await m.answer("❌ баскет 100к попал|промах")
        return
    try:
        bet = parse_amount(parts[1])
    except:
        await m.answer("❌ Неверная сумма")
        return
    choix = parts[2]
    if choix not in ["попал","промах"]:
        await m.answer("❌ попал / промах")
        return
    if bet < MIN_BET or bet > MAX_BET:
        await m.answer(f"❌ Ставка от {fmt_money(MIN_BET)} до {fmt_money(MAX_BET)}")
        return
    u = get_user(m.from_user.id)
    if u["balance"] < bet:
        await m.answer("❌ Недостаточно средств")
        return
    update_balance(m.from_user.id, -bet)
    res, _ = basketball_shot()
    win = (choix == "попал" and res == "ПОПАЛ") or (choix == "промах" and res == "ПРОМАХ")
    if win:
        win_amount = round(bet * 2.2 * get_multiplier(m.from_user.id), 2)
        update_balance(m.from_user.id, win_amount)
        add_bet(m.from_user.id, "basketball", bet, win_amount, 2.2)
        await m.answer(f"🏀 {res}\n✅ +{fmt_money(win_amount)}")
    else:
        add_bet(m.from_user.id, "basketball", bet, 0, 0)
        await m.answer(f"🏀 {res}\n❌ -{fmt_money(bet)}")
    await m.answer(f"💰 {fmt_money(get_user(m.from_user.id)['balance'])}")

# ==================== MENU CALLBACKS ====================
@dp.callback_query(F.data == "bal")
async def cb_bal(c: CallbackQuery):
    u = get_user(c.from_user.id)
    await c.message.answer(f"💰 Баланс: {fmt_money(u['balance'])}")
    await c.answer()

@dp.callback_query(F.data == "bonus")
async def cb_bonus(c: CallbackQuery):
    ok, rem, reward, streak = claim_bonus(c.from_user.id)
    if not ok:
        await c.message.answer(f"🎁 Бонус через {rem//3600}ч {(rem%3600)//60}мин")
    else:
        await c.message.answer(f"🎁 +{fmt_money(reward)}\n🔥 Стрик: {streak}\n💰 {fmt_money(get_user(c.from_user.id)['balance'])}")
    await c.answer()

@dp.callback_query(F.data == "games")
async def cb_games(c: CallbackQuery):
    await c.message.edit_text("🎮 Выбери игру:", reply_markup=games_kb())
    await c.answer()

@dp.callback_query(F.data == "top")
async def cb_top(c: CallbackQuery):
    top = get_top_users(10)
    if not top:
        await c.message.answer("🏆 Топ пуст")
    else:
        medals = ["🥇","🥈","🥉"]
        text = "🏆 Топ ONEmi\n\n"
        for i, u in enumerate(top,1):
            medal = medals[i-1] if i<=3 else f"{i}."
            st_emoji = STATUSES[u["status"]]["emoji"]
            text += f"{medal} {st_emoji} {u['name']} — {fmt_money(u['balance'])}\n"
        await c.message.answer(text)
    await c.answer()

@dp.callback_query(F.data == "profile")
async def cb_profile(c: CallbackQuery):
    u = get_user(c.from_user.id)
    st = STATUSES[u["status"]]
    wr = (u["total_wins"] / u["total_bets"] * 100) if u["total_bets"] else 0
    await c.message.answer(
        f"👤 {u['name']}\n"
        f"🎭 {st['name']} (x{st['mult']})\n"
        f"💰 {fmt_money(u['balance'])}\n"
        f"🎲 Ставок: {u['total_bets']} | Побед: {u['total_wins']} ({wr:.1f}%)\n"
        f"🏆 Выиграно: {fmt_money(u['total_win'])}"
    )
    await c.answer()

@dp.callback_query(F.data == "bank")
async def cb_bank(c: CallbackQuery):
    await c.message.edit_text("🏦 Банк ONEmi", reply_markup=bank_kb())
    await c.answer()

@dp.callback_query(F.data == "checks")
async def cb_checks(c: CallbackQuery):
    await c.message.edit_text("🧾 Чеки", reply_markup=checks_kb())
    await c.answer()

@dp.callback_query(F.data == "transfer")
async def cb_transfer(c: CallbackQuery, state: FSMContext):
    await state.set_state(TransferState.target)
    await c.message.answer("💸 Введите ID или @username получателя:")
    await c.answer()

@dp.message(TransferState.target)
async def transfer_target(m: Message, state: FSMContext):
    text = m.text.strip()
    target_id = None
    if text.startswith("@"):
        name = text[1:]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE name = ?", (name,))
        row = c.fetchone()
        conn.close()
        if not row:
            await m.answer("❌ Пользователь не найден")
            return
        target_id = int(row[0])
    else:
        try:
            target_id = int(text)
        except:
            await m.answer("❌ Неверный формат")
            return
    await state.update_data(target=target_id)
    await state.set_state(TransferState.amount)
    await m.answer(f"Введите сумму (макс {fmt_money(TRANSFER_MAX)}):")

@dp.message(TransferState.amount)
async def transfer_amount(m: Message, state: FSMContext):
    try:
        amount = parse_amount(m.text)
    except:
        await m.answer("❌ Неверная сумма")
        return
    if amount <= 0 or amount > TRANSFER_MAX:
        await m.answer(f"❌ Сумма от 1 до {fmt_money(TRANSFER_MAX)}")
        return
    data = await state.get_data()
    target = data["target"]
    ok, msg = transfer_coins(m.from_user.id, target, amount)
    await m.answer(msg)
    await state.clear()

@dp.callback_query(F.data == "help")
async def cb_help(c: CallbackQuery):
    await help_txt(c.message)
    await c.answer()

@dp.callback_query(F.data == "back")
async def cb_back(c: CallbackQuery):
    await c.message.edit_text("🎮 Главное меню", reply_markup=main_kb())
    await c.answer()

# ==================== ИГРЫ (кнопки) ====================
@dp.callback_query(F.data == "g:roulette")
async def roulette_start(c: CallbackQuery, state: FSMContext):
    if is_banned(c.from_user.id):
        await c.answer("🚫 Вы забанены", show_alert=True)
        return
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="roulette")
    await c.message.answer("🎡 Рулетка\nВведи ставку:")
    await c.answer()

@dp.message(GameStates.waiting_bet)
async def game_bet(m: Message, state: FSMContext):
    if is_banned(m.from_user.id):
        await m.answer("🚫 Вы забанены")
        await state.clear()
        return
    try:
        bet = parse_amount(m.text)
        if bet < MIN_BET or bet > MAX_BET:
            await m.answer(f"❌ Ставка от {fmt_money(MIN_BET)} до {fmt_money(MAX_BET)}")
            return
    except:
        await m.answer("❌ Неверная сумма")
        return
    u = get_user(m.from_user.id)
    if u["balance"] < bet:
        await m.answer("❌ Недостаточно средств")
        return
    await state.update_data(bet=bet)
    data = await state.get_data()
    game = data.get("game")
    if game == "roulette":
        await m.answer(f"💰 {fmt_money(bet)}\nВыбери ставку:", reply_markup=roulette_kb())
    elif game == "crash":
        await state.set_state(GameStates.waiting_crash_target)
        await m.answer(f"💰 {fmt_money(bet)}\nВыбери множитель:", reply_markup=crash_kb())
    elif game == "cube":
        await m.answer(f"💰 {fmt_money(bet)}\nУгадай число:", reply_markup=cube_kb())
    elif game == "dice":
        await m.answer(f"💰 {fmt_money(bet)}\nВыбери условие:", reply_markup=dice_kb())
    elif game == "football":
        await m.answer(f"💰 {fmt_money(bet)}\nВыбери исход:", reply_markup=football_kb())
    elif game == "basket":
        await m.answer(f"💰 {fmt_money(bet)}\nВыбери исход:", reply_markup=basket_kb())
    elif game == "tower":
        await state.clear()
        update_balance(m.from_user.id, -bet)
        active_tower[m.from_user.id] = {"bet": bet, "level": 0}
        await m.answer(f"🗼 Башня | {fmt_money(bet)}\nУровень 1 → x{TOWER_MULT[0]}\nВыбери секцию:", reply_markup=tower_kb())
    elif game == "diamond":
        await state.clear()
        update_balance(m.from_user.id, -bet)
        active_diamond[m.from_user.id] = {"bet": bet, "level": 0}
        await m.answer(f"💎 Алмазы | {fmt_money(bet)}\nВыбери ячейку:", reply_markup=diamond_kb())
    elif game == "gold":
        await state.clear()
        update_balance(m.from_user.id, -bet)
        active_gold[m.from_user.id] = {"bet": bet, "level": 0}
        await m.answer(f"🥇 Золото | {fmt_money(bet)}\nВыбери ячейку 1 или 2:", reply_markup=gold_kb())
    elif game == "mines":
        await state.update_data(bet=bet)
        await state.set_state(GameStates.waiting_mines_count)
        await m.answer(f"💰 {fmt_money(bet)}\nСколько мин? (1-5):")

@dp.callback_query(F.data.startswith("rl:"))
async def roulette_play(c: CallbackQuery, state: FSMContext):
    choice = c.data.split(":")[1]
    data = await state.get_data()
    bet = data["bet"]
    uid = c.from_user.id
    update_balance(uid, -bet)
    win, mult, num, col = roulette_spin(choice)
    if win:
        win_amount = round(bet * mult * get_multiplier(uid), 2)
        update_balance(uid, win_amount)
        add_bet(uid, "roulette", bet, win_amount, mult)
        text = f"🎡 {num} {col}\n✅ +{fmt_money(win_amount)}"
    else:
        add_bet(uid, "roulette", bet, 0, 0)
        text = f"🎡 {num} {col}\n❌ -{fmt_money(bet)}"
    text += f"\n💰 {fmt_money(get_user(uid)['balance'])}"
    await c.message.answer(text, reply_markup=play_again_kb("roulette"))
    await state.clear()
    await c.answer()

@dp.callback_query(F.data == "g:crash")
async def crash_menu(c: CallbackQuery, state: FSMContext):
    if is_banned(c.from_user.id):
        await c.answer("🚫 Вы забанены", show_alert=True)
        return
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="crash")
    await c.message.answer("📈 Краш\nВведи ставку:")
    await c.answer()

@dp.callback_query(GameStates.waiting_crash_target, F.data.startswith("cr:"))
async def crash_play(c: CallbackQuery, state: FSMContext):
    target = float(c.data.split(":")[1])
    data = await state.get_data()
    bet = data["bet"]
    uid = c.from_user.id
    update_balance(uid, -bet)
    point = crash_roll()
    if target <= point:
        win_amount = round(bet * target * get_multiplier(uid), 2)
        update_balance(uid, win_amount)
        add_bet(uid, "crash", bet, win_amount, target)
        text = f"📈 Краш x{point}\n✅ +{fmt_money(win_amount)}"
    else:
        add_bet(uid, "crash", bet, 0, 0)
        text = f"📈 Краш x{point}\n❌ -{fmt_money(bet)}"
    text += f"\n💰 {fmt_money(get_user(uid)['balance'])}"
    await c.message.answer(text, reply_markup=play_again_kb("crash"))
    await state.clear()
    await c.answer()

@dp.callback_query(F.data == "g:cube")
async def cube_menu(c: CallbackQuery, state: FSMContext):
    if is_banned(c.from_user.id):
        await c.answer("🚫 Вы забанены", show_alert=True)
        return
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="cube")
    await c.message.answer("🎲 Кубик\nВведи ставку:")
    await c.answer()

@dp.callback_query(F.data.startswith("cb:"))
async def cube_play(c: CallbackQuery, state: FSMContext):
    guess = int(c.data.split(":")[1])
    data = await state.get_data()
    bet = data["bet"]
    uid = c.from_user.id
    update_balance(uid, -bet)
    res = roll_dice()
    if guess == res:
        win_amount = round(bet * 5.8 * get_multiplier(uid), 2)
        update_balance(uid, win_amount)
        add_bet(uid, "cube", bet, win_amount, 5.8)
        text = f"🎲 {res}\n✅ +{fmt_money(win_amount)}"
    else:
        add_bet(uid, "cube", bet, 0, 0)
        text = f"🎲 {res}\n❌ -{fmt_money(bet)}"
    text += f"\n💰 {fmt_money(get_user(uid)['balance'])}"
    await c.message.answer(text, reply_markup=play_again_kb("cube"))
    await state.clear()
    await c.answer()

@dp.callback_query(F.data == "g:dice")
async def dice_menu(c: CallbackQuery, state: FSMContext):
    if is_banned(c.from_user.id):
        await c.answer("🚫 Вы забанены", show_alert=True)
        return
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="dice")
    await c.message.answer("🎯 Кости\nВведи ставку:")
    await c.answer()

@dp.callback_query(F.data.startswith("dc:"))
async def dice_play(c: CallbackQuery, state: FSMContext):
    choice = c.data.split(":")[1]
    data = await state.get_data()
    bet = data["bet"]
    uid = c.from_user.id
    update_balance(uid, -bet)
    total = two_dice()
    win = (choice == "more" and total > 7) or (choice == "less" and total < 7) or (choice == "seven" and total == 7)
    mult = 1.9 if win and total != 7 else 5.0 if win and total == 7 else 0
    if win:
        win_amount = round(bet * mult * get_multiplier(uid), 2)
        update_balance(uid, win_amount)
        add_bet(uid, "dice", bet, win_amount, mult)
        text = f"🎯 {total}\n✅ +{fmt_money(win_amount)}"
    else:
        add_bet(uid, "dice", bet, 0, 0)
        text = f"🎯 {total}\n❌ -{fmt_money(bet)}"
    text += f"\n💰 {fmt_money(get_user(uid)['balance'])}"
    await c.message.answer(text, reply_markup=play_again_kb("dice"))
    await state.clear()
    await c.answer()

@dp.callback_query(F.data == "g:football")
async def football_menu(c: CallbackQuery, state: FSMContext):
    if is_banned(c.from_user.id):
        await c.answer("🚫 Вы забанены", show_alert=True)
        return
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="football")
    await c.message.answer("⚽ Футбол\nВведи ставку:")
    await c.answer()

@dp.callback_query(F.data.startswith("fb:"))
async def football_play(c: CallbackQuery, state: FSMContext):
    choice = c.data.split(":")[1]
    data = await state.get_data()
    bet = data["bet"]
    uid = c.from_user.id
    update_balance(uid, -bet)
    res, _ = football_kick()
    win = (choice == "goal" and res == "ГОЛ") or (choice == "miss" and res == "МИМО")
    if win:
        win_amount = round(bet * 1.85 * get_multiplier(uid), 2)
        update_balance(uid, win_amount)
        add_bet(uid, "football", bet, win_amount, 1.85)
        text = f"⚽ {res}\n✅ +{fmt_money(win_amount)}"
    else:
        add_bet(uid, "football", bet, 0, 0)
        text = f"⚽ {res}\n❌ -{fmt_money(bet)}"
    text += f"\n💰 {fmt_money(get_user(uid)['balance'])}"
    await c.message.answer(text, reply_markup=play_again_kb("football"))
    await state.clear()
    await c.answer()

@dp.callback_query(F.data == "g:basket")
async def basket_menu(c: CallbackQuery, state: FSMContext):
    if is_banned(c.from_user.id):
        await c.answer("🚫 Вы забанены", show_alert=True)
        return
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="basket")
    await c.message.answer("🏀 Баскетбол\nВведи ставку:")
    await c.answer()

@dp.callback_query(F.data.startswith("bs:"))
async def basket_play(c: CallbackQuery, state: FSMContext):
    choice = c.data.split(":")[1]
    data = await state.get_data()
    bet = data["bet"]
    uid = c.from_user.id
    update_balance(uid, -bet)
    res, _ = basketball_shot()
    win = (choice == "hit" and res == "ПОПАЛ") or (choice == "miss" and res == "ПРОМАХ")
    if win:
        win_amount = round(bet * 2.2 * get_multiplier(uid), 2)
        update_balance(uid, win_amount)
        add_bet(uid, "basketball", bet, win_amount, 2.2)
        text = f"🏀 {res}\n✅ +{fmt_money(win_amount)}"
    else:
        add_bet(uid, "basketball", bet, 0, 0)
        text = f"🏀 {res}\n❌ -{fmt_money(bet)}"
    text += f"\n💰 {fmt_money(get_user(uid)['balance'])}"
    await c.message.answer(text, reply_markup=play_again_kb("basket"))
    await state.clear()
    await c.answer()

@dp.callback_query(F.data == "g:tower")
async def tower_start(c: CallbackQuery, state: FSMContext):
    if is_banned(c.from_user.id):
        await c.answer("🚫 Вы забанены", show_alert=True)
        return
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="tower")
    await c.message.answer("🗼 Башня\nВведи ставку:")
    await c.answer()

@dp.callback_query(F.data.startswith("tw:"))
async def tower_play(c: CallbackQuery):
    act = c.data.split(":")[1]
    uid = c.from_user.id
    game = active_tower.get(uid)
    if not game:
        await c.answer("Нет активной игры")
        return
    if act == "cash":
        if game["level"] == 0:
            win_amount = game["bet"]
        else:
            win_amount = round(game["bet"] * TOWER_MULT[game["level"]-1] * get_multiplier(uid), 2)
        update_balance(uid, win_amount)
        add_bet(uid, "tower", game["bet"], win_amount, TOWER_MULT[game["level"]-1] if game["level"]>0 else 1)
        del active_tower[uid]
        await c.message.answer(f"🗼 Выигрыш {fmt_money(win_amount)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("tower"))
    elif act in ["1","2","3"]:
        choice = int(act)
        safe = random.randint(1,3)
        if choice == safe:
            game["level"] += 1
            if game["level"] >= len(TOWER_MULT):
                win_amount = round(game["bet"] * TOWER_MULT[-1] * get_multiplier(uid), 2)
                update_balance(uid, win_amount)
                add_bet(uid, "tower", game["bet"], win_amount, TOWER_MULT[-1])
                del active_tower[uid]
                await c.message.answer(f"🗼 ПОЛНЫЙ ПРОХОД! {fmt_money(win_amount)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("tower"))
            else:
                next_mult = TOWER_MULT[game["level"]] if game["level"] < len(TOWER_MULT) else TOWER_MULT[-1]
                await c.message.edit_text(
                    f"🗼 Уровень {game['level']} пройден!\n"
                    f"Множитель x{TOWER_MULT[game['level']-1]}\n"
                    f"Следующий x{next_mult}\n"
                    f"Потенциал {fmt_money(game['bet'] * TOWER_MULT[game['level']-1])}\n\n"
                    f"Выбери дальше:",
                    reply_markup=tower_kb()
                )
        else:
            add_bet(uid, "tower", game["bet"], 0, 0)
            del active_tower[uid]
            await c.message.answer(f"🗼 Ловушка! Проигрыш {fmt_money(game['bet'])}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("tower"))
    await c.answer()

@dp.callback_query(F.data == "g:diamond")
async def diamond_start(c: CallbackQuery, state: FSMContext):
    if is_banned(c.from_user.id):
        await c.answer("🚫 Вы забанены", show_alert=True)
        return
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="diamond")
    await c.message.answer("💎 Алмазы\nВведи ставку:")
    await c.answer()

@dp.callback_query(F.data.startswith("dm:"))
async def diamond_play(c: CallbackQuery):
    act = c.data.split(":")[1]
    uid = c.from_user.id
    game = active_diamond.get(uid)
    if not game:
        await c.answer("Нет активной игры")
        return
    if act == "cash":
        if game["level"] == 0:
            win_amount = game["bet"]
        else:
            win_amount = round(game["bet"] * DIAMOND_MULT[game["level"]-1] * get_multiplier(uid), 2)
        update_balance(uid, win_amount)
        add_bet(uid, "diamond", game["bet"], win_amount, DIAMOND_MULT[game["level"]-1] if game["level"]>0 else 1)
        del active_diamond[uid]
        await c.message.answer(f"💎 Выигрыш {fmt_money(win_amount)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("diamond"))
    elif act in ["1","2","3","4","5"]:
        choice = int(act)
        safe = random.randint(1,5)
        if choice == safe:
            game["level"] += 1
            if game["level"] >= len(DIAMOND_MULT):
                win_amount = round(game["bet"] * DIAMOND_MULT[-1] * get_multiplier(uid), 2)
                update_balance(uid, win_amount)
                add_bet(uid, "diamond", game["bet"], win_amount, DIAMOND_MULT[-1])
                del active_diamond[uid]
                await c.message.answer(f"💎 ПОЛНЫЙ ПРОХОД! {fmt_money(win_amount)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("diamond"))
            else:
                await c.message.edit_text(f"💎 Уровень {game['level']} пройден! x{DIAMOND_MULT[game['level']-1]}\nВыбери дальше:", reply_markup=diamond_kb())
        else:
            add_bet(uid, "diamond", game["bet"], 0, 0)
            del active_diamond[uid]
            await c.message.answer(f"💎 Бракованный алмаз! Проигрыш {fmt_money(game['bet'])}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("diamond"))
    await c.answer()

@dp.callback_query(F.data == "g:gold")
async def gold_start(c: CallbackQuery, state: FSMContext):
    if is_banned(c.from_user.id):
        await c.answer("🚫 Вы забанены", show_alert=True)
        return
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="gold")
    await c.message.answer("🥇 Золото\nВведи ставку:")
    await c.answer()

@dp.callback_query(F.data.startswith("gd:"))
async def gold_play(c: CallbackQuery):
    act = c.data.split(":")[1]
    uid = c.from_user.id
    game = active_gold.get(uid)
    if not game:
        await c.answer("Нет активной игры")
        return
    if act == "cash":
        if game["level"] == 0:
            win_amount = game["bet"]
        else:
            win_amount = round(game["bet"] * GOLD_MULT[game["level"]-1] * get_multiplier(uid), 2)
        update_balance(uid, win_amount)
        add_bet(uid, "gold", game["bet"], win_amount, GOLD_MULT[game["level"]-1] if game["level"]>0 else 1)
        del active_gold[uid]
        await c.message.answer(f"🥇 Выигрыш {fmt_money(win_amount)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("gold"))
    elif act in ["1","2"]:
        choice = int(act)
        safe = random.randint(1,2)
        if choice == safe:
            game["level"] += 1
            if game["level"] >= len(GOLD_MULT):
                win_amount = round(game["bet"] * GOLD_MULT[-1] * get_multiplier(uid), 2)
                update_balance(uid, win_amount)
                add_bet(uid, "gold", game["bet"], win_amount, GOLD_MULT[-1])
                del active_gold[uid]
                await c.message.answer(f"🥇 ПОЛНЫЙ ПРОХОД! {fmt_money(win_amount)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("gold"))
            else:
                await c.message.edit_text(f"🥇 Уровень {game['level']} пройден! x{GOLD_MULT[game['level']-1]}\nВыбери дальше:", reply_markup=gold_kb())
        else:
            add_bet(uid, "gold", game["bet"], 0, 0)
            del active_gold[uid]
            await c.message.answer(f"🥇 Ловушка! Проигрыш {fmt_money(game['bet'])}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("gold"))
    await c.answer()

@dp.callback_query(F.data == "g:mines")
async def mines_start(c: CallbackQuery, state: FSMContext):
    if is_banned(c.from_user.id):
        await c.answer("🚫 Вы забанены", show_alert=True)
        return
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="mines")
    await c.message.answer("💣 Мины 3x3\nВведи ставку:")
    await c.answer()

@dp.message(GameStates.waiting_mines_count)
async def mines_count(m: Message, state: FSMContext):
    try:
        mines = int(m.text)
        if mines < 1 or mines > 5:
            await m.answer("❌ 1-5")
            return
    except:
        await m.answer("❌ Число")
        return
    data = await state.get_data()
    bet = data["bet"]
    uid = m.from_user.id
    update_balance(uid, -bet)
    game = MinesGame(bet, mines)
    active_mines[uid] = game
    await state.clear()
    await m.answer(f"💣 {fmt_money(bet)} | мин: {mines}\nОткрывай клетки:", reply_markup=mines_kb(game))

@dp.callback_query(F.data.startswith("mn:"))
async def mines_action(c: CallbackQuery):
    act = c.data.split(":")[1]
    uid = c.from_user.id
    game = active_mines.get(uid)
    if not game:
        await c.answer("Нет активной игры")
        return
    if act == "cash":
        if len(game.opened) == 0:
            await c.answer("Сначала открой клетку")
            return
        win_amount = round(game.bet * game.get_mult() * get_multiplier(uid), 2)
        update_balance(uid, win_amount)
        add_bet(uid, "mines", game.bet, win_amount, game.get_mult())
        del active_mines[uid]
        await c.message.answer(f"💣 Забрано {fmt_money(win_amount)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("mines"))
    elif act == "cancel":
        if len(game.opened) == 0:
            update_balance(uid, game.bet)
            await c.message.answer(f"💣 Отмена, возврат {fmt_money(game.bet)}")
        else:
            await c.message.answer("❌ Нельзя отменить после хода")
        del active_mines[uid]
    elif act == "noop":
        await c.answer()
    elif act.startswith("cell"):
        cell = int(act.split(":")[2])
        win, mult = game.open(cell)
        if not win:
            add_bet(uid, "mines", game.bet, 0, 0)
            del active_mines[uid]
            await c.message.answer(f"💣 МИНА! Проигрыш {fmt_money(game.bet)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("mines"))
        else:
            if len(game.opened) >= (9 - game.mines):
                win_amount = round(game.bet * mult * get_multiplier(uid), 2)
                update_balance(uid, win_amount)
                add_bet(uid, "mines", game.bet, win_amount, mult)
                del active_mines[uid]
                await c.message.answer(f"💣 ВСЕ КЛЕТКИ! {fmt_money(win_amount)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("mines"))
            else:
                await c.message.edit_text(f"💣 Безопасно! Множитель x{mult:.2f}\nПотенциал {fmt_money(game.potential())}", reply_markup=mines_kb(game))
    await c.answer()

@dp.callback_query(F.data == "g:blackjack")
async def blackjack_start(c: CallbackQuery, state: FSMContext):
    if is_banned(c.from_user.id):
        await c.answer("🚫 Вы забанены", show_alert=True)
        return
    await state.set_state(GameStates.waiting_bet)
    await state.update_data(game="blackjack")
    await c.message.answer("🎴 Очко (блэкджек)\nВведи ставку:")
    await c.answer()

@dp.message(GameStates.waiting_bet)
async def blackjack_bet(m: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("game") != "blackjack":
        return
    try:
        bet = parse_amount(m.text)
        if bet < MIN_BET or bet > MAX_BET:
            await m.answer(f"❌ Ставка от {fmt_money(MIN_BET)} до {fmt_money(MAX_BET)}")
            return
    except:
        await m.answer("❌ Неверная сумма")
        return
    u = get_user(m.from_user.id)
    if u["balance"] < bet:
        await m.answer("❌ Недостаточно средств")
        return
    update_balance(m.from_user.id, -bet)
    deck = make_deck()
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]
    pv = hand_val(player)
    dv = hand_val(dealer)
    if pv == 21:
        if dv == 21:
            update_balance(m.from_user.id, bet)
            add_bet(m.from_user.id, "blackjack", bet, bet, 1)
            await m.answer(f"🎴 Ничья 21!\n💰 {fmt_money(get_user(m.from_user.id)['balance'])}", reply_markup=play_again_kb("blackjack"))
        else:
            win_amount = round(bet * 2.5 * get_multiplier(m.from_user.id), 2)
            update_balance(m.from_user.id, win_amount)
            add_bet(m.from_user.id, "blackjack", bet, win_amount, 2.5)
            await m.answer(f"🎴 BLACKJACK! {fmt_money(win_amount)}\n💰 {fmt_money(get_user(m.from_user.id)['balance'])}", reply_markup=play_again_kb("blackjack"))
    else:
        active_blackjack[m.from_user.id] = {"bet": bet, "deck": deck, "player": player, "dealer": dealer, "pv": pv}
        await m.answer(
            f"🎴 Ставка {fmt_money(bet)}\n"
            f"Дилер: {dealer[0]} ?\n"
            f"Вы: {' '.join(player)} ({pv})\n"
            f"Ход:",
            reply_markup=blackjack_kb()
        )
    await state.clear()

@dp.callback_query(F.data.startswith("bj:"))
async def blackjack_action(c: CallbackQuery):
    act = c.data.split(":")[1]
    uid = c.from_user.id
    game = active_blackjack.get(uid)
    if not game:
        await c.answer("Нет активной игры")
        return
    if act == "hit":
        if not game["deck"]:
            game["deck"] = make_deck()
        game["player"].append(game["deck"].pop())
        game["pv"] = hand_val(game["player"])
        if game["pv"] > 21:
            add_bet(uid, "blackjack", game["bet"], 0, 0)
            del active_blackjack[uid]
            await c.message.answer(f"🎴 Перебор {game['pv']}\n❌ -{fmt_money(game['bet'])}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("blackjack"))
        else:
            await c.message.edit_text(
                f"🎴 Дилер: {game['dealer'][0]} ?\n"
                f"Вы: {' '.join(game['player'])} ({game['pv']})\n"
                f"Ход:",
                reply_markup=blackjack_kb()
            )
    elif act == "stand":
        dv = hand_val(game["dealer"])
        while dv < 17:
            if not game["deck"]:
                game["deck"] = make_deck()
            game["dealer"].append(game["deck"].pop())
            dv = hand_val(game["dealer"])
        if dv > 21 or game["pv"] > dv:
            win_amount = round(game["bet"] * 2 * get_multiplier(uid), 2)
            update_balance(uid, win_amount)
            add_bet(uid, "blackjack", game["bet"], win_amount, 2)
            await c.message.answer(f"🎴 Вы {game['pv']} : {dv} дилер\n✅ +{fmt_money(win_amount)}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("blackjack"))
        elif game["pv"] == dv:
            update_balance(uid, game["bet"])
            add_bet(uid, "blackjack", game["bet"], game["bet"], 1)
            await c.message.answer(f"🎴 Ничья\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("blackjack"))
        else:
            add_bet(uid, "blackjack", game["bet"], 0, 0)
            await c.message.answer(f"🎴 Проигрыш {fmt_money(game['bet'])}\n💰 {fmt_money(get_user(uid)['balance'])}", reply_markup=play_again_kb("blackjack"))
        del active_blackjack[uid]
    await c.answer()

# ==================== БАНК (ДЕПОЗИТЫ) ====================
@dp.callback_query(F.data == "bank:open")
async def bank_open(c: CallbackQuery, state: FSMContext):
    await state.set_state(BankDeposit.amount)
    await c.message.answer("🏦 Сумма депозита (мин 100):")
    await c.answer()

@dp.message(BankDeposit.amount)
async def bank_amount(m: Message, state: FSMContext):
    try:
        amount = parse_amount(m.text)
        if amount < 100:
            await m.answer("❌ Минимум 100")
            return
    except:
        await m.answer("❌ Сумма")
        return
    u = get_user(m.from_user.id)
    if u["balance"] < amount:
        await m.answer("❌ Недостаточно средств")
        return
    await state.update_data(amount=amount)
    await m.answer("Выбери срок:", reply_markup=bank_terms_kb())

@dp.callback_query(F.data.startswith("bank:term:"))
async def bank_term(c: CallbackQuery, state: FSMContext):
    term = int(c.data.split(":")[2])
    data = await state.get_data()
    amount = data.get("amount")
    if not amount:
        await c.message.answer("❌ Ошибка")
        await state.clear()
        return
    ok, msg = open_deposit(c.from_user.id, amount, term)
    await c.message.answer(msg)
    await state.clear()
    await c.answer()

@dp.callback_query(F.data == "bank:list")
async def bank_list(c: CallbackQuery):
    deps = get_deposits(c.from_user.id)
    if not deps:
        await c.message.answer("📭 Нет активных депозитов")
    else:
        text = "🏦 Депозиты:\n"
        for d in deps:
            text += f"#{d['id']} | {fmt_money(d['amount'])} | {d['term']} дн | +{int(d['rate']*100)}%\n"
        await c.message.answer(text)
    await c.answer()

@dp.callback_query(F.data == "bank:claim")
async def bank_claim(c: CallbackQuery):
    cnt, total = claim_deposits(c.from_user.id)
    if cnt == 0:
        await c.message.answer("📭 Нет созревших депозитов")
    else:
        await c.message.answer(f"✅ Закрыто {cnt} депозитов, получено {fmt_money(total)}")
    await c.answer()

@dp.callback_query(F.data == "bank:cancel")
async def bank_cancel(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.answer("🛑 Отменено")
    await c.answer()

# ==================== ЧЕКИ ====================
@dp.callback_query(F.data == "ch:create")
async def ch_create(c: CallbackQuery, state: FSMContext):
    await state.set_state(CreateCheck.amount)
    await c.message.answer("🧾 Сумма на 1 активацию (мин 10):")
    await c.answer()

@dp.message(CreateCheck.amount)
async def ch_amount(m: Message, state: FSMContext):
    try:
        amount = parse_amount(m.text)
        if amount < 10:
            await m.answer("❌ Минимум 10")
            return
    except:
        await m.answer("❌ Сумма")
        return
    await state.update_data(amount=amount)
    await state.set_state(CreateCheck.count)
    await m.answer("Количество активаций (1-100):")

@dp.message(CreateCheck.count)
async def ch_count(m: Message, state: FSMContext):
    try:
        cnt = int(m.text)
        if cnt < 1 or cnt > 100:
            await m.answer("❌ 1-100")
            return
    except:
        await m.answer("❌ Число")
        return
    data = await state.get_data()
    amount = data["amount"]
    ok, code = create_check(m.from_user.id, amount, cnt)
    if not ok:
        await m.answer(ok)
    else:
        await m.answer(
            f"✅ Чек {code}\n"
            f"Сумма {fmt_money(amount)} x {cnt} = {fmt_money(amount*cnt)}\n"
            f"💰 {fmt_money(get_user(m.from_user.id)['balance'])}",
            reply_markup=share_check_kb(code, amount)
        )
    await state.clear()

@dp.callback_query(F.data == "ch:claim")
async def ch_claim(c: CallbackQuery, state: FSMContext):
    await state.set_state(ClaimCheck.code)
    await c.message.answer("Введи код чека:")
    await c.answer()

@dp.message(ClaimCheck.code)
async def ch_claim_code(m: Message, state: FSMContext):
    ok, msg, _ = claim_check(m.from_user.id, m.text.strip())
    await m.answer(msg)
    await state.clear()

@dp.callback_query(F.data == "ch:my")
async def ch_my(c: CallbackQuery):
    checks = get_my_checks(c.from_user.id)
    if not checks:
        await c.message.answer("📭 Нет чеков")
    else:
        text = "🧾 Твои чеки:\n"
        for ch in checks:
            text += f"🔑 {ch['code']} | {fmt_money(ch['amount'])} | осталось {ch['remaining']}\n"
        await c.message.answer(text)
    await c.answer()

@dp.callback_query(F.data.startswith("copy:"))
async def copy_code(c: CallbackQuery):
    code = c.data.split(":")[1]
    await c.answer(f"✅ Код скопирован: {code}", show_alert=True)
    await c.message.answer(f"📋 Код: `{code}`", parse_mode="Markdown")

# ==================== АДМИНКА ====================
@dp.callback_query(F.data == "adm:give")
async def adm_give(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id):
        await c.answer("⛔")
        return
    await state.set_state(AdminGive.target)
    await c.message.answer("💰 ID и сумма:\n123456789 100кк")
    await c.answer()

@dp.message(AdminGive.target)
async def adm_give_exec(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        await m.answer("⛔")
        return
    parts = m.text.split()
    if len(parts) != 2:
        await m.answer("❌ ID сумма")
        return
    try:
        uid = int(parts[0])
        amount = parse_amount(parts[1])
    except:
        await m.answer("❌ Ошибка")
        return
    update_balance(uid, amount)
    log_admin(m.from_user.id, "give", str(uid), str(amount))
    await m.answer(f"✅ {fmt_money(amount)} → {get_user(uid)['name']}")
    await state.clear()

@dp.callback_query(F.data == "adm:status")
async def adm_status(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id):
        await c.answer("⛔")
        return
    await state.set_state(AdminStatus.target)
    await c.message.answer("👑 Введи ID пользователя:")
    await c.answer()

@dp.message(AdminStatus.target)
async def adm_status_target(m: Message, state: FSMContext):
    try:
        uid = int(m.text.strip())
    except:
        await m.answer("❌ ID")
        return
    await state.update_data(target=uid)
    await m.answer("Выбери новый статус:", reply_markup=admin_status_kb())

@dp.callback_query(F.data.startswith("set_st:"))
async def adm_status_set(c: CallbackQuery, state: FSMContext):
    status = int(c.data.split(":")[1])
    data = await state.get_data()
    uid = data.get("target")
    if not uid:
        await c.answer("Ошибка")
        return
    set_user_status(uid, status)
    log_admin(c.from_user.id, "set_status", str(uid), str(status))
    await c.message.answer(f"✅ Статус {uid} → {STATUSES[status]['name']}")
    await state.clear()
    await c.answer()

@dp.callback_query(F.data == "adm:users")
async def adm_users(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("⛔")
        return
    users = get_top_users(20)
    text = "👥 Игроки:\n"
    for u in users:
        st_emoji = STATUSES[u["status"]]["emoji"]
        text += f"{st_emoji} {u['name']} — {fmt_money(u['balance'])}\n"
    await c.message.answer(text)
    await c.answer()

@dp.callback_query(F.data == "adm:broadcast")
async def adm_broadcast(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id):
        await c.answer("⛔")
        return
    await state.set_state(AdminBroadcast.text)
    await c.message.answer("📢 Введи текст рассылки:")
    await c.answer()

@dp.message(AdminBroadcast.text)
async def adm_broadcast_send(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        await m.answer("⛔")
        return
    text = m.html_text
    users = get_all_users()
    sent = 0
    for u in users:
        if u["is_banned"]:
            continue
        try:
            await m.bot.send_message(int(u["id"]), f"📢 Рассылка от администрации\n\n{text}")
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass
    log_admin(m.from_user.id, "broadcast", None, f"sent={sent}")
    await m.answer(f"✅ Отправлено {sent} пользователям")
    await state.clear()

@dp.callback_query(F.data == "adm:stats")
async def adm_stats(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("⛔")
        return
    stats = get_total_stats()
    await c.message.answer(
        f"📊 Статистика\n"
        f"👥 {stats['users']} игроков\n"
        f"💰 {fmt_money(stats['total_balance'])} в обороте\n"
        f"🎲 {stats['total_bets']} ставок"
    )
    await c.answer()

@dp.callback_query(F.data == "adm:promos")
async def adm_promos(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id):
        await c.answer("⛔")
        return
    await state.set_state(NewPromoStates.code)
    await c.message.answer("🎟 Введи код промокода (A-Z,0-9,_-):")
    await c.answer()

@dp.message(NewPromoStates.code)
async def adm_promo_code(m: Message, state: FSMContext):
    code = m.text.strip().upper()
    if not code or len(code) < 3:
        await m.answer("❌ 3+ символа")
        return
    await state.update_data(code=code)
    await state.set_state(NewPromoStates.reward)
    await m.answer("💰 Награда (число):")

@dp.message(NewPromoStates.reward)
async def adm_promo_reward(m: Message, state: FSMContext):
    try:
        reward = parse_amount(m.text)
    except:
        await m.answer("❌ Сумма")
        return
    await state.update_data(reward=reward)
    await state.set_state(NewPromoStates.activations)
    await m.answer("🎯 Количество активаций:")

@dp.message(NewPromoStates.activations)
async def adm_promo_acts(m: Message, state: FSMContext):
    try:
        acts = int(m.text)
        if acts <= 0:
            await m.answer("❌ >0")
            return
    except:
        await m.answer("❌ Число")
        return
    data = await state.get_data()
    ok = create_promo(data["code"], data["reward"], acts)
    if ok:
        await m.answer(f"✅ Промокод {data['code']} создан\nНаграда {fmt_money(data['reward'])} | {acts} активаций")
        log_admin(m.from_user.id, "create_promo", None, f"{data['code']} {data['reward']} {acts}")
    else:
        await m.answer("❌ Такой код уже есть")
    await state.clear()

@dp.callback_query(F.data == "adm:list_promos")
async def adm_list_promos(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("⛔")
        return
    promos = get_all_promos()
    if not promos:
        await c.message.answer("📭 Нет промокодов")
    else:
        text = "🎟 Список промокодов:\n"
        for p in promos:
            text += f"{p[0]} | {fmt_money(p[1])} | осталось {p[2]}\n"
        await c.message.answer(text)
    await c.answer()

@dp.callback_query(F.data == "adm:ban")
async def adm_ban(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id):
        await c.answer("⛔")
        return
    await state.set_state(AdminBan.target)
    await c.message.answer("🚫 Введи ID для бана:")
    await c.answer()

@dp.message(AdminBan.target)
async def adm_ban_exec(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        await m.answer("⛔")
        return
    try:
        uid = int(m.text.strip())
    except:
        await m.answer("❌ ID")
        return
    ban_user(uid)
    log_admin(m.from_user.id, "ban", str(uid), "")
    await m.answer(f"🚫 {uid} забанен")
    await state.clear()

@dp.callback_query(F.data == "adm:back")
async def adm_back(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("⛔")
        return
    await c.message.edit_text("👑 Админ-панель", reply_markup=admin_kb())
    await c.answer()

@dp.callback_query(F.data == "adm:close")
async def adm_close(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("⛔")
        return
    await c.message.delete()
    await c.answer()

# ==================== ИГРАТЬ СНОВА ====================
@dp.callback_query(F.data.startswith("again:"))
async def play_again(c: CallbackQuery, state: FSMContext):
    if is_banned(c.from_user.id):
        await c.answer("🚫 Вы забанены", show_alert=True)
        return
    game = c.data.split(":")[1]
    game_map = {
        "roulette": "g:roulette", "crash": "g:crash", "cube": "g:cube", "dice": "g:dice",
        "football": "g:football", "basket": "g:basket", "tower": "g:tower", "diamond": "g:diamond",
        "gold": "g:gold", "mines": "g:mines", "blackjack": "g:blackjack"
    }
    if game in game_map:
        await state.update_data(game=game)
        await state.set_state(GameStates.waiting_bet)
        await c.message.answer(f"🎮 Введи сумму ставки для {game}:")
    else:
        await c.message.answer("🎮 Выбери игру", reply_markup=games_kb())
    await c.answer()

# ==================== ЗАПУСК БОТА ====================
async def main():
    init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    print("✅ ONEmi Game Bot запущен")
    print(f"👑 Админы: {ADMIN_IDS}")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
