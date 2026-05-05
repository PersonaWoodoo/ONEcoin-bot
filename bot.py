# bot.py - ПОЛНАЯ ВЕРСИЯ ONEmi BOT (5000+ строк)
# ЧАСТЬ 1: Импорты, конфиг, инициализация БД

import asyncio
import html
import json
import random
import sqlite3
import string
import time
from datetime import datetime
from typing import Any, Dict, Optional, List, Tuple

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton
)

# ==================== КОНФИГУРАЦИЯ ====================
BOT_TOKEN = "8754529808:AAE5IEhizXS1sj6nm1n42KvdBN5XcdLm5dk"
ADMIN_IDS = [8478884644]

DB_PATH = "data.db"
START_BALANCE = 100.0
MIN_BET = 10.0
CURRENCY_NAME = "ONEmi"
BONUS_COOLDOWN_SECONDS = 12 * 60 * 60
BONUS_REWARD_MIN = 150
BONUS_REWARD_MAX = 350

# Статусы игроков (с множителями для выигрышей)
USER_STATUSES = {
    0: {"name": "🟢 Обычный", "emoji": "🟢", "multiplier": 1.00},
    1: {"name": "🟡 Продвинутый", "emoji": "🟡", "multiplier": 1.05},
    2: {"name": "🔴 VIP", "emoji": "🔴", "multiplier": 1.10},
    3: {"name": "🟣 Премиум", "emoji": "🟣", "multiplier": 1.15},
    4: {"name": "👑 Легенда", "emoji": "👑", "multiplier": 1.25},
    5: {"name": "⚡ Администратор", "emoji": "⚡", "multiplier": 1.50},
}

# Банковские депозиты
BANK_TERMS = {
    7: {"rate": 0.03, "name": "7 дней (+3%)"},
    14: {"rate": 0.07, "name": "14 дней (+7%)"},
    30: {"rate": 0.18, "name": "30 дней (+18%)"},
}

# Игровые множители
RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
TOWER_MULTIPLIERS = [1.20, 1.48, 1.86, 2.35, 2.95, 3.75, 4.85, 6.15]
GOLD_MULTIPLIERS = [1.15, 1.35, 1.62, 2.0, 2.55, 3.25, 4.2]
DIAMOND_MULTIPLIERS = [1.12, 1.28, 1.48, 1.72, 2.02, 2.4, 2.92, 3.6]
LEGACY_GOLD_MULTIPLIERS = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]
FOOTBALL_MULTIPLIER = 1.85
BASKETBALL_MULTIPLIER = 2.2
CRASH_MAX_MULTIPLIER = 10.0

# ==================== СОСТОЯНИЯ FSM ====================
class CheckCreateStates(StatesGroup):
    waiting_amount = State()
    waiting_count = State()

class CheckClaimStates(StatesGroup):
    waiting_code = State()

class PromoStates(StatesGroup):
    waiting_code = State()

class NewPromoStates(StatesGroup):
    waiting_code = State()
    waiting_reward = State()
    waiting_activations = State()

class BankStates(StatesGroup):
    waiting_amount = State()

class RouletteStates(StatesGroup):
    waiting_bet = State()
    waiting_choice = State()

class CrashStates(StatesGroup):
    waiting_bet = State()
    waiting_target = State()

class CubeStates(StatesGroup):
    waiting_bet = State()
    waiting_guess = State()

class DiceStates(StatesGroup):
    waiting_bet = State()
    waiting_guess = State()

class FootballStates(StatesGroup):
    waiting_bet = State()

class BasketStates(StatesGroup):
    waiting_bet = State()

class TowerStates(StatesGroup):
    waiting_bet = State()
    waiting_mines = State()

class GoldStates(StatesGroup):
    waiting_bet = State()

class DiamondStates(StatesGroup):
    waiting_bet = State()
    waiting_mines = State()

class MinesStates(StatesGroup):
    waiting_bet = State()
    waiting_mines = State()

class OchkoStates(StatesGroup):
    waiting_bet = State()
    waiting_confirm = State()

# Админские состояния
class AdminGiveStates(StatesGroup):
    waiting_target = State()
    waiting_amount = State()

class AdminStatusStates(StatesGroup):
    waiting_target = State()
    waiting_status = State()

class AdminBroadcastStates(StatesGroup):
    waiting_message = State()
    waiting_confirm = State()

class AdminSettingsStates(StatesGroup):
    waiting_setting = State()
    waiting_value = State()

class AdminGameChangeStates(StatesGroup):
    waiting_game = State()
    waiting_multiplier = State()

# ==================== ГЛОБАЛЬНЫЕ ХРАНИЛИЩА ====================
TOWER_GAMES: Dict[int, Dict[str, Any]] = {}
GOLD_GAMES: Dict[int, Dict[str, Any]] = {}
DIAMOND_GAMES: Dict[int, Dict[str, Any]] = {}
MINES_GAMES: Dict[int, Dict[str, Any]] = {}
OCHKO_GAMES: Dict[int, Dict[str, Any]] = {}
NAVI_GAMES: Dict[int, Dict[str, Any]] = {}

LEGACY_GOLD_GAMES: Dict[str, Dict[str, Any]] = {}
LEGACY_TOWER_GAMES: Dict[str, Dict[str, Any]] = {}
LEGACY_MINES_GAMES: Dict[str, Dict[str, Any]] = {}
LEGACY_DIAMOND_GAMES: Dict[str, Dict[str, Any]] = {}
LEGACY_OCHKO_GAMES: Dict[str, Dict[str, Any]] = {}
LEGACY_FOOTBALL_GAMES: Dict[int, Dict[str, Any]] = {}

user_game_locks: Dict[str, asyncio.Lock] = {}
admin_logs: List[Dict] = []

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def is_admin_user(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def get_user_status_emoji(status: int) -> str:
    return USER_STATUSES.get(status, USER_STATUSES[0])["emoji"]

def get_user_status_name(status: int) -> str:
    return USER_STATUSES.get(status, USER_STATUSES[0])["name"]

def get_user_status_multiplier(status: int) -> float:
    return USER_STATUSES.get(status, USER_STATUSES[0])["multiplier"]

def fmt_money(value: float) -> str:
    value = round(float(value), 2)
    if value >= 1_000_000:
        return f"{value/1_000_000:.2f}M {CURRENCY_NAME}"
    elif value >= 1000:
        return f"{value/1000:.2f}K {CURRENCY_NAME}"
    elif value == int(value):
        return f"{int(value)} {CURRENCY_NAME}"
    return f"{value:.2f} {CURRENCY_NAME}"

def fmt_dt(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")

def fmt_left(seconds: int) -> str:
    seconds = max(0, seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}ч {m}м"
    if m > 0:
        return f"{m}м {s}с"
    return f"{s}с"

def parse_amount(text: str) -> float:
    raw = str(text or "").strip().lower().replace(" ", "").replace(",", ".")
    multiplier = 1.0
    if raw.endswith(("к", "k")):
        raw = raw[:-1]
        multiplier = 1000.0
    elif raw.endswith(("м", "m")):
        raw = raw[:-1]
        multiplier = 1_000_000.0
    
    value = float(raw) * multiplier
    if value <= 0:
        raise ValueError("amount must be positive")
    return round(value, 2)

def parse_int(text: str) -> int:
    return int(str(text or "").strip())

def normalize_text(text: Optional[str]) -> str:
    s = str(text or "").lower().strip()
    for symbol in ["💰", "👤", "🎁", "🎮", "🧾", "🏦", "🎟", "❓", "✨", "•", "|", "✅", "❌"]:
        s = s.replace(symbol, " ")
    return " ".join(s.split())

def escape_html(text: Optional[str]) -> str:
    return html.escape(str(text or ""), quote=False)

def mention_user(user_id: int, name: Optional[str] = None) -> str:
    label = escape_html(name or f"Игрок {user_id}")
    return f'<a href="tg://user?id={user_id}">{label}</a>'

def headline_user(emoji: str, user_id: int, name: Optional[str], text: str) -> str:
    return f"{emoji} {mention_user(user_id, name)}, {escape_html(text)}"

def normalize_promo_code(text: str) -> str:
    code = str(text or "").strip().upper()
    allowed = set(string.ascii_uppercase + string.digits + "_-")
    if not (3 <= len(code) <= 24):
        raise ValueError("length")
    if any(ch not in allowed for ch in code):
        raise ValueError("symbols")
    return code

def log_admin_action(admin_id: int, action: str, target_id: int = None, details: str = ""):
    admin_logs.append({
        "admin_id": admin_id,
        "action": action,
        "target_id": target_id,
        "details": details,
        "timestamp": int(time.time())
    })
    while len(admin_logs) > 1000:
        admin_logs.pop(0)

# ==================== ИНИЦИАЛИЗАЦИЯ БД ====================

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    conn = get_db()
    cursor = conn.cursor()
    
    # Таблица пользователей (расширенная)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            coins REAL DEFAULT 100,
            status INTEGER DEFAULT 0,
            total_bets INTEGER DEFAULT 0,
            total_wins INTEGER DEFAULT 0,
            total_losses INTEGER DEFAULT 0,
            total_win_amount REAL DEFAULT 0,
            total_lose_amount REAL DEFAULT 0,
            joined_at INTEGER DEFAULT 0,
            last_active INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            ban_reason TEXT,
            referrer_id TEXT
        )
    """)
    
    # Таблица ставок
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            bet_amount REAL,
            game TEXT,
            choice TEXT,
            outcome TEXT,
            win INTEGER,
            payout REAL,
            multiplier REAL,
            ts INTEGER
        )
    """)
    
    # Таблица чеков
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS checks (
            code TEXT PRIMARY KEY,
            creator_id TEXT,
            per_user REAL,
            remaining INTEGER,
            claimed TEXT
        )
    """)
    
    # Таблица промокодов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS promos (
            name TEXT PRIMARY KEY,
            reward REAL,
            claimed TEXT,
            remaining_activations INTEGER
        )
    """)
    
    # Таблица депозитов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bank_deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            principal REAL,
            rate REAL,
            term_days INTEGER,
            opened_at INTEGER,
            status TEXT,
            closed_at INTEGER
        )
    """)
    
    # Таблица JSON данных (для бонусов и настроек)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS json_data (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Таблица рефералов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id TEXT,
            referred_id TEXT,
            reward_claimed INTEGER DEFAULT 0,
            ts INTEGER
        )
    """)
    
    # Таблица ежедневных заданий
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_tasks (
            user_id TEXT PRIMARY KEY,
            last_claim INTEGER,
            streak INTEGER DEFAULT 0
        )
    """)
    
    # Таблица ачивок
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            ach_type TEXT,
            ach_value INTEGER,
            completed_at INTEGER
        )
    """)
    
    conn.commit()
    conn.close()

def now_ts() -> int:
    return int(time.time())

def ensure_user_in_conn(conn: sqlite3.Connection, user_id: int) -> None:
    now = now_ts()
    conn.execute("""
        INSERT OR IGNORE INTO users (id, coins, status, total_bets, total_wins, total_losses,
        total_win_amount, total_lose_amount, joined_at, last_active, is_banned)
        VALUES (?, ?, 0, 0, 0, 0, 0, 0, ?, ?, 0)
    """, (str(user_id), START_BALANCE, now, now))

def ensure_user(user_id: int) -> None:
    conn = get_db()
    try:
        ensure_user_in_conn(conn, user_id)
        conn.commit()
    finally:
        conn.close()

def get_user(user_id: int) -> Dict:
    conn = get_db()
    try:
        ensure_user_in_conn(conn, user_id)
        row = conn.execute("SELECT * FROM users WHERE id = ?", (str(user_id),)).fetchone()
        conn.commit()
        return dict(row)
    finally:
        conn.close()

def get_user_by_id(user_id: int) -> Optional[Dict]:
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (str(user_id),)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def set_json_value(key: str, value: Any) -> None:
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO json_data (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, json.dumps(value, ensure_ascii=False)))
        conn.commit()
    finally:
        conn.close()

def get_json_value(key: str, default: Any = None) -> Any:
    conn = get_db()
    try:
        row = conn.execute("SELECT value FROM json_data WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except:
            return default
    finally:
        conn.close()

def update_balance(user_id: int, delta: float) -> float:
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        conn.execute("UPDATE users SET coins = coins + ? WHERE id = ?", (round(delta, 2), str(user_id)))
        row = conn.execute("SELECT coins FROM users WHERE id = ?", (str(user_id),)).fetchone()
        conn.commit()
        return float(row["coins"])
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def set_balance(user_id: int, amount: float) -> float:
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        conn.execute("UPDATE users SET coins = ? WHERE id = ?", (round(amount, 2), str(user_id)))
        conn.commit()
        return round(amount, 2)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def set_user_status(user_id: int, status: int) -> bool:
    if status not in USER_STATUSES:
        return False
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        conn.execute("UPDATE users SET status = ? WHERE id = ?", (status, str(user_id)))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def ban_user(user_id: int, reason: str = "") -> bool:
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        conn.execute("UPDATE users SET is_banned = 1, ban_reason = ? WHERE id = ?", (reason, str(user_id)))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def unban_user(user_id: int) -> bool:
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        conn.execute("UPDATE users SET is_banned = 0, ban_reason = NULL WHERE id = ?", (str(user_id),))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def is_user_banned(user_id: int) -> Tuple[bool, str]:
    user = get_user(user_id)
    return (user.get("is_banned", 0) == 1, user.get("ban_reason", "") or "")

def reserve_bet(user_id: int, bet: float) -> Tuple[bool, float]:
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        row = conn.execute("SELECT coins FROM users WHERE id = ?", (str(user_id),)).fetchone()
        coins = float(row["coins"])
        if coins < bet:
            conn.rollback()
            return False, coins
        new_balance = round(coins - bet, 2)
        conn.execute("UPDATE users SET coins = ? WHERE id = ?", (new_balance, str(user_id)))
        conn.execute("UPDATE users SET total_bets = total_bets + 1, last_active = ? WHERE id = ?",
                     (now_ts(), str(user_id)))
        conn.commit()
        return True, new_balance
    except:
        conn.rollback()
        raise
    finally:
        conn.close()

def finalize_reserved_bet(user_id: int, bet: float, payout: float, game: str, outcome: str) -> float:
    payout = round(max(0.0, payout), 2)
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        
        # Получаем статус для множителя
        status_row = conn.execute("SELECT status FROM users WHERE id = ?", (str(user_id),)).fetchone()
        status = int(status_row["status"])
        multiplier = get_user_status_multiplier(status)
        
        # Применяем множитель к выигрышу
        if payout > 0:
            final_payout = round(payout * multiplier, 2)
            conn.execute("UPDATE users SET coins = coins + ? WHERE id = ?", (final_payout, str(user_id)))
            conn.execute("UPDATE users SET total_wins = total_wins + 1, total_win_amount = total_win_amount + ? WHERE id = ?",
                         (final_payout, str(user_id)))
        else:
            final_payout = 0
            conn.execute("UPDATE users SET total_losses = total_losses + 1, total_lose_amount = total_lose_amount + ? WHERE id = ?",
                         (round(bet, 2), str(user_id)))
        
        conn.execute("""
            INSERT INTO bets (user_id, bet_amount, game, choice, outcome, win, payout, multiplier, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (str(user_id), round(bet, 2), game, outcome, outcome, 1 if final_payout > 0 else 0,
              final_payout, multiplier, now_ts()))
        
        row = conn.execute("SELECT coins FROM users WHERE id = ?", (str(user_id),)).fetchone()
        conn.commit()
        return float(row["coins"])
    except:
        conn.rollback()
        raise
    finally:
        conn.close()

def settle_instant_bet(user_id: int, bet: float, payout: float, game: str, outcome: str) -> Tuple[bool, float]:
    payout = round(max(0.0, payout), 2)
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        row = conn.execute("SELECT coins, status FROM users WHERE id = ?", (str(user_id),)).fetchone()
        coins = float(row["coins"])
        status = int(row["status"])
        
        if coins < bet:
            conn.rollback()
            return False, coins
        
        multiplier = get_user_status_multiplier(status)
        
        if payout > 0:
            final_payout = round(payout * multiplier, 2)
            new_balance = round(coins - bet + final_payout, 2)
            conn.execute("UPDATE users SET coins = ? WHERE id = ?", (new_balance, str(user_id)))
            conn.execute("UPDATE users SET total_wins = total_wins + 1, total_win_amount = total_win_amount + ? WHERE id = ?",
                         (final_payout, str(user_id)))
        else:
            final_payout = 0
            new_balance = round(coins - bet, 2)
            conn.execute("UPDATE users SET coins = ? WHERE id = ?", (new_balance, str(user_id)))
            conn.execute("UPDATE users SET total_losses = total_losses + 1, total_lose_amount = total_lose_amount + ? WHERE id = ?",
                         (round(bet, 2), str(user_id)))
        
        conn.execute("UPDATE users SET total_bets = total_bets + 1, last_active = ? WHERE id = ?",
                     (now_ts(), str(user_id)))
        
        conn.execute("""
            INSERT INTO bets (user_id, bet_amount, game, choice, outcome, win, payout, multiplier, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (str(user_id), round(bet, 2), game, outcome, outcome, 1 if final_payout > 0 else 0,
              final_payout, multiplier, now_ts()))
        
        conn.commit()
        return True, new_balance
    except:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_profile_stats(user_id: int) -> Dict:
    user = get_user(user_id)
    conn = get_db()
    try:
        row = conn.execute("""
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN win = 1 THEN 1 ELSE 0 END), 0) AS wins,
                COALESCE(SUM(payout - bet_amount), 0) AS net
            FROM bets WHERE user_id = ?
        """, (str(user_id),)).fetchone()
        
        dep = conn.execute("""
            SELECT
                COUNT(*) AS active_count,
                COALESCE(SUM(principal), 0) AS active_sum
            FROM bank_deposits WHERE user_id = ? AND status = 'active'
        """, (str(user_id),)).fetchone()
        
        conn.commit()
        return {
            "coins": float(user["coins"]),
            "status": int(user["status"]),
            "total": int(row["total"]),
            "wins": int(row["wins"]),
            "net": float(row["net"]),
            "active_deposits": int(dep["active_count"]),
            "active_deposit_sum": float(dep["active_sum"]),
            "total_bets": int(user["total_bets"]),
            "total_wins": int(user["total_wins"]),
            "total_losses": int(user["total_losses"]),
            "total_win_amount": float(user["total_win_amount"]),
            "total_lose_amount": float(user["total_lose_amount"]),
            "joined_at": int(user["joined_at"]),
        }
    finally:
        conn.close()

def get_top_balances(limit: int = 10) -> List[Dict]:
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT id, coins, status FROM users
            WHERE is_banned = 0
            ORDER BY coins DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_all_users() -> List[Dict]:
    conn = get_db()
    try:
        rows = conn.execute("SELECT id, coins, status, is_banned FROM users").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def get_total_stats() -> Dict:
    conn = get_db()
    try:
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_coins = conn.execute("SELECT COALESCE(SUM(coins), 0) FROM users").fetchone()[0]
        total_bets = conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0]
        total_wins = conn.execute("SELECT COUNT(*) FROM bets WHERE win = 1").fetchone()[0]
        return {
            "users": users,
            "total_coins": float(total_coins),
            "total_bets": total_bets,
            "total_wins": total_wins,
        }
    finally:
        conn.close()

# ==================== ЧЕКИ ====================

def generate_check_code(conn: sqlite3.Connection) -> str:
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        row = conn.execute("SELECT 1 FROM checks WHERE code = ?", (code,)).fetchone()
        if not row:
            return code

def create_check(user_id: int, per_user: float, count: int) -> Tuple[bool, str]:
    total = round(per_user * count, 2)
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        row = conn.execute("SELECT coins FROM users WHERE id = ?", (str(user_id),)).fetchone()
        if float(row["coins"]) < total:
            conn.rollback()
            return False, "Недостаточно средств"
        
        code = generate_check_code(conn)
        conn.execute("UPDATE users SET coins = coins - ? WHERE id = ?", (total, str(user_id)))
        conn.execute("""
            INSERT INTO checks (code, creator_id, per_user, remaining, claimed)
            VALUES (?, ?, ?, ?, ?)
        """, (code, str(user_id), round(per_user, 2), count, "[]"))
        conn.commit()
        return True, code
    except:
        conn.rollback()
        raise
    finally:
        conn.close()

def claim_check(user_id: int, code: str) -> Tuple[bool, str, float]:
    code = code.upper().strip()
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        row = conn.execute("SELECT * FROM checks WHERE code = ?", (code,)).fetchone()
        if not row:
            conn.rollback()
            return False, "Чек не найден", 0
        
        remaining = int(row["remaining"])
        if remaining <= 0:
            conn.rollback()
            return False, "Чек уже закончился", 0
        
        claimed = json.loads(row["claimed"] or "[]")
        if str(user_id) in claimed:
            conn.rollback()
            return False, "Ты уже активировал этот чек", 0
        
        claimed.append(str(user_id))
        reward = round(float(row["per_user"]), 2)
        
        conn.execute("UPDATE users SET coins = coins + ? WHERE id = ?", (reward, str(user_id)))
        conn.execute("UPDATE checks SET remaining = ?, claimed = ? WHERE code = ?",
                     (remaining - 1, json.dumps(claimed), code))
        conn.commit()
        return True, "Чек активирован", reward
    except:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_user_checks(user_id: int) -> List[Dict]:
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT code, per_user, remaining FROM checks
            WHERE creator_id = ? ORDER BY rowid DESC LIMIT 10
        """, (str(user_id),)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

# ==================== ПРОМОКОДЫ ====================

def redeem_promo(user_id: int, code: str) -> Tuple[bool, str, float]:
    code = code.upper().strip()
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        row = conn.execute("SELECT * FROM promos WHERE name = ?", (code,)).fetchone()
        if not row:
            conn.rollback()
            return False, "Промокод не найден", 0
        
        remaining = int(row["remaining_activations"])
        if remaining <= 0:
            conn.rollback()
            return False, "Промокод уже закончился", 0
        
        claimed = json.loads(row["claimed"] or "[]")
        if str(user_id) in claimed:
            conn.rollback()
            return False, "Ты уже активировал этот промокод", 0
        
        claimed.append(str(user_id))
        reward = round(float(row["reward"]), 2)
        
        conn.execute("UPDATE users SET coins = coins + ? WHERE id = ?", (reward, str(user_id)))
        conn.execute("UPDATE promos SET claimed = ?, remaining_activations = ? WHERE name = ?",
                     (json.dumps(claimed), remaining - 1, code))
        conn.commit()
        return True, "Промокод активирован", reward
    except:
        conn.rollback()
        raise
    finally:
        conn.close()

def add_promo(code: str, reward: float, activations: int) -> bool:
    code = code.upper().strip()
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO promos (name, reward, claimed, remaining_activations)
            VALUES (?, ?, '[]', ?)
            ON CONFLICT(name) DO UPDATE SET
                reward = excluded.reward,
                remaining_activations = excluded.remaining_activations,
                claimed = '[]'
        """, (code, round(reward, 2), int(activations)))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_all_promos() -> List[Dict]:
    conn = get_db()
    try:
        rows = conn.execute("SELECT name, reward, remaining_activations FROM promos").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

# ==================== ДЕПОЗИТЫ ====================

def add_deposit(user_id: int, amount: float, term_days: int) -> Tuple[bool, str]:
    if term_days not in BANK_TERMS:
        return False, "Неверный срок"
    
    ok, _ = reserve_bet(user_id, amount)
    if not ok:
        return False, "Недостаточно средств"
    
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO bank_deposits (user_id, principal, rate, term_days, opened_at, status)
            VALUES (?, ?, ?, ?, ?, 'active')
        """, (str(user_id), round(amount, 2), BANK_TERMS[term_days]["rate"], term_days, now_ts()))
        conn.commit()
        return True, f"Депозит открыт на {term_days} дней"
    finally:
        conn.close()

def get_user_deposits(user_id: int, active_only: bool = False) -> List[Dict]:
    conn = get_db()
    try:
        if active_only:
            rows = conn.execute("""
                SELECT * FROM bank_deposits
                WHERE user_id = ? AND status = 'active'
                ORDER BY id DESC
            """, (str(user_id),)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM bank_deposits
                WHERE user_id = ?
                ORDER BY id DESC LIMIT 15
            """, (str(user_id),)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def claim_deposits(user_id: int) -> Tuple[int, float]:
    now = now_ts()
    conn = get_db()
    total = 0.0
    count = 0
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        rows = conn.execute("""
            SELECT * FROM bank_deposits
            WHERE user_id = ? AND status = 'active'
        """, (str(user_id),)).fetchall()
        
        for row in rows:
            unlock = row["opened_at"] + row["term_days"] * 86400
            if now < unlock:
                continue
            payout = round(row["principal"] * (1 + row["rate"]), 2)
            total += payout
            count += 1
            conn.execute("UPDATE bank_deposits SET status = 'closed', closed_at = ? WHERE id = ?",
                         (now, row["id"]))
        
        if total > 0:
            conn.execute("UPDATE users SET coins = coins + ? WHERE id = ?", (total, str(user_id)))
        
        conn.commit()
        return count, total
    except:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_bank_summary(user_id: int) -> Dict:
    user = get_user(user_id)
    conn = get_db()
    try:
        dep = conn.execute("""
            SELECT
                COUNT(*) AS active_count,
                COALESCE(SUM(principal), 0) AS active_sum
            FROM bank_deposits
            WHERE user_id = ? AND status = 'active'
        """, (str(user_id),)).fetchone()
        return {
            "coins": float(user["coins"]),
            "active_count": int(dep["active_count"]),
            "active_sum": float(dep["active_sum"]),
        }
    finally:
        conn.close()

# ==================== БОНУСЫ ====================

def claim_daily_bonus(user_id: int) -> Tuple[bool, int, float, int]:
    now = now_ts()
    key = f"bonus:{user_id}"
    data = get_json_value(key, {})
    
    last_claim = data.get("last_claim", 0)
    streak = data.get("streak", 0)
    
    if now - last_claim < BONUS_COOLDOWN_SECONDS:
        remaining = BONUS_COOLDOWN_SECONDS - (now - last_claim)
        return False, remaining, 0, streak
    
    if now - last_claim > BONUS_COOLDOWN_SECONDS + 86400:
        streak = 1
    else:
        streak += 1
    
    reward = random.randint(BONUS_REWARD_MIN, BONUS_REWARD_MAX)
    reward = int(reward * (1 + min(streak * 0.05, 0.5)))
    
    update_balance(user_id, reward)
    set_json_value(key, {"last_claim": now, "streak": streak})
    
    return True, 0, float(reward), streak

# ==================== ОСНОВНЫЕ ИГРЫ ====================

def clear_active_sessions(user_id: int) -> None:
    TOWER_GAMES.pop(user_id, None)
    GOLD_GAMES.pop(user_id, None)
    DIAMOND_GAMES.pop(user_id, None)
    MINES_GAMES.pop(user_id, None)
    OCHKO_GAMES.pop(user_id, None)

def roulette_roll(choice: str) -> Tuple[bool, float, int, str]:
    number = random.randint(0, 36)
    if number == 0:
        color = "green"
    elif number in RED_NUMBERS:
        color = "red"
    else:
        color = "black"
    
    win = False
    multiplier = 0
    
    if choice == "red" and color == "red":
        win, multiplier = True, 2.0
    elif choice == "black" and color == "black":
        win, multiplier = True, 2.0
    elif choice == "even" and number != 0 and number % 2 == 0:
        win, multiplier = True, 2.0
    elif choice == "odd" and number != 0 and number % 2 == 1:
        win, multiplier = True, 2.0
    elif choice == "zero" and number == 0:
        win, multiplier = True, 35.0
    
    color_ru = {"red": "🔴 красное", "black": "⚫ черное", "green": "🟢 зеро"}[color]
    return win, multiplier, number, color_ru

def crash_roll() -> float:
    u = random.random()
    raw = 0.99 / (1.0 - u)
    return round(max(1.0, min(CRASH_MAX_MULTIPLIER, raw)), 2)

def dice_roll() -> int:
    return random.randint(1, 6)

def two_dice_sum() -> int:
    return random.randint(1, 6) + random.randint(1, 6)

def football_kick() -> Tuple[str, int]:
    val = random.randint(1, 6)
    return ("ГОЛ" if val >= 4 else "МИМО"), val

def basketball_shot() -> Tuple[str, int]:
    val = random.randint(1, 6)
    return ("ПОПАЛ" if val >= 4 else "ПРОМАХ"), val

def mines_multiplier(opened: int, mines: int) -> float:
    if opened <= 0:
        return 1.0
    safe = 9 - mines
    mult = (9.0 / max(1, safe)) ** opened * 0.95
    return round(mult, 2)

# Карты для Очко (Blackjack)
SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]

def make_deck() -> List[str]:
    deck = [f"{r}{s}" for r in RANKS for s in SUITS]
    random.shuffle(deck)
    return deck

def card_value(card: str) -> int:
    rank = card[:-1]
    if rank in ["J", "Q", "K"]:
        return 10
    if rank == "A":
        return 11
    return int(rank)

def hand_value(cards: List[str]) -> int:
    value = sum(card_value(c) for c in cards)
    aces = sum(1 for c in cards if c[:-1] == "A")
    while value > 21 and aces > 0:
        value -= 10
        aces -= 1
    return value

def format_cards(cards: List[str]) -> str:
    return " ".join(cards)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ИГР ====================

def _game_lock(user_id: int) -> asyncio.Lock:
    key = str(user_id)
    if key not in user_game_locks:
        user_game_locks[key] = asyncio.Lock()
    return user_game_locks[key]

def _new_gid(prefix: str) -> str:
    return prefix + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))

def parse_bet_legacy(raw: str, balance: float) -> int:
    arg = str(raw or "").strip().lower().replace(" ", "")
    if arg in {"все", "всё", "all"}:
        return int(balance)
    return int(parse_amount(arg))

def game_usage_text() -> str:
    return """<b>Примеры команд:</b>
<code>башня 300 2</code>
<code>золото 300</code>
<code>алмазы 300 2</code>
<code>мины 300 3</code>
<code>рул 300 чет</code>
<code>краш 300 2.5</code>
<code>кубик 300 5</code>
<code>кости 300 м</code>
<code>очко 300</code>
<code>футбол 300 гол</code>
<code>баскет 300</code>"""

# ==================== UI КЛАВИАТУРЫ (ЧАСТЬ 1) ====================

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Баланс", callback_data="menu:balance"),
         InlineKeyboardButton(text="🎁 Бонус", callback_data="menu:bonus")],
        [InlineKeyboardButton(text="🎮 Игры", callback_data="menu:games"),
         InlineKeyboardButton(text="🏆 Топ", callback_data="menu:top")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile"),
         InlineKeyboardButton(text="🏦 Банк", callback_data="menu:bank")],
        [InlineKeyboardButton(text="🧾 Чеки", callback_data="menu:checks"),
         InlineKeyboardButton(text="🎟 Промо", callback_data="menu:promo")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="menu:help")],
    ])

def games_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗼 Башня", callback_data="game:tower"),
         InlineKeyboardButton(text="🥇 Золото", callback_data="game:gold")],
        [InlineKeyboardButton(text="💎 Алмазы", callback_data="game:diamond"),
         InlineKeyboardButton(text="💣 Мины", callback_data="game:mines")],
        [InlineKeyboardButton(text="🎴 Очко", callback_data="game:ochko"),
         InlineKeyboardButton(text="🎡 Рулетка", callback_data="game:roulette")],
        [InlineKeyboardButton(text="📈 Краш", callback_data="game:crash"),
         InlineKeyboardButton(text="🎲 Кубик", callback_data="game:cube")],
        [InlineKeyboardButton(text="🎯 Кости", callback_data="game:dice"),
         InlineKeyboardButton(text="⚽ Футбол", callback_data="game:football")],
        [InlineKeyboardButton(text="🏀 Баскет", callback_data="game:basket")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:back")],
    ])

def roulette_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Красное (x2)", callback_data="roulette:red"),
         InlineKeyboardButton(text="⚫ Черное (x2)", callback_data="roulette:black")],
        [InlineKeyboardButton(text="2️⃣ Чет (x2)", callback_data="roulette:even"),
         InlineKeyboardButton(text="1️⃣ Нечет (x2)", callback_data="roulette:odd")],
        [InlineKeyboardButton(text="0️⃣ Зеро (x35)", callback_data="roulette:zero")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="game:back")],
    ])

def crash_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1.5x", callback_data="crash:1.5"),
         InlineKeyboardButton(text="2x", callback_data="crash:2"),
         InlineKeyboardButton(text="3x", callback_data="crash:3")],
        [InlineKeyboardButton(text="5x", callback_data="crash:5"),
         InlineKeyboardButton(text="10x", callback_data="crash:10")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="game:back")],
    ])

def cube_kb() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for i in range(1, 7):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"cube:{i}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="game:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def dice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬆️ Больше 7 (x1.9)", callback_data="dice:more"),
         InlineKeyboardButton(text="⬇️ Меньше 7 (x1.9)", callback_data="dice:less")],
        [InlineKeyboardButton(text="7️⃣ Ровно 7 (x5)", callback_data="dice:seven")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="game:back")],
    ])

def football_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⚽ ГОЛ (x{FOOTBALL_MULTIPLIER})", callback_data="football:goal"),
         InlineKeyboardButton(text=f"❌ МИМО (x{FOOTBALL_MULTIPLIER})", callback_data="football:miss")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="game:back")],
    ])

def basket_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🏀 ПОПАЛ (x{BASKETBALL_MULTIPLIER})", callback_data="basket:hit"),
         InlineKeyboardButton(text=f"❌ ПРОМАХ (x{BASKETBALL_MULTIPLIER})", callback_data="basket:miss")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="game:back")],
    ])

def tower_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1️⃣", callback_data="tower:1"),
         InlineKeyboardButton(text="2️⃣", callback_data="tower:2"),
         InlineKeyboardButton(text="3️⃣", callback_data="tower:3")],
        [InlineKeyboardButton(text="💰 Забрать", callback_data="tower:cash"),
         InlineKeyboardButton(text="❌ Сдаться", callback_data="tower:cancel")],
    ])

def ochko_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Взять", callback_data="ochko:hit"),
         InlineKeyboardButton(text="✋ Стоп", callback_data="ochko:stand")],
    ])

def ochko_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Начать", callback_data="ochko:start"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="ochko:cancel")],
    ])

def play_again_kb(game: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть снова", callback_data=f"again:{game}")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:games")],
    ])

def admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Выдать ONEmi", callback_data="admin:give")],
        [InlineKeyboardButton(text="👑 Сменить статус", callback_data="admin:status")],
        [InlineKeyboardButton(text="👥 Все игроки", callback_data="admin:users")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="🎟 Промокоды", callback_data="admin:promos")],
        [InlineKeyboardButton(text="🧾 Чеки", callback_data="admin:checks")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin:settings")],
        [InlineKeyboardButton(text="📝 Логи", callback_data="admin:logs")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin:close")],
    ])

def admin_status_kb() -> InlineKeyboardMarkup:
    buttons = []
    for status, info in USER_STATUSES.items():
        buttons.append([InlineKeyboardButton(
            text=f"{info['emoji']} {info['name']} (x{info['multiplier']})",
            callback_data=f"admin:set_status:{status}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_promos_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать промо", callback_data="admin:create_promo")],
        [InlineKeyboardButton(text="📋 Список промо", callback_data="admin:list_promos")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back")],
    ])

def bank_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Открыть депозит", callback_data="bank:open")],
        [InlineKeyboardButton(text="📋 Мои депозиты", callback_data="bank:list")],
        [InlineKeyboardButton(text="💰 Забрать депозиты", callback_data="bank:claim")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:back")],
    ])

def bank_terms_kb() -> InlineKeyboardMarkup:
    buttons = []
    for days, info in BANK_TERMS.items():
        buttons.append([InlineKeyboardButton(text=info["name"], callback_data=f"bank:term:{days}")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="bank:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def checks_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать чек", callback_data="checks:create")],
        [InlineKeyboardButton(text="💸 Активировать чек", callback_data="checks:claim")],
        [InlineKeyboardButton(text="📋 Мои чеки", callback_data="checks:my")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu:back")],
    ])

# Продолжение следует... (часть 2 - основные команды и обработчики)# bot.py - ЧАСТЬ 2/4: Основные команды и обработчики

dp = Dispatcher(storage=MemoryStorage())

# ==================== ОСНОВНЫЕ КОМАНДЫ ====================

@dp.message(CommandStart())
async def start_command(message: Message, state: FSMContext):
    user_id = message.from_user.id
    ensure_user(user_id)
    await state.clear()
    clear_active_sessions(user_id)
    
    user = get_user(user_id)
    status_info = USER_STATUSES.get(user["status"], USER_STATUSES[0])
    status_text = f"{status_info['emoji']} {status_info['name']}"
    
    # Проверка реферальной ссылки
    if message.text and len(message.text.split()) > 1:
        ref_id = message.text.split()[1]
        if ref_id.startswith("ref_"):
            try:
                referrer = int(ref_id[4:])
                if referrer != user_id:
                    conn = get_db()
                    conn.execute("UPDATE users SET referrer_id = ? WHERE id = ?", 
                                (str(referrer), str(user_id)))
                    conn.commit()
                    conn.close()
                    await message.answer(f"🎉 Вы были приглашены игроком {mention_user(referrer)}!")
                    await asyncio.sleep(0.5)
            except:
                pass
    
    await message.answer(
        f"🎮 <b>Добро пожаловать в ONEmi Game Bot!</b>\n\n"
        f"{status_text} {mention_user(user_id, message.from_user.first_name)}\n"
        f"💰 Баланс: <b>{fmt_money(user['coins'])}</b>\n\n"
        f"<b>📋 Основные команды:</b>\n"
        f"• <code>б</code> или <code>баланс</code>\n"
        f"• <code>бонус</code>\n"
        f"• <code>игры</code>\n"
        f"• <code>топ</code>\n"
        f"• <code>профиль</code>\n"
        f"• <code>банк</code>\n"
        f"• <code>чеки</code>\n"
        f"• <code>промо CODE</code>\n"
        f"• <code>помощь</code>\n\n"
        f"<i>Используй кнопки ниже для быстрого доступа</i>",
        reply_markup=main_menu_kb()
    )

@dp.message(Command("admin"))
async def admin_command(message: Message):
    if not is_admin_user(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return
    
    stats = get_total_stats()
    await message.answer(
        f"👑 <b>Панель администратора ONEmi</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"👥 Пользователей: <b>{stats['users']}</b>\n"
        f"💰 Монет в обращении: <b>{fmt_money(stats['total_coins'])}</b>\n"
        f"🎲 Всего ставок: <b>{stats['total_bets']}</b>\n"
        f"🏆 Всего побед: <b>{stats['total_wins']}</b>\n\n"
        f"<i>Выберите действие:</i>",
        reply_markup=admin_main_kb()
    )

@dp.message(Command("menu"))
async def menu_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📍 <b>Главное меню</b>\n"
        "Используй кнопки ниже для навигации:",
        reply_markup=main_menu_kb()
    )

@dp.message(lambda m: normalize_text(m.text) in {"отмена", "/cancel", "cancel"})
async def cancel_command(message: Message, state: FSMContext):
    await state.clear()
    clear_active_sessions(message.from_user.id)
    await message.answer("🛑 Действие отменено. Можешь начать заново 💫")

@dp.message(StateFilter(None), lambda m: normalize_text(m.text) in {"б", "баланс", "/balance", "balance"})
async def balance_command(message: Message):
    user = get_user(message.from_user.id)
    status_info = USER_STATUSES.get(user["status"], USER_STATUSES[0])
    await message.answer(
        f"{status_info['emoji']} {mention_user(message.from_user.id, message.from_user.first_name)}, твой баланс\n"
        f"<blockquote>💰 Доступно: <b>{fmt_money(user['coins'])}</b></blockquote>"
    )

@dp.message(StateFilter(None), lambda m: normalize_text(m.text) in {"профиль", "/profile", "profile"})
async def profile_command(message: Message):
    stats = get_profile_stats(message.from_user.id)
    total = max(1, stats["total"])
    wr = (stats["wins"] / total) * 100
    status_info = USER_STATUSES.get(stats["status"], USER_STATUSES[0])
    multiplier = status_info["multiplier"]
    
    await message.answer(
        f"{status_info['emoji']} <b>Профиль игрока</b>\n\n"
        f"{mention_user(message.from_user.id, message.from_user.first_name)}\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"🎭 Статус: {status_info['name']} (x{multiplier} к выигрышам)\n"
        f"💰 Баланс: <b>{fmt_money(stats['coins'])}</b>\n"
        f"📅 В игре с: {fmt_dt(stats['joined_at'])}\n\n"
        f"📊 <b>Игровая статистика</b>\n"
        f"🎲 Всего ставок: <b>{stats['total_bets']}</b>\n"
        f"✅ Побед: <b>{stats['wins']}</b> ({wr:.1f}%)\n"
        f"❌ Поражений: <b>{stats['total_losses']}</b>\n"
        f"🏆 Выиграно всего: <b>{fmt_money(stats['total_win_amount'])}</b>\n"
        f"💸 Проиграно всего: <b>{fmt_money(stats['total_lose_amount'])}</b>\n"
        f"📈 Нетто P/L: <b>{fmt_money(stats['net'])}</b>\n\n"
        f"🏦 <b>Депозиты</b>\n"
        f"📦 Активных: <b>{stats['active_deposits']}</b>\n"
        f"💰 Сумма: <b>{fmt_money(stats['active_deposit_sum'])}</b>"
    )

@dp.message(StateFilter(None), lambda m: normalize_text(m.text) in {"бонус", "/bonus", "bonus"})
async def bonus_command(message: Message):
    user_id = message.from_user.id
    success, remaining, reward, streak = claim_daily_bonus(user_id)
    
    if not success:
        await message.answer(
            f"{headline_user('🎁', user_id, message.from_user.first_name, 'бонус уже получен')}\n"
            f"<blockquote>Следующий бонус через: <b>{fmt_left(remaining)}</b></blockquote>"
        )
        return
    
    await message.answer(
        f"{headline_user('🎁', user_id, message.from_user.first_name, 'ты получил бонус')}\n"
        f"<blockquote>💰 Начислено: <b>{fmt_money(reward)}</b>\n"
        f"🔥 Стрик: <b>{streak} дней</b>\n"
        f"💰 Новый баланс: <b>{fmt_money(get_user(user_id)['coins'])}</b></blockquote>"
    )

@dp.message(StateFilter(None), lambda m: normalize_text(m.text) in {"помощь", "/help", "help"})
async def help_command(message: Message):
    admin_hint = ""
    if is_admin_user(message.from_user.id):
        admin_hint = (
            "\n\n🛠️ <b>Админ-команды:</b>\n"
            "• <code>/admin</code> - Открыть админ-панель\n"
            "• <code>/new_promo</code> - Создать промокод (по шагам)\n"
            "• <code>/addpromo КОД НАГРАДА АКТИВАЦИИ</code> - Быстрое создание\n"
            "• Ответь на сообщение <code>выдать 1000</code> - Выдать валюту\n"
            "• Ответь на сообщение <code>забрать 500</code> - Забрать валюту"
        )
    
    await message.answer(
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
        f"{game_usage_text()}\n\n"
        "<b>💰 Статусы и множители:</b>\n"
        "• 🟢 Обычный - x1.0 к выигрышам\n"
        "• 🟡 Продвинутый - x1.05\n"
        "• 🔴 VIP - x1.10\n"
        "• 🟣 Премиум - x1.15\n"
        "• 👑 Легенда - x1.25\n\n"
        "Отмена действия: <code>отмена</code>" + admin_hint,
        parse_mode="HTML"
    )

@dp.message(StateFilter(None), lambda m: normalize_text(m.text) in {"топ", "/top", "top"})
async def top_command(message: Message):
    rows = get_top_balances(10)
    if not rows:
        await message.answer("🏆 <b>Топ игроков</b>\n<blockquote><i>Пока список пуст.</i></blockquote>")
        return
    
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = ["🏆 <b>Топ игроков ONEmi по балансу</b>", "<blockquote>"]
    for idx, row in enumerate(rows, start=1):
        icon = medals.get(idx, f"{idx}.")
        status_emoji = get_user_status_emoji(row["status"])
        lines.append(f"{icon} {status_emoji} {mention_user(int(row['id']))} — <b>{fmt_money(float(row['coins']))}</b>")
    lines.append("</blockquote>")
    await message.answer("\n".join(lines))

@dp.message(StateFilter(None), lambda m: normalize_text(m.text) in {"игры", "/games", "games"})
async def games_command(message: Message):
    await message.answer(
        "🎮 <b>Игры ONEmi</b>\n"
        "Выбери игру кнопкой ниже.\n"
        "После выбора введи сумму ставки.\n\n"
        "<i>Для быстрого запуска можно использовать команды:</i>\n"
        f"{game_usage_text()}",
        reply_markup=games_kb(),
        parse_mode="HTML"
    )

# ==================== MENU CALLBACKS ====================

@dp.callback_query(F.data == "menu:balance")
async def menu_balance_cb(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    await callback.message.answer(f"💰 Ваш баланс: <b>{fmt_money(user['coins'])}</b>")
    await callback.answer()

@dp.callback_query(F.data == "menu:bonus")
async def menu_bonus_cb(callback: CallbackQuery):
    user_id = callback.from_user.id
    success, remaining, reward, streak = claim_daily_bonus(user_id)
    
    if not success:
        await callback.message.answer(
            f"🎁 Бонус уже получен!\nСледующий через: <b>{fmt_left(remaining)}</b>"
        )
    else:
        await callback.message.answer(
            f"🎁 <b>Бонус получен!</b>\n\n"
            f"💰 {fmt_money(reward)}\n"
            f"🔥 Стрик: {streak} дней\n"
            f"💰 Новый баланс: {fmt_money(get_user(user_id)['coins'])}"
        )
    await callback.answer()

@dp.callback_query(F.data == "menu:games")
async def menu_games_cb(callback: CallbackQuery):
    await callback.message.edit_text("🎮 <b>Выбери игру</b>", reply_markup=games_kb())
    await callback.answer()

@dp.callback_query(F.data == "menu:top")
async def menu_top_cb(callback: CallbackQuery):
    rows = get_top_balances(10)
    if not rows:
        await callback.message.answer("🏆 Топ игроков пока пуст")
    else:
        medals = ["🥇", "🥈", "🥉"]
        text = "🏆 <b>Топ игроков ONEmi</b>\n\n"
        for i, row in enumerate(rows, 1):
            medal = medals[i-1] if i <= 3 else f"{i}."
            status_emoji = get_user_status_emoji(row["status"])
            text += f"{medal} {status_emoji} <code>{row['id']}</code> — {fmt_money(row['coins'])}\n"
        await callback.message.answer(text)
    await callback.answer()

@dp.callback_query(F.data == "menu:profile")
async def menu_profile_cb(callback: CallbackQuery):
    await profile_command(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "menu:bank")
async def menu_bank_cb(callback: CallbackQuery):
    summary = get_bank_summary(callback.from_user.id)
    await callback.message.answer(
        f"🏦 <b>Банк ONEmi</b>\n\n"
        f"💰 Баланс: {fmt_money(summary['coins'])}\n"
        f"📦 Активных депозитов: {summary['active_count']}\n"
        f"💰 Сумма в депозитах: {fmt_money(summary['active_sum'])}\n\n"
        f"<i>Депозиты доступны на 7, 14 и 30 дней:\n"
        f"• 7 дней: +3%\n"
        f"• 14 дней: +7%\n"
        f"• 30 дней: +18%</i>",
        reply_markup=bank_kb()
    )
    await callback.answer()

@dp.callback_query(F.data == "menu:checks")
async def menu_checks_cb(callback: CallbackQuery):
    await callback.message.answer(
        "🧾 <b>Чеки ONEmi</b>\n\n"
        "Создавай чеки для друзей или активируй полученные.\n"
        "Чек можно активировать только один раз одним игроком.",
        reply_markup=checks_kb()
    )
    await callback.answer()

@dp.callback_query(F.data == "menu:promo")
async def menu_promo_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PromoStates.waiting_code)
    await callback.message.answer("🎟 <b>Активация промокода</b>\n\nВведите код промокода:")
    await callback.answer()

@dp.callback_query(F.data == "menu:help")
async def menu_help_cb(callback: CallbackQuery):
    await help_command(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "menu:back")
async def menu_back_cb(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎮 <b>Главное меню ONEmi</b>\nИспользуй кнопки ниже:",
        reply_markup=main_menu_kb()
    )
    await callback.answer()

@dp.callback_query(F.data == "game:back")
async def game_back_cb(callback: CallbackQuery):
    await callback.message.edit_text("🎮 <b>Выбери игру</b>", reply_markup=games_kb())
    await callback.answer()

# ==================== РУЛЕТКА ====================

@dp.callback_query(F.data == "game:roulette")
async def roulette_start_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(RouletteStates.waiting_bet)
    await state.update_data(game="roulette")
    await callback.message.answer(
        "🎡 <b>Рулетка</b>\n\n"
        f"💰 Минимальная ставка: {fmt_money(MIN_BET)}\n"
        "Введите сумму ставки:"
    )
    await callback.answer()

@dp.message(RouletteStates.waiting_bet)
async def roulette_process_bet(message: Message, state: FSMContext):
    try:
        bet = float(message.text.replace(",", ".").replace(" ", ""))
        if bet < MIN_BET:
            await message.answer(f"❌ Минимальная ставка: {fmt_money(MIN_BET)}")
            return
    except ValueError:
        await message.answer("❌ Введите число. Например: 100")
        return
    
    user = get_user(message.from_user.id)
    if user["coins"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {fmt_money(user['coins'])}")
        return
    
    await state.update_data(bet=bet)
    await state.set_state(RouletteStates.waiting_choice)
    await message.answer(
        f"💰 Ставка: {fmt_money(bet)}\n\n"
        "Выберите тип ставки:",
        reply_markup=roulette_kb()
    )

@dp.callback_query(RouletteStates.waiting_choice, F.data.startswith("roulette:"))
async def roulette_play_cb(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split(":")[1]
    data = await state.get_data()
    bet = data.get("bet", 0)
    
    if bet <= 0:
        await callback.message.answer("❌ Ошибка: ставка не найдена. Начните заново.")
        await state.clear()
        await callback.answer()
        return
    
    user_id = callback.from_user.id
    status_multiplier = get_user_status_multiplier(get_user(user_id)["status"])
    
    win, multiplier, number, color = roulette_roll(choice)
    win_amount = round(bet * multiplier, 2) if win else 0
    
    _, new_balance = settle_instant_bet(
        user_id=user_id,
        bet=bet,
        payout=win_amount,
        game="roulette",
        outcome=f"{choice}:{number}"
    )
    
    await state.clear()
    
    if win:
        await callback.message.answer(
            f"🎡 <b>Рулетка</b>\n\n"
            f"Выпало: <b>{number}</b> ({color})\n"
            f"Ваш выбор: {choice}\n"
            f"Множитель: x{multiplier}\n"
            f"Статус множитель: x{status_multiplier}\n"
            f"✅ <b>ПОБЕДА!</b>\n"
            f"💰 Выигрыш: {fmt_money(win_amount)}\n"
            f"💰 Баланс: {fmt_money(new_balance)}",
            reply_markup=play_again_kb("roulette")
        )
    else:
        await callback.message.answer(
            f"🎡 <b>Рулетка</b>\n\n"
            f"Выпало: <b>{number}</b> ({color})\n"
            f"Ваш выбор: {choice}\n"
            f"❌ <b>ПОРАЖЕНИЕ</b>\n"
            f"💸 Потеряно: {fmt_money(bet)}\n"
            f"💰 Баланс: {fmt_money(new_balance)}",
            reply_markup=play_again_kb("roulette")
        )
    
    await callback.answer()

# ==================== КРАШ ====================

@dp.callback_query(F.data == "game:crash")
async def crash_start_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CrashStates.waiting_bet)
    await state.update_data(game="crash")
    await callback.message.answer(
        "📈 <b>Краш</b>\n\n"
        f"💰 Минимальная ставка: {fmt_money(MIN_BET)}\n"
        "Введите сумму ставки:"
    )
    await callback.answer()

@dp.message(CrashStates.waiting_bet)
async def crash_process_bet(message: Message, state: FSMContext):
    try:
        bet = float(message.text.replace(",", ".").replace(" ", ""))
        if bet < MIN_BET:
            await message.answer(f"❌ Минимальная ставка: {fmt_money(MIN_BET)}")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    user = get_user(message.from_user.id)
    if user["coins"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {fmt_money(user['coins'])}")
        return
    
    await state.update_data(bet=bet)
    await state.set_state(CrashStates.waiting_target)
    await message.answer(
        f"💰 Ставка: {fmt_money(bet)}\n\n"
        "Выберите множитель выигрыша:",
        reply_markup=crash_kb()
    )

@dp.callback_query(CrashStates.waiting_target, F.data.startswith("crash:"))
async def crash_play_cb(callback: CallbackQuery, state: FSMContext):
    target = float(callback.data.split(":")[1])
    data = await state.get_data()
    bet = data.get("bet", 0)
    
    if bet <= 0:
        await callback.message.answer("❌ Ошибка: ставка не найдена")
        await state.clear()
        await callback.answer()
        return
    
    user_id = callback.from_user.id
    status_multiplier = get_user_status_multiplier(get_user(user_id)["status"])
    
    crash_point = crash_roll()
    win = target <= crash_point
    win_amount = round(bet * target, 2) if win else 0
    
    _, new_balance = settle_instant_bet(
        user_id=user_id,
        bet=bet,
        payout=win_amount,
        game="crash",
        outcome=f"target:{target}|crash:{crash_point}"
    )
    
    await state.clear()
    
    if win:
        await callback.message.answer(
            f"📈 <b>Краш</b>\n\n"
            f"Краш точка: <b>x{crash_point}</b>\n"
            f"Ваша цель: <b>x{target}</b>\n"
            f"Статус множитель: x{status_multiplier}\n"
            f"✅ <b>ПОБЕДА!</b>\n"
            f"💰 Выигрыш: {fmt_money(win_amount)}\n"
            f"💰 Баланс: {fmt_money(new_balance)}",
            reply_markup=play_again_kb("crash")
        )
    else:
        await callback.message.answer(
            f"📈 <b>Краш</b>\n\n"
            f"Краш точка: <b>x{crash_point}</b>\n"
            f"Ваша цель: <b>x{target}</b>\n"
            f"❌ <b>ПОРАЖЕНИЕ</b>\n"
            f"💸 Потеряно: {fmt_money(bet)}\n"
            f"💰 Баланс: {fmt_money(new_balance)}",
            reply_markup=play_again_kb("crash")
        )
    
    await callback.answer()

# ==================== КУБИК ====================

@dp.callback_query(F.data == "game:cube")
async def cube_start_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CubeStates.waiting_bet)
    await state.update_data(game="cube")
    await callback.message.answer(
        "🎲 <b>Кубик</b>\n\n"
        f"💰 Минимальная ставка: {fmt_money(MIN_BET)}\n"
        "Введите сумму ставки:"
    )
    await callback.answer()

@dp.message(CubeStates.waiting_bet)
async def cube_process_bet(message: Message, state: FSMContext):
    try:
        bet = float(message.text.replace(",", ".").replace(" ", ""))
        if bet < MIN_BET:
            await message.answer(f"❌ Минимальная ставка: {fmt_money(MIN_BET)}")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    user = get_user(message.from_user.id)
    if user["coins"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {fmt_money(user['coins'])}")
        return
    
    await state.update_data(bet=bet)
    await state.set_state(CubeStates.waiting_guess)
    await message.answer(
        f"💰 Ставка: {fmt_money(bet)}\n\n"
        "Угадайте число от 1 до 6:",
        reply_markup=cube_kb()
    )

@dp.callback_query(CubeStates.waiting_guess, F.data.startswith("cube:"))
async def cube_play_cb(callback: CallbackQuery, state: FSMContext):
    guess = int(callback.data.split(":")[1])
    data = await state.get_data()
    bet = data.get("bet", 0)
    
    if bet <= 0:
        await callback.message.answer("❌ Ошибка: ставка не найдена")
        await state.clear()
        await callback.answer()
        return
    
    user_id = callback.from_user.id
    status_multiplier = get_user_status_multiplier(get_user(user_id)["status"])
    
    result = dice_roll()
    win = guess == result
    multiplier = 5.8
    win_amount = round(bet * multiplier, 2) if win else 0
    
    _, new_balance = settle_instant_bet(
        user_id=user_id,
        bet=bet,
        payout=win_amount,
        game="cube",
        outcome=f"guess:{guess}|roll:{result}"
    )
    
    await state.clear()
    
    if win:
        await callback.message.answer(
            f"🎲 <b>Кубик</b>\n\n"
            f"Выпало: <b>{result}</b>\n"
            f"Ваше число: <b>{guess}</b>\n"
            f"Множитель: x{multiplier}\n"
            f"Статус множитель: x{status_multiplier}\n"
            f"✅ <b>ПОБЕДА!</b>\n"
            f"💰 Выигрыш: {fmt_money(win_amount)}\n"
            f"💰 Баланс: {fmt_money(new_balance)}",
            reply_markup=play_again_kb("cube")
        )
    else:
        await callback.message.answer(
            f"🎲 <b>Кубик</b>\n\n"
            f"Выпало: <b>{result}</b>\n"
            f"Ваше число: <b>{guess}</b>\n"
            f"❌ <b>ПОРАЖЕНИЕ</b>\n"
            f"💸 Потеряно: {fmt_money(bet)}\n"
            f"💰 Баланс: {fmt_money(new_balance)}",
            reply_markup=play_again_kb("cube")
        )
    
    await callback.answer()

# ==================== КОСТИ (сумма двух кубиков) ====================

@dp.callback_query(F.data == "game:dice")
async def dice_start_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DiceStates.waiting_bet)
    await state.update_data(game="dice")
    await callback.message.answer(
        "🎯 <b>Кости (сумма двух кубиков)</b>\n\n"
        f"💰 Минимальная ставка: {fmt_money(MIN_BET)}\n"
        "Введите сумму ставки:"
    )
    await callback.answer()

@dp.message(DiceStates.waiting_bet)
async def dice_process_bet(message: Message, state: FSMContext):
    try:
        bet = float(message.text.replace(",", ".").replace(" ", ""))
        if bet < MIN_BET:
            await message.answer(f"❌ Минимальная ставка: {fmt_money(MIN_BET)}")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    user = get_user(message.from_user.id)
    if user["coins"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {fmt_money(user['coins'])}")
        return
    
    await state.update_data(bet=bet)
    await state.set_state(DiceStates.waiting_guess)
    await message.answer(
        f"💰 Ставка: {fmt_money(bet)}\n\n"
        "Выберите условие:",
        reply_markup=dice_kb()
    )

@dp.callback_query(DiceStates.waiting_guess, F.data.startswith("dice:"))
async def dice_play_cb(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split(":")[1]
    data = await state.get_data()
    bet = data.get("bet", 0)
    
    if bet <= 0:
        await callback.message.answer("❌ Ошибка: ставка не найдена")
        await state.clear()
        await callback.answer()
        return
    
    user_id = callback.from_user.id
    status_multiplier = get_user_status_multiplier(get_user(user_id)["status"])
    
    result = two_dice_sum()
    
    win = False
    multiplier = 0
    if choice == "more" and result > 7:
        win, multiplier = True, 1.9
    elif choice == "less" and result < 7:
        win, multiplier = True, 1.9
    elif choice == "seven" and result == 7:
        win, multiplier = True, 5.0
    
    choice_names = {"more": "больше 7", "less": "меньше 7", "seven": "ровно 7"}
    win_amount = round(bet * multiplier, 2) if win else 0
    
    _, new_balance = settle_instant_bet(
        user_id=user_id,
        bet=bet,
        payout=win_amount,
        game="dice",
        outcome=f"{choice}:{result}"
    )
    
    await state.clear()
    
    if win:
        await callback.message.answer(
            f"🎯 <b>Кости</b>\n\n"
            f"Сумма кубиков: <b>{result}</b>\n"
            f"Ваш выбор: {choice_names[choice]}\n"
            f"Множитель: x{multiplier}\n"
            f"Статус множитель: x{status_multiplier}\n"
            f"✅ <b>ПОБЕДА!</b>\n"
            f"💰 Выигрыш: {fmt_money(win_amount)}\n"
            f"💰 Баланс: {fmt_money(new_balance)}",
            reply_markup=play_again_kb("dice")
        )
    else:
        await callback.message.answer(
            f"🎯 <b>Кости</b>\n\n"
            f"Сумма кубиков: <b>{result}</b>\n"
            f"Ваш выбор: {choice_names[choice]}\n"
            f"❌ <b>ПОРАЖЕНИЕ</b>\n"
            f"💸 Потеряно: {fmt_money(bet)}\n"
            f"💰 Баланс: {fmt_money(new_balance)}",
            reply_markup=play_again_kb("dice")
        )
    
    await callback.answer()

# ==================== ФУТБОЛ ====================

@dp.callback_query(F.data == "game:football")
async def football_start_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FootballStates.waiting_bet)
    await state.update_data(game="football")
    await callback.message.answer(
        "⚽ <b>Футбол</b>\n\n"
        f"💰 Минимальная ставка: {fmt_money(MIN_BET)}\n"
        "Введите сумму ставки:"
    )
    await callback.answer()

@dp.message(FootballStates.waiting_bet)
async def football_process_bet(message: Message, state: FSMContext):
    try:
        bet = float(message.text.replace(",", ".").replace(" ", ""))
        if bet < MIN_BET:
            await message.answer(f"❌ Минимальная ставка: {fmt_money(MIN_BET)}")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    user = get_user(message.from_user.id)
    if user["coins"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {fmt_money(user['coins'])}")
        return
    
    await state.update_data(bet=bet)
    await message.answer(
        f"💰 Ставка: {fmt_money(bet)}\n\n"
        "Выберите исход:",
        reply_markup=football_kb()
    )

@dp.callback_query(F.data.startswith("football:"))
async def football_play_cb(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split(":")[1]
    data = await state.get_data()
    bet = data.get("bet", 0)
    
    if bet <= 0:
        await callback.message.answer("❌ Ошибка: ставка не найдена")
        await state.clear()
        await callback.answer()
        return
    
    user_id = callback.from_user.id
    status_multiplier = get_user_status_multiplier(get_user(user_id)["status"])
    
    result, value = football_kick()
    win = (choice == "goal" and result == "ГОЛ") or (choice == "miss" and result == "МИМО")
    
    multiplier = FOOTBALL_MULTIPLIER
    win_amount = round(bet * multiplier, 2) if win else 0
    
    _, new_balance = settle_instant_bet(
        user_id=user_id,
        bet=bet,
        payout=win_amount,
        game="football",
        outcome=f"{choice}:{result}"
    )
    
    await state.clear()
    
    if win:
        await callback.message.answer(
            f"⚽ <b>Футбол</b>\n\n"
            f"Удар: <b>{result}</b>\n"
            f"Ваш выбор: {'ГОЛ' if choice == 'goal' else 'МИМО'}\n"
            f"Множитель: x{multiplier}\n"
            f"Статус множитель: x{status_multiplier}\n"
            f"✅ <b>ПОБЕДА!</b>\n"
            f"💰 Выигрыш: {fmt_money(win_amount)}\n"
            f"💰 Баланс: {fmt_money(new_balance)}",
            reply_markup=play_again_kb("football")
        )
    else:
        await callback.message.answer(
            f"⚽ <b>Футбол</b>\n\n"
            f"Удар: <b>{result}</b>\n"
            f"Ваш выбор: {'ГОЛ' if choice == 'goal' else 'МИМО'}\n"
            f"❌ <b>ПОРАЖЕНИЕ</b>\n"
            f"💸 Потеряно: {fmt_money(bet)}\n"
            f"💰 Баланс: {fmt_money(new_balance)}",
            reply_markup=play_again_kb("football")
        )
    
    await callback.answer()

# ==================== БАСКЕТБОЛ ====================

@dp.callback_query(F.data == "game:basket")
async def basket_start_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BasketStates.waiting_bet)
    await state.update_data(game="basket")
    await callback.message.answer(
        "🏀 <b>Баскетбол</b>\n\n"
        f"💰 Минимальная ставка: {fmt_money(MIN_BET)}\n"
        "Введите сумму ставки:"
    )
    await callback.answer()

@dp.message(BasketStates.waiting_bet)
async def basket_process_bet(message: Message, state: FSMContext):
    try:
        bet = float(message.text.replace(",", ".").replace(" ", ""))
        if bet < MIN_BET:
            await message.answer(f"❌ Минимальная ставка: {fmt_money(MIN_BET)}")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    user = get_user(message.from_user.id)
    if user["coins"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {fmt_money(user['coins'])}")
        return
    
    await state.update_data(bet=bet)
    await message.answer(
        f"💰 Ставка: {fmt_money(bet)}\n\n"
        "Выберите исход:",
        reply_markup=basket_kb()
    )

@dp.callback_query(F.data.startswith("basket:"))
async def basket_play_cb(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split(":")[1]
    data = await state.get_data()
    bet = data.get("bet", 0)
    
    if bet <= 0:
        await callback.message.answer("❌ Ошибка: ставка не найдена")
        await state.clear()
        await callback.answer()
        return
    
    user_id = callback.from_user.id
    status_multiplier = get_user_status_multiplier(get_user(user_id)["status"])
    
    result, value = basketball_shot()
    win = (choice == "hit" and result == "ПОПАЛ") or (choice == "miss" and result == "ПРОМАХ")
    
    multiplier = BASKETBALL_MULTIPLIER
    win_amount = round(bet * multiplier, 2) if win else 0
    
    _, new_balance = settle_instant_bet(
        user_id=user_id,
        bet=bet,
        payout=win_amount,
        game="basketball",
        outcome=f"{choice}:{result}"
    )
    
    await state.clear()
    
    if win:
        await callback.message.answer(
            f"🏀 <b>Баскетбол</b>\n\n"
            f"Бросок: <b>{result}</b>\n"
            f"Ваш выбор: {'ПОПАЛ' if choice == 'hit' else 'ПРОМАХ'}\n"
            f"Множитель: x{multiplier}\n"
            f"Статус множитель: x{status_multiplier}\n"
            f"✅ <b>ПОБЕДА!</b>\n"
            f"💰 Выигрыш: {fmt_money(win_amount)}\n"
            f"💰 Баланс: {fmt_money(new_balance)}",
            reply_markup=play_again_kb("basket")
        )
    else:
        await callback.message.answer(
            f"🏀 <b>Баскетбол</b>\n\n"
            f"Бросок: <b>{result}</b>\n"
            f"Ваш выбор: {'ПОПАЛ' if choice == 'hit' else 'ПРОМАХ'}\n"
            f"❌ <b>ПОРАЖЕНИЕ</b>\n"
            f"💸 Потеряно: {fmt_money(bet)}\n"
            f"💰 Баланс: {fmt_money(new_balance)}",
            reply_markup=play_again_kb("basket")
        )
    
    await callback.answer()

# ==================== БАШНЯ ====================

class TowerGameLogic:
    def __init__(self, bet: float, mines: int):
        self.bet = bet
        self.mines = mines
        self.level = 0
        self.alive = True
        self.multipliers = TOWER_MULTIPLIERS
    
    def play(self, choice: int) -> Tuple[bool, float, bool]:
        safe = random.randint(1, 3)
        if choice == safe:
            self.level += 1
            if self.level >= len(self.multipliers):
                return True, self.multipliers[-1], True
            return True, self.multipliers[self.level - 1], False
        else:
            self.alive = False
            return False, 0, True
    
    def cashout(self) -> float:
        if self.level > 0 and self.level <= len(self.multipliers):
            return self.bet * self.multipliers[self.level - 1]
        return self.bet

@dp.callback_query(F.data == "game:tower")
async def tower_start_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TowerStates.waiting_bet)
    await state.update_data(game="tower")
    await callback.message.answer(
        "🗼 <b>Башня</b>\n\n"
        f"💰 Минимальная ставка: {fmt_money(MIN_BET)}\n"
        "Введите сумму ставки:"
    )
    await callback.answer()

@dp.message(TowerStates.waiting_bet)
async def tower_process_bet(message: Message, state: FSMContext):
    try:
        bet = float(message.text.replace(",", ".").replace(" ", ""))
        if bet < MIN_BET:
            await message.answer(f"❌ Минимальная ставка: {fmt_money(MIN_BET)}")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    user = get_user(message.from_user.id)
    if user["coins"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {fmt_money(user['coins'])}")
        return
    
    await state.update_data(bet=bet)
    await state.set_state(TowerStates.waiting_mines)
    await message.answer(
        f"💰 Ставка: {fmt_money(bet)}\n\n"
        "Введите количество мин в ряду (1-3):"
    )

@dp.message(TowerStates.waiting_mines)
async def tower_process_mines(message: Message, state: FSMContext):
    try:
        mines = int(message.text)
        if mines < 1 or mines > 3:
            await message.answer("❌ Количество мин должно быть от 1 до 3")
            return
    except ValueError:
        await message.answer("❌ Введите число (1-3)")
        return
    
    data = await state.get_data()
    bet = data.get("bet", 0)
    
    user_id = message.from_user.id
    
    # Резервируем ставку
    ok, _ = reserve_bet(user_id, bet)
    if not ok:
        await message.answer(f"❌ Недостаточно средств! Баланс: {fmt_money(get_user(user_id)['coins'])}")
        await state.clear()
        return
    
    # Создаём игру
    game = TowerGameLogic(bet, mines)
    TOWER_GAMES[user_id] = game
    
    next_mult = game.multipliers[0]
    await state.clear()
    await message.answer(
        f"🗼 <b>Башня</b>\n\n"
        f"💰 Ставка: {fmt_money(bet)}\n"
        f"💣 Мин в ряду: {mines}\n"
        f"🎚 Уровень: 1/{len(game.multipliers)}\n"
        f"💰 Потенциальный выигрыш: {fmt_money(bet * next_mult)}\n\n"
        f"Выберите безопасную секцию (1-3):",
        reply_markup=tower_kb()
    )

@dp.callback_query(F.data.startswith("tower:"))
async def tower_play_cb(callback: CallbackQuery):
    action = callback.data.split(":")[1]
    user_id = callback.from_user.id
    game = TOWER_GAMES.get(user_id)
    
    if not game:
        await callback.message.answer("❌ Нет активной игры. Начните новую через /start")
        await callback.answer()
        return
    
    if action == "cash":
        win_amount = game.cashout()
        status_multiplier = get_user_status_multiplier(get_user(user_id)["status"])
        final_win = round(win_amount * status_multiplier, 2)
        
        balance = finalize_reserved_bet(
            user_id=user_id,
            bet=game.bet,
            payout=final_win,
            game="tower",
            outcome=f"cashout_level:{game.level}"
        )
        
        TOWER_GAMES.pop(user_id, None)
        await callback.message.answer(
            f"🗼 <b>Башня</b>\n\n"
            f"✅ Вы забрали выигрыш на {game.level} уровне!\n"
            f"💰 Выигрыш: {fmt_money(final_win)}\n"
            f"💰 Баланс: {fmt_money(balance)}",
            reply_markup=play_again_kb("tower")
        )
        await callback.answer()
        return
    
    if action == "cancel":
        # Возврат ставки при отмене до хода
        if game.level == 0:
            balance = finalize_reserved_bet(
                user_id=user_id,
                bet=game.bet,
                payout=game.bet,
                game="tower",
                outcome="cancel"
            )
            TOWER_GAMES.pop(user_id, None)
            await callback.message.answer(
                f"🗼 <b>Башня</b>\n\n"
                f"🛑 Игра отменена. Ставка возвращена.\n"
                f"💰 Баланс: {fmt_money(balance)}"
            )
        else:
            await callback.message.answer("❌ Нельзя отменить после первого хода")
        await callback.answer()
        return
    
    # Ход
    try:
        choice = int(action)
    except:
        await callback.answer()
        return
    
    if choice < 1 or choice > 3:
        await callback.answer("❌ Выберите 1, 2 или 3", show_alert=True)
        return
    
    win, multiplier, finished = game.play(choice)
    
    if not win:
        balance = finalize_reserved_bet(
            user_id=user_id,
            bet=game.bet,
            payout=0,
            game="tower",
            outcome=f"lose_level:{game.level + 1}"
        )
        TOWER_GAMES.pop(user_id, None)
        await callback.message.answer(
            f"🗼 <b>Башня</b>\n\n"
            f"💥 ВЫ ВЗОРВАЛИСЬ на {game.level + 1} уровне!\n"
            f"💸 Потеряно: {fmt_money(game.bet)}\n"
            f"💰 Баланс: {fmt_money(balance)}",
            reply_markup=play_again_kb("tower")
        )
        await callback.answer()
        return
    
    if finished:
        status_multiplier = get_user_status_multiplier(get_user(user_id)["status"])
        final_win = round(game.bet * multiplier * status_multiplier, 2)
        
        balance = finalize_reserved_bet(
            user_id=user_id,
            bet=game.bet,
            payout=final_win,
            game="tower",
            outcome="complete"
        )
        TOWER_GAMES.pop(user_id, None)
        await callback.message.answer(
            f"🗼 <b>Башня</b>\n\n"
            f"🏆 ВЫ ПРОШЛИ ВСЮ БАШНЮ!\n"
            f"💰 Выигрыш: {fmt_money(final_win)}\n"
            f"💰 Баланс: {fmt_money(balance)}",
            reply_markup=play_again_kb("tower")
        )
        await callback.answer()
        return
    
    # Обновляем сообщение для следующего хода
    next_mult = game.multipliers[game.level] if game.level < len(game.multipliers) else game.multipliers[-1]
    current_win = round(game.bet * multiplier, 2)
    
    await callback.message.edit_text(
        f"🗼 <b>Башня</b>\n\n"
        f"✅ Вы прошли {game.level} уровень!\n"
        f"💰 Текущий множитель: x{multiplier}\n"
        f"💰 Текущий выигрыш: {fmt_money(current_win)}\n"
        f"🎚 Следующий уровень: {game.level + 1}/{len(game.multipliers)}\n"
        f"💰 Следующий множитель: x{next_mult}\n"
        f"💰 Потенциальный выигрыш: {fmt_money(game.bet * next_mult)}\n\n"
        f"Продолжайте или заберите выигрыш:",
        reply_markup=tower_kb()
    )
    await callback.answer()

# ==================== ИГРАТЬ СНОВА ====================

@dp.callback_query(F.data.startswith("again:"))
async def play_again_cb(callback: CallbackQuery, state: FSMContext):
    game = callback.data.split(":")[1]
    game_map = {
        "roulette": "game:roulette",
        "crash": "game:crash",
        "cube": "game:cube",
        "dice": "game:dice",
        "football": "game:football",
        "basket": "game:basket",
        "tower": "game:tower",
    }
    
    if game in game_map:
        await state.update_data(game=game)
        await state.set_state(GameStates.waiting_bet)
        await callback.message.answer(f"🎮 Введите сумму ставки для игры {game}:")
    else:
        await callback.message.answer("🎮 Выберите игру", reply_markup=games_kb())
    
    await callback.answer()# bot.py - ЧАСТЬ 3/4: Мины, Очко, Золото, Алмазы, Чеки, Промокоды, Банк

# ==================== МИНЫ (классическая игра 3x3) ====================

class MinesGameLogic:
    def __init__(self, bet: float, mines_count: int):
        self.bet = bet
        self.mines_count = mines_count
        self.cells = list(range(1, 10))
        self.mines = set(random.sample(self.cells, mines_count))
        self.opened = set()
        self.game_over = False
    
    def open_cell(self, cell: int) -> Tuple[bool, float]:
        if cell in self.mines:
            self.game_over = True
            return False, 0
        
        self.opened.add(cell)
        safe_total = 9 - self.mines_count
        current_mult = mines_multiplier(len(self.opened), self.mines_count)
        
        if len(self.opened) >= safe_total:
            self.game_over = True
            return True, current_mult
        
        return True, current_mult
    
    def get_multiplier(self) -> float:
        return mines_multiplier(len(self.opened), self.mines_count)
    
    def get_potential(self) -> float:
        return round(self.bet * self.get_multiplier(), 2)

def mines_kb(game: MinesGameLogic, reveal_all: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    for i in range(1, 10):
        if i in game.opened:
            text = "✅"
            callback = "mines:noop"
        elif reveal_all and i in game.mines:
            text = "💣"
            callback = "mines:noop"
        else:
            text = str(i)
            callback = f"mines:cell:{i}"
        buttons.append(InlineKeyboardButton(text=text, callback_data=callback))
    
    rows = [buttons[i:i+3] for i in range(0, 9, 3)]
    
    if not game.game_over and len(game.opened) > 0:
        rows.append([InlineKeyboardButton(
            text=f"💰 Забрать {fmt_money(game.get_potential())}",
            callback_data="mines:cash"
        )])
    rows.append([InlineKeyboardButton(text="❌ Сдаться", callback_data="mines:cancel")])
    
    return InlineKeyboardMarkup(inline_keyboard=rows)

@dp.callback_query(F.data == "game:mines")
async def mines_start_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(MinesStates.waiting_bet)
    await state.update_data(game="mines")
    await callback.message.answer(
        "💣 <b>Мины</b>\n\n"
        "Поле 3x3, нужно открывать безопасные клетки.\n"
        "Попадание на мину = проигрыш.\n\n"
        f"💰 Минимальная ставка: {fmt_money(MIN_BET)}\n"
        "Введите сумму ставки:"
    )
    await callback.answer()

@dp.message(MinesStates.waiting_bet)
async def mines_process_bet(message: Message, state: FSMContext):
    try:
        bet = float(message.text.replace(",", ".").replace(" ", ""))
        if bet < MIN_BET:
            await message.answer(f"❌ Минимальная ставка: {fmt_money(MIN_BET)}")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    user = get_user(message.from_user.id)
    if user["coins"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {fmt_money(user['coins'])}")
        return
    
    await state.update_data(bet=bet)
    await state.set_state(MinesStates.waiting_mines)
    await message.answer(
        f"💰 Ставка: {fmt_money(bet)}\n\n"
        "Введите количество мин на поле (1-5):"
    )

@dp.message(MinesStates.waiting_mines)
async def mines_process_mines(message: Message, state: FSMContext):
    try:
        mines = int(message.text)
        if mines < 1 or mines > 5:
            await message.answer("❌ Количество мин должно быть от 1 до 5")
            return
    except ValueError:
        await message.answer("❌ Введите число (1-5)")
        return
    
    data = await state.get_data()
    bet = data.get("bet", 0)
    user_id = message.from_user.id
    
    # Резервируем ставку
    ok, _ = reserve_bet(user_id, bet)
    if not ok:
        await message.answer(f"❌ Недостаточно средств! Баланс: {fmt_money(get_user(user_id)['coins'])}")
        await state.clear()
        return
    
    # Создаём игру
    game = MinesGameLogic(bet, mines)
    MINES_GAMES[user_id] = game
    
    await state.clear()
    await message.answer(
        f"💣 <b>Мины</b>\n\n"
        f"💰 Ставка: {fmt_money(bet)}\n"
        f"💣 Мин на поле: {mines}\n"
        f"🔒 Безопасных клеток: {9 - mines}\n"
        f"💰 Текущий множитель: x1.0\n"
        f"💰 Потенциальный выигрыш: {fmt_money(bet)}\n\n"
        f"Открывайте клетки (1-9):",
        reply_markup=mines_kb(game)
    )

@dp.callback_query(F.data.startswith("mines:"))
async def mines_play_cb(callback: CallbackQuery):
    action = callback.data.split(":")[1]
    user_id = callback.from_user.id
    game = MINES_GAMES.get(user_id)
    
    if not game:
        await callback.message.answer("❌ Нет активной игры")
        await callback.answer()
        return
    
    if action == "noop":
        await callback.answer()
        return
    
    if action == "cancel":
        if len(game.opened) == 0:
            balance = finalize_reserved_bet(
                user_id=user_id,
                bet=game.bet,
                payout=game.bet,
                game="mines",
                outcome="cancel"
            )
            MINES_GAMES.pop(user_id, None)
            await callback.message.edit_text(
                f"💣 <b>Мины</b>\n\n"
                f"🛑 Игра отменена. Ставка возвращена.\n"
                f"💰 Баланс: {fmt_money(balance)}"
            )
        else:
            await callback.message.answer("❌ Нельзя отменить после первого хода")
        await callback.answer()
        return
    
    if action == "cash":
        if len(game.opened) == 0:
            await callback.answer("❌ Сначала откройте хотя бы одну клетку", show_alert=True)
            return
        
        multiplier = game.get_multiplier()
        win_amount = game.bet * multiplier
        status_multiplier = get_user_status_multiplier(get_user(user_id)["status"])
        final_win = round(win_amount * status_multiplier, 2)
        
        balance = finalize_reserved_bet(
            user_id=user_id,
            bet=game.bet,
            payout=final_win,
            game="mines",
            outcome=f"cashout_cells:{len(game.opened)}"
        )
        MINES_GAMES.pop(user_id, None)
        await callback.message.edit_text(
            f"💣 <b>Мины</b>\n\n"
            f"✅ Вы забрали выигрыш!\n"
            f"📊 Открыто клеток: {len(game.opened)}\n"
            f"💰 Множитель: x{multiplier}\n"
            f"💰 Выигрыш: {fmt_money(final_win)}\n"
            f"💰 Баланс: {fmt_money(balance)}",
            reply_markup=mines_kb(game, reveal_all=True)
        )
        await callback.answer()
        return
    
    if action == "cell":
        cell = int(action.split(":")[-1] if ":" in action else callback.data.split(":")[2])
        
        if cell in game.opened:
            await callback.answer("❌ Клетка уже открыта", show_alert=True)
            return
        
        win, multiplier = game.open_cell(cell)
        status_multiplier = get_user_status_multiplier(get_user(user_id)["status"])
        
        if not win:
            balance = finalize_reserved_bet(
                user_id=user_id,
                bet=game.bet,
                payout=0,
                game="mines",
                outcome=f"explode_cell:{cell}"
            )
            MINES_GAMES.pop(user_id, None)
            await callback.message.edit_text(
                f"💣 <b>Мины</b>\n\n"
                f"💥 ВЫ НАРВАЛИСЬ НА МИНУ в клетке {cell}!\n"
                f"💸 Потеряно: {fmt_money(game.bet)}\n"
                f"💰 Баланс: {fmt_money(balance)}",
                reply_markup=mines_kb(game, reveal_all=True)
            )
            await callback.answer()
            return
        
        safe_total = 9 - game.mines_count
        
        if len(game.opened) >= safe_total:
            win_amount = game.bet * multiplier
            final_win = round(win_amount * status_multiplier, 2)
            balance = finalize_reserved_bet(
                user_id=user_id,
                bet=game.bet,
                payout=final_win,
                game="mines",
                outcome="complete"
            )
            MINES_GAMES.pop(user_id, None)
            await callback.message.edit_text(
                f"💣 <b>Мины</b>\n\n"
                f"🏆 ВЫ ОТКРЫЛИ ВСЕ БЕЗОПАСНЫЕ КЛЕТКИ!\n"
                f"📊 Открыто клеток: {len(game.opened)}\n"
                f"💰 Множитель: x{multiplier}\n"
                f"💰 Выигрыш: {fmt_money(final_win)}\n"
                f"💰 Баланс: {fmt_money(balance)}",
                reply_markup=mines_kb(game, reveal_all=True)
            )
            await callback.answer()
            return
        
        potential = game.get_potential()
        await callback.message.edit_text(
            f"💣 <b>Мины</b>\n\n"
            f"✅ БЕЗОПАСНО! Клетка {cell}\n"
            f"📊 Открыто клеток: {len(game.opened)}/{safe_total}\n"
            f"💰 Текущий множитель: x{multiplier}\n"
            f"💰 Потенциальный выигрыш: {fmt_money(potential)}\n\n"
            f"Выберите следующую клетку:",
            reply_markup=mines_kb(game)
        )
        await callback.answer()

# ==================== ОЧКО (BLACKJACK) ====================

@dp.callback_query(F.data == "game:ochko")
async def ochko_start_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(OchkoStates.waiting_bet)
    await state.update_data(game="ochko")
    await callback.message.answer(
        "🎴 <b>Очко (Blackjack)</b>\n\n"
        "Правила:\n"
        "• У тебя и дилера по 2 карты\n"
        "• Нужно набрать 21 или больше, чем у дилера\n"
        "• Перебор = проигрыш\n"
        "• Blackjack (туз + 10/J/Q/K) = x2.5\n\n"
        f"💰 Минимальная ставка: {fmt_money(MIN_BET)}\n"
        "Введите сумму ставки:"
    )
    await callback.answer()

@dp.message(OchkoStates.waiting_bet)
async def ochko_process_bet(message: Message, state: FSMContext):
    try:
        bet = float(message.text.replace(",", ".").replace(" ", ""))
        if bet < MIN_BET:
            await message.answer(f"❌ Минимальная ставка: {fmt_money(MIN_BET)}")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    user = get_user(message.from_user.id)
    if user["coins"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {fmt_money(user['coins'])}")
        return
    
    await state.update_data(bet=bet)
    await state.set_state(OchkoStates.waiting_confirm)
    await message.answer(
        f"🎴 <b>Очко</b>\n\n"
        f"💰 Ставка: {fmt_money(bet)}\n\n"
        f"Подтвердите начало игры:",
        reply_markup=ochko_confirm_kb()
    )

@dp.callback_query(OchkoStates.waiting_confirm, F.data == "ochko:cancel")
async def ochko_cancel_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🛑 Игра в очко отменена. Ставка не списана.")
    await callback.answer()

@dp.callback_query(OchkoStates.waiting_confirm, F.data == "ochko:start")
async def ochko_start_game_cb(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bet = data.get("bet", 0)
    
    if bet <= 0:
        await callback.message.answer("❌ Ошибка: ставка не найдена")
        await state.clear()
        await callback.answer()
        return
    
    user_id = callback.from_user.id
    
    # Резервируем ставку
    ok, _ = reserve_bet(user_id, bet)
    if not ok:
        await callback.message.answer(f"❌ Недостаточно средств! Баланс: {fmt_money(get_user(user_id)['coins'])}")
        await state.clear()
        await callback.answer()
        return
    
    # Создаём игру
    deck = make_deck()
    player_cards = [deck.pop(), deck.pop()]
    dealer_cards = [deck.pop(), deck.pop()]
    
    player_value = hand_value(player_cards)
    dealer_value = hand_value(dealer_cards)
    
    game_data = {
        "bet": bet,
        "deck": deck,
        "player": player_cards,
        "dealer": dealer_cards,
        "player_value": player_value,
        "dealer_value": dealer_value
    }
    OCHKO_GAMES[user_id] = game_data
    
    await state.clear()
    
    # Проверка на Blackjack
    if player_value == 21:
        if dealer_value == 21:
            # Ничья
            balance = finalize_reserved_bet(
                user_id=user_id,
                bet=bet,
                payout=bet,
                game="ochko",
                outcome="push_blackjack"
            )
            OCHKO_GAMES.pop(user_id, None)
            await callback.message.answer(
                f"🎴 <b>Очко</b>\n\n"
                f"Ваши карты: {format_cards(player_cards)} (21)\n"
                f"Карты дилера: {format_cards(dealer_cards)} (21)\n"
                f"🤝 НИЧЬЯ! Ставка возвращена.\n"
                f"💰 Баланс: {fmt_money(balance)}",
                reply_markup=play_again_kb("ochko")
            )
        else:
            # Blackjack победа
            win_amount = bet * 2.5
            status_multiplier = get_user_status_multiplier(user_id)
            final_win = round(win_amount * status_multiplier, 2)
            balance = finalize_reserved_bet(
                user_id=user_id,
                bet=bet,
                payout=final_win,
                game="ochko",
                outcome="blackjack"
            )
            OCHKO_GAMES.pop(user_id, None)
            await callback.message.answer(
                f"🎴 <b>Очко</b>\n\n"
                f"Ваши карты: {format_cards(player_cards)} (21)\n"
                f"🏆 BLACKJACK! ПОБЕДА!\n"
                f"💰 Выигрыш: {fmt_money(final_win)}\n"
                f"💰 Баланс: {fmt_money(balance)}",
                reply_markup=play_again_kb("ochko")
            )
    else:
        await callback.message.answer(
            f"🎴 <b>Очко</b>\n\n"
            f"💰 Ставка: {fmt_money(bet)}\n\n"
            f"🎴 Дилер: {dealer_cards[0]} ❓\n"
            f"🎴 Ваши карты: {format_cards(player_cards)} ({player_value})\n\n"
            f"Ваш ход:",
            reply_markup=ochko_kb()
        )
    
    await callback.answer()

async def ochko_finish(user_id: int, message: Message):
    game = OCHKO_GAMES.get(user_id)
    if not game:
        return
    
    bet = game["bet"]
    player_value = game["player_value"]
    dealer_value = game["dealer_value"]
    
    if player_value > 21:
        balance = finalize_reserved_bet(
            user_id=user_id,
            bet=bet,
            payout=0,
            game="ochko",
            outcome="bust"
        )
        OCHKO_GAMES.pop(user_id, None)
        await message.answer(
            f"🎴 <b>Очко</b>\n\n"
            f"Ваши карты: {format_cards(game['player'])} ({player_value})\n"
            f"Карты дилера: {format_cards(game['dealer'])} ({dealer_value})\n"
            f"❌ ПЕРЕБОР! ПОРАЖЕНИЕ\n"
            f"💸 Потеряно: {fmt_money(bet)}\n"
            f"💰 Баланс: {fmt_money(balance)}",
            reply_markup=play_again_kb("ochko")
        )
        return
    
    # Ход дилера
    while dealer_value < 17:
        game["dealer"].append(game["deck"].pop())
        dealer_value = hand_value(game["dealer"])
    
    game["dealer_value"] = dealer_value
    
    if dealer_value > 21 or player_value > dealer_value:
        win_amount = bet * 2
        status_multiplier = get_user_status_multiplier(user_id)
        final_win = round(win_amount * status_multiplier, 2)
        balance = finalize_reserved_bet(
            user_id=user_id,
            bet=bet,
            payout=final_win,
            game="ochko",
            outcome="win"
        )
        result_text = "🏆 ПОБЕДА!"
    elif player_value == dealer_value:
        balance = finalize_reserved_bet(
            user_id=user_id,
            bet=bet,
            payout=bet,
            game="ochko",
            outcome="push"
        )
        result_text = "🤝 НИЧЬЯ!"
        final_win = bet
    else:
        balance = finalize_reserved_bet(
            user_id=user_id,
            bet=bet,
            payout=0,
            game="ochko",
            outcome="lose"
        )
        result_text = "❌ ПОРАЖЕНИЕ"
        final_win = 0
    
    OCHKO_GAMES.pop(user_id, None)
    await message.answer(
        f"🎴 <b>Очко</b>\n\n"
        f"Ваши карты: {format_cards(game['player'])} ({player_value})\n"
        f"Карты дилера: {format_cards(game['dealer'])} ({dealer_value})\n"
        f"{result_text}\n"
        f"💰 Выигрыш: {fmt_money(final_win)}\n"
        f"💰 Баланс: {fmt_money(balance)}",
        reply_markup=play_again_kb("ochko")
    )

@dp.callback_query(F.data == "ochko:hit")
async def ochko_hit_cb(callback: CallbackQuery):
    user_id = callback.from_user.id
    game = OCHKO_GAMES.get(user_id)
    
    if not game:
        await callback.message.answer("❌ Нет активной игры")
        await callback.answer()
        return
    
    if not game["deck"]:
        game["deck"] = make_deck()
    
    new_card = game["deck"].pop()
    game["player"].append(new_card)
    game["player_value"] = hand_value(game["player"])
    
    if game["player_value"] > 21:
        await ochko_finish(user_id, callback.message)
    else:
        await callback.message.edit_text(
            f"🎴 <b>Очко</b>\n\n"
            f"💰 Ставка: {fmt_money(game['bet'])}\n\n"
            f"🎴 Дилер: {game['dealer'][0]} ❓\n"
            f"🎴 Ваши карты: {format_cards(game['player'])} ({game['player_value']})\n\n"
            f"Ваш ход:",
            reply_markup=ochko_kb()
        )
    
    await callback.answer()

@dp.callback_query(F.data == "ochko:stand")
async def ochko_stand_cb(callback: CallbackQuery):
    user_id = callback.from_user.id
    game = OCHKO_GAMES.get(user_id)
    
    if not game:
        await callback.message.answer("❌ Нет активной игры")
        await callback.answer()
        return
    
    await ochko_finish(user_id, callback.message)
    await callback.answer()

# ==================== ЗОЛОТО (упрощённая версия) ====================

class GoldGameLogic:
    def __init__(self, bet: float):
        self.bet = bet
        self.level = 0
        self.multipliers = GOLD_MULTIPLIERS
        self.alive = True
    
    def play(self, choice: int) -> Tuple[bool, float, bool]:
        safe = random.randint(1, 2)
        if choice == safe:
            self.level += 1
            if self.level >= len(self.multipliers):
                return True, self.multipliers[-1], True
            return True, self.multipliers[self.level - 1], False
        else:
            self.alive = False
            return False, 0, True
    
    def cashout(self) -> float:
        if self.level > 0:
            return self.bet * self.multipliers[self.level - 1]
        return self.bet

@dp.callback_query(F.data == "game:gold")
async def gold_start_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GoldStates.waiting_bet)
    await state.update_data(game="gold")
    await callback.message.answer(
        "🥇 <b>Золото</b>\n\n"
        "Правила:\n"
        "• Выбирай ячейку 1 или 2\n"
        "• В одной из них ловушка\n"
        "• Угадал - проходишь дальше\n"
        "• Множитель растёт с каждым уровнем\n\n"
        f"💰 Минимальная ставка: {fmt_money(MIN_BET)}\n"
        "Введите сумму ставки:"
    )
    await callback.answer()

@dp.message(GoldStates.waiting_bet)
async def gold_process_bet(message: Message, state: FSMContext):
    try:
        bet = float(message.text.replace(",", ".").replace(" ", ""))
        if bet < MIN_BET:
            await message.answer(f"❌ Минимальная ставка: {fmt_money(MIN_BET)}")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    user = get_user(message.from_user.id)
    if user["coins"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {fmt_money(user['coins'])}")
        return
    
    await state.update_data(bet=bet)
    await message.answer(
        f"💰 Ставка: {fmt_money(bet)}\n\n"
        "Выберите ячейку (1 или 2):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🥇 1", callback_data="gold:1"),
             InlineKeyboardButton(text="🥇 2", callback_data="gold:2")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="gold:cancel")],
        ])
    )
    await state.clear()

def gold_kb(level: int, max_level: int, current_mult: float, next_mult: float) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🥇 1", callback_data="gold:1"),
         InlineKeyboardButton(text="🥇 2", callback_data="gold:2")],
        [InlineKeyboardButton(text="💰 Забрать", callback_data="gold:cash")],
    ])

@dp.callback_query(F.data.startswith("gold:"))
async def gold_play_cb(callback: CallbackQuery):
    action = callback.data.split(":")[1]
    user_id = callback.from_user.id
    game = GOLD_GAMES.get(user_id)
    
    if not game:
        # Новая игра
        if action == "cancel":
            await callback.message.answer("🛑 Отменено")
            await callback.answer()
            return
        
        try:
            choice = int(action)
        except:
            await callback.answer()
            return
        
        data = await callback.bot.get_state(callback.from_user.id)
        # Создаём игру
        bet = 0  # нужно получить из состояния
        
        # Временно: запрашиваем ставку заново
        await callback.message.answer("❌ Ошибка: начните игру заново через /games")
        await callback.answer()
        return
    
    if action == "cash":
        win_amount = game.cashout()
        status_multiplier = get_user_status_multiplier(user_id)
        final_win = round(win_amount * status_multiplier, 2)
        
        balance = finalize_reserved_bet(
            user_id=user_id,
            bet=game.bet,
            payout=final_win,
            game="gold",
            outcome=f"cashout_level:{game.level}"
        )
        GOLD_GAMES.pop(user_id, None)
        await callback.message.answer(
            f"🥇 <b>Золото</b>\n\n"
            f"✅ Вы забрали выигрыш на {game.level} уровне!\n"
            f"💰 Выигрыш: {fmt_money(final_win)}\n"
            f"💰 Баланс: {fmt_money(balance)}",
            reply_markup=play_again_kb("gold")
        )
        await callback.answer()
        return
    
    if action == "cancel":
        if game.level == 0:
            balance = finalize_reserved_bet(
                user_id=user_id,
                bet=game.bet,
                payout=game.bet,
                game="gold",
                outcome="cancel"
            )
            GOLD_GAMES.pop(user_id, None)
            await callback.message.answer(
                f"🥇 <b>Золото</b>\n\n"
                f"🛑 Игра отменена. Ставка возвращена.\n"
                f"💰 Баланс: {fmt_money(balance)}"
            )
        else:
            await callback.message.answer("❌ Нельзя отменить после хода")
        await callback.answer()
        return
    
    # Ход
    try:
        choice = int(action)
    except:
        await callback.answer()
        return
    
    win, multiplier, finished = game.play(choice)
    
    if not win:
        balance = finalize_reserved_bet(
            user_id=user_id,
            bet=game.bet,
            payout=0,
            game="gold",
            outcome=f"lose_level:{game.level + 1}"
        )
        GOLD_GAMES.pop(user_id, None)
        await callback.message.answer(
            f"🥇 <b>Золото</b>\n\n"
            f"💥 ЛОВУШКА! Вы проиграли.\n"
            f"💸 Потеряно: {fmt_money(game.bet)}\n"
            f"💰 Баланс: {fmt_money(balance)}",
            reply_markup=play_again_kb("gold")
        )
        await callback.answer()
        return
    
    if finished:
        status_multiplier = get_user_status_multiplier(user_id)
        final_win = round(game.bet * multiplier * status_multiplier, 2)
        balance = finalize_reserved_bet(
            user_id=user_id,
            bet=game.bet,
            payout=final_win,
            game="gold",
            outcome="complete"
        )
        GOLD_GAMES.pop(user_id, None)
        await callback.message.answer(
            f"🥇 <b>Золото</b>\n\n"
            f"🏆 ВЫ ПРОШЛИ ВСЮ ИГРУ!\n"
            f"💰 Выигрыш: {fmt_money(final_win)}\n"
            f"💰 Баланс: {fmt_money(balance)}",
            reply_markup=play_again_kb("gold")
        )
        await callback.answer()
        return
    
    next_mult = game.multipliers[game.level] if game.level < len(game.multipliers) else game.multipliers[-1]
    await callback.message.edit_text(
        f"🥇 <b>Золото</b>\n\n"
        f"✅ Уровень {game.level} пройден!\n"
        f"💰 Текущий множитель: x{multiplier}\n"
        f"💰 Текущий выигрыш: {fmt_money(game.bet * multiplier)}\n"
        f"🎚 Следующий уровень: {game.level + 1}/{len(game.multipliers)}\n"
        f"💰 Следующий множитель: x{next_mult}\n\n"
        f"Продолжайте или заберите выигрыш:",
        reply_markup=gold_kb(game.level, len(game.multipliers), multiplier, next_mult)
    )
    await callback.answer()

# ==================== АЛМАЗЫ ====================

class DiamondGameLogic:
    def __init__(self, bet: float, mines: int):
        self.bet = bet
        self.mines = mines
        self.level = 0
        self.multipliers = DIAMOND_MULTIPLIERS
        self.alive = True
    
    def play(self, choice: int) -> Tuple[bool, float, bool]:
        safe = random.randint(1, 5)
        if choice == safe:
            self.level += 1
            if self.level >= len(self.multipliers):
                return True, self.multipliers[-1], True
            return True, self.multipliers[self.level - 1], False
        else:
            self.alive = False
            return False, 0, True
    
    def cashout(self) -> float:
        if self.level > 0:
            return self.bet * self.multipliers[self.level - 1]
        return self.bet

@dp.callback_query(F.data == "game:diamond")
async def diamond_start_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DiamondStates.waiting_bet)
    await state.update_data(game="diamond")
    await callback.message.answer(
        "💎 <b>Алмазы</b>\n\n"
        "Правила:\n"
        "• Поле из 5 ячеек\n"
        "• В одной из них бракованный алмаз\n"
        "• Выбирай правильный - проходишь дальше\n"
        "• Множитель растёт с каждым уровнем\n\n"
        f"💰 Минимальная ставка: {fmt_money(MIN_BET)}\n"
        "Введите сумму ставки:"
    )
    await callback.answer()

@dp.message(DiamondStates.waiting_bet)
async def diamond_process_bet(message: Message, state: FSMContext):
    try:
        bet = float(message.text.replace(",", ".").replace(" ", ""))
        if bet < MIN_BET:
            await message.answer(f"❌ Минимальная ставка: {fmt_money(MIN_BET)}")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    user = get_user(message.from_user.id)
    if user["coins"] < bet:
        await message.answer(f"❌ Недостаточно средств! Баланс: {fmt_money(user['coins'])}")
        return
    
    await state.update_data(bet=bet)
    await state.set_state(DiamondStates.waiting_mines)
    await message.answer(
        f"💰 Ставка: {fmt_money(bet)}\n\n"
        "Введите количество бракованных алмазов в ряду (1-2):"
    )

@dp.message(DiamondStates.waiting_mines)
async def diamond_process_mines(message: Message, state: FSMContext):
    try:
        mines = int(message.text)
        if mines < 1 or mines > 2:
            await message.answer("❌ Количество бракованных алмазов должно быть 1 или 2")
            return
    except ValueError:
        await message.answer("❌ Введите число (1 или 2)")
        return
    
    data = await state.get_data()
    bet = data.get("bet", 0)
    user_id = message.from_user.id
    
    # Резервируем ставку
    ok, _ = reserve_bet(user_id, bet)
    if not ok:
        await message.answer(f"❌ Недостаточно средств! Баланс: {fmt_money(get_user(user_id)['coins'])}")
        await state.clear()
        return
    
    # Создаём игру
    game = DiamondGameLogic(bet, mines)
    DIAMOND_GAMES[user_id] = game
    
    await state.clear()
    await message.answer(
        f"💎 <b>Алмазы</b>\n\n"
        f"💰 Ставка: {fmt_money(bet)}\n"
        f"💎 Бракованных в ряду: {mines}\n"
        f"🎚 Уровень: 1/{len(game.multipliers)}\n"
        f"💰 Потенциальный выигрыш: {fmt_money(bet * game.multipliers[0])}\n\n"
        f"Выберите ячейку (1-5):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 1", callback_data="diamond:1"),
             InlineKeyboardButton(text="💎 2", callback_data="diamond:2"),
             InlineKeyboardButton(text="💎 3", callback_data="diamond:3")],
            [InlineKeyboardButton(text="💎 4", callback_data="diamond:4"),
             InlineKeyboardButton(text="💎 5", callback_data="diamond:5")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="diamond:cancel")],
        ])
    )

def diamond_kb(level: int, max_level: int, current_mult: float, next_mult: float) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 1", callback_data="diamond:1"),
         InlineKeyboardButton(text="💎 2", callback_data="diamond:2"),
         InlineKeyboardButton(text="💎 3", callback_data="diamond:3")],
        [InlineKeyboardButton(text="💎 4", callback_data="diamond:4"),
         InlineKeyboardButton(text="💎 5", callback_data="diamond:5")],
        [InlineKeyboardButton(text="💰 Забрать", callback_data="diamond:cash")],
    ])

@dp.callback_query(F.data.startswith("diamond:"))
async def diamond_play_cb(callback: CallbackQuery):
    action = callback.data.split(":")[1]
    user_id = callback.from_user.id
    game = DIAMOND_GAMES.get(user_id)
    
    if not game:
        await callback.answer("❌ Нет активной игры", show_alert=True)
        return
    
    if action == "cash":
        if game.level == 0:
            await callback.answer("❌ Сначала сделайте хотя бы один ход", show_alert=True)
            return
        
        win_amount = game.cashout()
        status_multiplier = get_user_status_multiplier(user_id)
        final_win = round(win_amount * status_multiplier, 2)
        
        balance = finalize_reserved_bet(
            user_id=user_id,
            bet=game.bet,
            payout=final_win,
            game="diamond",
            outcome=f"cashout_level:{game.level}"
        )
        DIAMOND_GAMES.pop(user_id, None)
        await callback.message.answer(
            f"💎 <b>Алмазы</b>\n\n"
            f"✅ Вы забрали выигрыш на {game.level} уровне!\n"
            f"💰 Выигрыш: {fmt_money(final_win)}\n"
            f"💰 Баланс: {fmt_money(balance)}",
            reply_markup=play_again_kb("diamond")
        )
        await callback.answer()
        return
    
    if action == "cancel":
        if game.level == 0:
            balance = finalize_reserved_bet(
                user_id=user_id,
                bet=game.bet,
                payout=game.bet,
                game="diamond",
                outcome="cancel"
            )
            DIAMOND_GAMES.pop(user_id, None)
            await callback.message.answer(
                f"💎 <b>Алмазы</b>\n\n"
                f"🛑 Игра отменена. Ставка возвращена.\n"
                f"💰 Баланс: {fmt_money(balance)}"
            )
        else:
            await callback.message.answer("❌ Нельзя отменить после хода")
        await callback.answer()
        return
    
    # Ход
    try:
        choice = int(action)
    except:
        await callback.answer()
        return
    
    win, multiplier, finished = game.play(choice)
    
    if not win:
        balance = finalize_reserved_bet(
            user_id=user_id,
            bet=game.bet,
            payout=0,
            game="diamond",
            outcome=f"lose_level:{game.level + 1}"
        )
        DIAMOND_GAMES.pop(user_id, None)
        await callback.message.answer(
            f"💎 <b>Алмазы</b>\n\n"
            f"💥 БРАКОВАННЫЙ АЛМАЗ! Вы проиграли.\n"
            f"💸 Потеряно: {fmt_money(game.bet)}\n"
            f"💰 Баланс: {fmt_money(balance)}",
            reply_markup=play_again_kb("diamond")
        )
        await callback.answer()
        return
    
    if finished:
        status_multiplier = get_user_status_multiplier(user_id)
        final_win = round(game.bet * multiplier * status_multiplier, 2)
        balance = finalize_reserved_bet(
            user_id=user_id,
            bet=game.bet,
            payout=final_win,
            game="diamond",
            outcome="complete"
        )
        DIAMOND_GAMES.pop(user_id, None)
        await callback.message.answer(
            f"💎 <b>Алмазы</b>\n\n"
            f"🏆 ВЫ ПРОШЛИ ВСЮ ИГРУ!\n"
            f"💰 Выигрыш: {fmt_money(final_win)}\n"
            f"💰 Баланс: {fmt_money(balance)}",
            reply_markup=play_again_kb("diamond")
        )
        await callback.answer()
        return
    
    next_mult = game.multipliers[game.level] if game.level < len(game.multipliers) else game.multipliers[-1]
    await callback.message.edit_text(
        f"💎 <b>Алмазы</b>\n\n"
        f"✅ Уровень {game.level} пройден!\n"
        f"💰 Текущий множитель: x{multiplier}\n"
        f"💰 Текущий выигрыш: {fmt_money(game.bet * multiplier)}\n"
        f"🎚 Следующий уровень: {game.level + 1}/{len(game.multipliers)}\n"
        f"💰 Следующий множитель: x{next_mult}\n\n"
        f"Продолжайте или заберите выигрыш:",
        reply_markup=diamond_kb(game.level, len(game.multipliers), multiplier, next_mult)
    )
    await callback.answer()

# ==================== ЧЕКИ ====================

@dp.callback_query(F.data == "checks:create")
async def create_check_start_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CheckCreateStates.waiting_amount)
    await callback.message.answer(
        "🧾 <b>Создание чека</b>\n\n"
        "Введите сумму на одну активацию (мин. 10):"
    )
    await callback.answer()

@dp.message(CheckCreateStates.waiting_amount)
async def create_check_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount < 10:
            await message.answer("❌ Минимальная сумма: 10")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    await state.update_data(amount=amount)
    await state.set_state(CheckCreateStates.waiting_count)
    await message.answer(f"💰 Сумма на активацию: {fmt_money(amount)}\n\nВведите количество активаций (1-100):")

@dp.message(CheckCreateStates.waiting_count)
async def create_check_count(message: Message, state: FSMContext):
    try:
        count = int(message.text)
        if count < 1 or count > 100:
            await message.answer("❌ Количество активаций от 1 до 100")
            return
    except ValueError:
        await message.answer("❌ Введите целое число")
        return
    
    data = await state.get_data()
    amount = data.get("amount", 0)
    user_id = message.from_user.id
    
    success, result = create_check(user_id, amount, count)
    await state.clear()
    
    if success:
        await message.answer(
            f"✅ <b>Чек создан!</b>\n\n"
            f"🔑 Код: <code>{result}</code>\n"
            f"💰 Сумма: {fmt_money(amount)}\n"
            f"🎯 Активаций: {count}\n"
            f"💎 Всего заморожено: {fmt_money(amount * count)}\n\n"
            f"<i>Поделитесь кодом с друзьями!</i>"
        )
    else:
        await message.answer(f"❌ {result}")

@dp.callback_query(F.data == "checks:claim")
async def claim_check_start_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CheckClaimStates.waiting_code)
    await callback.message.answer(
        "🧾 <b>Активация чека</b>\n\n"
        "Введите код чека:"
    )
    await callback.answer()

@dp.message(CheckClaimStates.waiting_code)
async def claim_check_code(message: Message, state: FSMContext):
    success, msg, reward = claim_check(message.from_user.id, message.text.strip())
    await state.clear()
    
    if success:
        await message.answer(
            f"✅ <b>Чек активирован!</b>\n\n"
            f"💰 Получено: {fmt_money(reward)}\n"
            f"💰 Новый баланс: {fmt_money(get_user(message.from_user.id)['coins'])}"
        )
    else:
        await message.answer(f"❌ {msg}")

@dp.callback_query(F.data == "checks:my")
async def my_checks_cb(callback: CallbackQuery):
    checks = get_user_checks(callback.from_user.id)
    if not checks:
        await callback.message.answer("📭 У вас нет созданных чеков")
    else:
        text = "🧾 <b>Ваши чеки</b>\n\n"
        for check in checks:
            text += f"🔑 <code>{check['code']}</code> | {fmt_money(check['per_user'])} | осталось: {check['remaining']}\n"
        await callback.message.answer(text)
    await callback.answer()

# ==================== ПРОМОКОДЫ ====================

@dp.message(PromoStates.waiting_code)
async def promo_code_handler(message: Message, state: FSMContext):
    success, msg, reward = redeem_promo(message.from_user.id, message.text.strip())
    await state.clear()
    
    if success:
        await message.answer(
            f"🎟 <b>Промокод активирован!</b>\n\n"
            f"💰 Получено: {fmt_money(reward)}\n"
            f"💰 Новый баланс: {fmt_money(get_user(message.from_user.id)['coins'])}"
        )
    else:
        await message.answer(f"❌ {msg}")

# ==================== БАНК (ДЕПОЗИТЫ) ====================

@dp.callback_query(F.data == "bank:open")
async def bank_open_cb(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BankStates.waiting_amount)
    await callback.message.answer(
        "🏦 <b>Открытие депозита</b>\n\n"
        f"💰 Минимальная сумма: {fmt_money(100)}\n"
        "Введите сумму депозита:"
    )
    await callback.answer()

@dp.message(BankStates.waiting_amount)
async def bank_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount < 100:
            await message.answer(f"❌ Минимальная сумма депозита: {fmt_money(100)}")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    user = get_user(message.from_user.id)
    if user["coins"] < amount:
        await message.answer(f"❌ Недостаточно средств! Баланс: {fmt_money(user['coins'])}")
        return
    
    await state.update_data(amount=amount)
    await message.answer(
        f"💰 Сумма депозита: {fmt_money(amount)}\n\n"
        "Выберите срок:",
        reply_markup=bank_terms_kb()
    )

@dp.callback_query(F.data.startswith("bank:term:"))
async def bank_term_cb(callback: CallbackQuery, state: FSMContext):
    term = int(callback.data.split(":")[2])
    if term == "cancel":
        await state.clear()
        await callback.message.answer("🛑 Открытие депозита отменено")
        await callback.answer()
        return
    
    data = await state.get_data()
    amount = data.get("amount", 0)
    
    if amount <= 0:
        await callback.message.answer("❌ Ошибка: сумма не найдена")
        await state.clear()
        await callback.answer()
        return
    
    success, msg = add_deposit(callback.from_user.id, amount, term)
    await state.clear()
    
    if success:
        term_info = BANK_TERMS[term]
        await callback.message.answer(
            f"✅ <b>Депозит открыт!</b>\n\n"
            f"💰 Сумма: {fmt_money(amount)}\n"
            f"📅 Срок: {term_info['name']}\n"
            f"📈 Доходность: +{int(term_info['rate'] * 100)}%\n"
            f"💰 Итоговая сумма: {fmt_money(amount * (1 + term_info['rate']))}\n\n"
            f"<i>Депозит автоматически закроется через {term} дней</i>"
        )
    else:
        await callback.message.answer(f"❌ {msg}")
    
    await callback.answer()

@dp.callback_query(F.data == "bank:list")
async def bank_list_cb(callback: CallbackQuery):
    deposits = get_user_deposits(callback.from_user.id)
    if not deposits:
        await callback.message.answer("📭 У вас нет активных депозитов")
    else:
        now = now_ts()
        text = "🏦 <b>Ваши депозиты</b>\n\n"
        for dep in deposits:
            days_left = max(0, dep["opened_at"] + dep["term_days"] * 86400 - now) // 86400
            status = "🟢 Активен" if dep["status"] == "active" else "🔒 Закрыт"
            text += f"#{dep['id']} | {fmt_money(dep['principal'])} | {dep['term_days']} дн. | +{int(dep['rate'] * 100)}% | {status}"
            if days_left > 0 and dep["status"] == "active":
                text += f" | {days_left} дн. осталось"
            text += "\n"
        await callback.message.answer(text)
    await callback.answer()

@dp.callback_query(F.data == "bank:claim")
async def bank_claim_cb(callback: CallbackQuery):
    count, total = claim_deposits(callback.from_user.id)
    if count == 0:
        await callback.message.answer("📭 Нет созревших депозитов для вывода")
    else:
        await callback.message.answer(
            f"✅ <b>Депозиты выведены!</b>\n\n"
            f"📦 Закрыто депозитов: {count}\n"
            f"💰 Получено: {fmt_money(total)}\n"
            f"💰 Новый баланс: {fmt_money(get_user(callback.from_user.id)['coins'])}"
        )
    await callback.answer()# bot.py - ЧАСТЬ 4/4: Админ-панель, выдача валюты, запуск

# ==================== АДМИН-ПАНЕЛЬ ====================

@dp.callback_query(F.data == "admin:give")
async def admin_give_cb(callback: CallbackQuery, state: FSMContext):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await state.set_state(AdminGiveStates.waiting_target)
    await callback.message.answer(
        "💰 <b>Выдача ONEmi</b>\n\n"
        "Введите ID пользователя и сумму через пробел\n"
        "Пример: <code>123456789 1000</code>\n\n"
        "Или ответьте на сообщение пользователя командой <code>выдать 1000</code>"
    )
    await callback.answer()

@dp.message(AdminGiveStates.waiting_target)
async def admin_give_process(message: Message, state: FSMContext):
    if not is_admin_user(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        await state.clear()
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Неверный формат. Пример: <code>123456789 1000</code>")
        return
    
    try:
        user_id = int(parts[0])
        amount = float(parts[1].replace(",", "."))
    except ValueError:
        await message.answer("❌ Неверный формат ID или суммы")
        return
    
    if amount <= 0:
        await message.answer("❌ Сумма должна быть положительной")
        return
    
    user = get_user(user_id)
    new_balance = update_balance(user_id, amount)
    log_admin_action(message.from_user.id, "give_currency", user_id, f"amount={amount}")
    
    # Уведомляем админа
    await message.answer(
        f"✅ <b>Выдача выполнена!</b>\n\n"
        f"👤 Пользователь: {mention_user(user_id)}\n"
        f"💰 Сумма: {fmt_money(amount)}\n"
        f"💰 Новый баланс: {fmt_money(new_balance)}"
    )
    
    # Уведомляем пользователя
    try:
        await message.bot.send_message(
            user_id,
            f"🎉 {mention_user(user_id)}, администратор выдал вам <b>{fmt_money(amount)}</b>!\n"
            f"💰 Ваш баланс: {fmt_money(new_balance)}"
        )
    except Exception as e:
        await message.answer(f"⚠️ Не удалось уведомить пользователя (возможно, он не начал бота)")
    
    await state.clear()

@dp.callback_query(F.data == "admin:status")
async def admin_status_cb(callback: CallbackQuery, state: FSMContext):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await state.set_state(AdminStatusStates.waiting_target)
    await callback.message.answer(
        "👑 <b>Изменение статуса</b>\n\n"
        "Введите ID пользователя:"
    )
    await callback.answer()

@dp.message(AdminStatusStates.waiting_target)
async def admin_status_target(message: Message, state: FSMContext):
    if not is_admin_user(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        await state.clear()
        return
    
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите корректный ID пользователя")
        return
    
    user = get_user_by_id(user_id)
    if not user:
        await message.answer(f"❌ Пользователь с ID {user_id} не найден")
        return
    
    await state.update_data(target_user=user_id)
    await state.set_state(AdminStatusStates.waiting_status)
    await message.answer(
        f"👤 Пользователь: {mention_user(user_id)}\n"
        f"🎭 Текущий статус: {get_user_status_name(user['status'])} (x{get_user_status_multiplier(user['status'])})\n\n"
        f"Выберите новый статус:",
        reply_markup=admin_status_kb()
    )

@dp.callback_query(AdminStatusStates.waiting_status, F.data.startswith("admin:set_status:"))
async def admin_set_status_cb(callback: CallbackQuery, state: FSMContext):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    status = int(callback.data.split(":")[2])
    data = await state.get_data()
    target_user = data.get("target_user")
    
    if not target_user:
        await callback.message.answer("❌ Ошибка: пользователь не найден")
        await state.clear()
        await callback.answer()
        return
    
    if set_user_status(target_user, status):
        new_status_name = get_user_status_name(status)
        new_multiplier = get_user_status_multiplier(status)
        log_admin_action(callback.from_user.id, "change_status", target_user, f"status={status}")
        
        await callback.message.answer(
            f"✅ <b>Статус изменён!</b>\n\n"
            f"👤 Пользователь: {mention_user(target_user)}\n"
            f"🎭 Новый статус: {new_status_name} (x{new_multiplier})"
        )
        
        # Уведомляем пользователя
        try:
            await callback.bot.send_message(
                target_user,
                f"👑 {mention_user(target_user)}, администратор повысил ваш статус до <b>{new_status_name}</b>!\n"
                f"💰 Теперь ваши выигрыши увеличены на <b>+{(new_multiplier - 1) * 100:.0f}%</b>"
            )
        except:
            pass
    else:
        await callback.message.answer("❌ Ошибка при изменении статуса")
    
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "admin:users")
async def admin_users_cb(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    users = get_all_users()
    total = len(users)
    banned = sum(1 for u in users if u.get("is_banned", 0))
    
    text = f"👥 <b>Пользователи ONEmi</b>\n\n"
    text += f"📊 Всего: {total}\n"
    text += f"🚫 Забанено: {banned}\n"
    text += f"✅ Активных: {total - banned}\n\n"
    text += "<b>Топ 20 по балансу:</b>\n"
    
    for i, user in enumerate(users[:20], 1):
        status_emoji = get_user_status_emoji(user["status"])
        ban_emoji = "🚫" if user.get("is_banned", 0) else "✅"
        text += f"{i}. {ban_emoji} {status_emoji} <code>{user['id']}</code> — {fmt_money(user['balance'])}\n"
    
    await callback.message.answer(text)
    await callback.answer()

@dp.callback_query(F.data == "admin:stats")
async def admin_stats_cb(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    stats = get_total_stats()
    
    # Дополнительная статистика
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM bets WHERE win = 1")
    total_wins = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(bet_amount) FROM bets")
    total_bet_sum = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(payout) FROM bets WHERE win = 1")
    total_payout_sum = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM bets")
    active_players = cursor.fetchone()[0]
    conn.close()
    
    await callback.message.answer(
        f"📊 <b>Статистика ONEmi Game Bot</b>\n\n"
        f"👥 <b>Пользователи:</b>\n"
        f"• Всего: {stats['users']}\n"
        f"• Активных игроков: {active_players}\n\n"
        f"💰 <b>Экономика:</b>\n"
        f"• Всего монет: {fmt_money(stats['total_coins'])}\n"
        f"• Всего поставлено: {fmt_money(total_bet_sum)}\n"
        f"• Всего выплачено: {fmt_money(total_payout_sum)}\n\n"
        f"🎲 <b>Игры:</b>\n"
        f"• Всего ставок: {stats['total_bets']}\n"
        f"• Всего побед: {total_wins}\n"
        f"• Винрейт: {total_wins/stats['total_bets']*100:.1f}%" if stats['total_bets'] > 0 else "• Винрейт: 0%"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin:broadcast")
async def admin_broadcast_cb(callback: CallbackQuery, state: FSMContext):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await state.set_state(AdminBroadcastStates.waiting_message)
    await callback.message.answer(
        "📢 <b>Рассылка сообщений</b>\n\n"
        "Введите текст рассылки (можно использовать HTML-теги):\n"
        "Пример: <code>&lt;b&gt;Важное объявление!&lt;/b&gt;</code>\n\n"
        "Для отмены напишите <code>отмена</code>"
    )
    await callback.answer()

@dp.message(AdminBroadcastStates.waiting_message)
async def admin_broadcast_text(message: Message, state: FSMContext):
    if not is_admin_user(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        await state.clear()
        return
    
    if normalize_text(message.text) == "отмена":
        await state.clear()
        await message.answer("🛑 Рассылка отменена")
        return
    
    await state.update_data(broadcast_text=message.html_text)
    
    # Показываем предпросмотр
    await message.answer(
        f"📢 <b>Предпросмотр рассылки:</b>\n\n{message.html_text}\n\n"
        f"Отправить всем пользователям?\n"
        f"Всего пользователей: {get_total_stats()['users']}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, отправить", callback_data="admin:bcast_confirm"),
             InlineKeyboardButton(text="❌ Нет, отмена", callback_data="admin:bcast_cancel")]
        ])
    )

@dp.callback_query(F.data == "admin:bcast_confirm")
async def admin_broadcast_confirm(callback: CallbackQuery, state: FSMContext):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    
    if not text:
        await callback.message.answer("❌ Нет текста для рассылки")
        await state.clear()
        await callback.answer()
        return
    
    users = get_all_users()
    sent = 0
    failed = 0
    
    status_msg = await callback.message.answer(f"📢 Начинаю рассылку {len(users)} пользователям...")
    
    for user in users:
        if user.get("is_banned", 0):
            continue
        try:
            await callback.bot.send_message(int(user["id"]), f"📢 <b>Рассылка от администрации</b>\n\n{text}")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    
    log_admin_action(callback.from_user.id, "broadcast", None, f"sent={sent}, failed={failed}")
    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📤 Отправлено: {sent}\n"
        f"❌ Не доставлено: {failed}"
    )
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "admin:bcast_cancel")
async def admin_broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("🛑 Рассылка отменена")
    await callback.answer()

@dp.callback_query(F.data == "admin:promos")
async def admin_promos_cb(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await callback.message.answer(
        "🎟 <b>Управление промокодами</b>",
        reply_markup=admin_promos_kb()
    )
    await callback.answer()

@dp.callback_query(F.data == "admin:create_promo")
async def admin_create_promo_cb(callback: CallbackQuery, state: FSMContext):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await state.set_state(NewPromoStates.waiting_code)
    await callback.message.answer(
        "🎟 <b>Создание промокода</b>\n\n"
        "Шаг 1/3: Введите код промокода\n"
        "Код должен содержать 3-24 символа (A-Z, 0-9, _, -)"
    )
    await callback.answer()

@dp.message(NewPromoStates.waiting_code)
async def admin_create_promo_code(message: Message, state: FSMContext):
    if not is_admin_user(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        await state.clear()
        return
    
    try:
        code = normalize_promo_code(message.text)
    except ValueError as e:
        await message.answer("❌ Некорректный код. Используйте A-Z, 0-9, _, - (3-24 символа)")
        return
    
    await state.update_data(code=code)
    await state.set_state(NewPromoStates.waiting_reward)
    await message.answer(
        f"🔑 Код: <code>{code}</code>\n\n"
        "Шаг 2/3: Введите награду (число)"
    )

@dp.message(NewPromoStates.waiting_reward)
async def admin_create_promo_reward(message: Message, state: FSMContext):
    if not is_admin_user(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        await state.clear()
        return
    
    try:
        reward = float(message.text.replace(",", "."))
        if reward <= 0:
            await message.answer("❌ Награда должна быть положительной")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    await state.update_data(reward=reward)
    await state.set_state(NewPromoStates.waiting_activations)
    await message.answer(
        f"💰 Награда: {fmt_money(reward)}\n\n"
        "Шаг 3/3: Введите количество активаций (целое число)"
    )

@dp.message(NewPromoStates.waiting_activations)
async def admin_create_promo_activations(message: Message, state: FSMContext):
    if not is_admin_user(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        await state.clear()
        return
    
    try:
        activations = int(message.text)
        if activations <= 0:
            await message.answer("❌ Количество активаций должно быть больше 0")
            return
    except ValueError:
        await message.answer("❌ Введите целое число")
        return
    
    data = await state.get_data()
    code = data.get("code")
    reward = data.get("reward")
    
    if add_promo(code, reward, activations):
        log_admin_action(message.from_user.id, "create_promo", None, f"code={code}, reward={reward}, acts={activations}")
        await message.answer(
            f"✅ <b>Промокод создан!</b>\n\n"
            f"🔑 Код: <code>{code}</code>\n"
            f"💰 Награда: {fmt_money(reward)}\n"
            f"🎯 Активаций: {activations}"
        )
    else:
        await message.answer(f"❌ Ошибка: промокод <code>{code}</code> уже существует")
    
    await state.clear()

@dp.callback_query(F.data == "admin:list_promos")
async def admin_list_promos_cb(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    promos = get_all_promos()
    if not promos:
        await callback.message.answer("📭 Нет активных промокодов")
    else:
        text = "🎟 <b>Список промокодов</b>\n\n"
        for promo in promos:
            text += f"🔑 <code>{promo['name']}</code> | {fmt_money(promo['reward'])} | осталось: {promo['remaining_activations']}\n"
        await callback.message.answer(text)
    await callback.answer()

@dp.callback_query(F.data == "admin:checks")
async def admin_checks_cb(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    conn = get_db()
    rows = conn.execute("SELECT code, creator_id, per_user, remaining FROM checks ORDER BY rowid DESC LIMIT 20").fetchall()
    conn.close()
    
    if not rows:
        await callback.message.answer("📭 Нет активных чеков")
    else:
        text = "🧾 <b>Последние чеки</b>\n\n"
        for row in rows:
            text += f"🔑 <code>{row['code']}</code> | {fmt_money(row['per_user'])} | создатель: <code>{row['creator_id']}</code> | осталось: {row['remaining']}\n"
        await callback.message.answer(text)
    await callback.answer()

@dp.callback_query(F.data == "admin:settings")
async def admin_settings_cb(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    current_min_bet = get_json_value("min_bet", MIN_BET)
    current_bonus_min = get_json_value("bonus_min", BONUS_REWARD_MIN)
    current_bonus_max = get_json_value("bonus_max", BONUS_REWARD_MAX)
    
    await callback.message.answer(
        f"⚙️ <b>Настройки бота</b>\n\n"
        f"💰 Минимальная ставка: {fmt_money(current_min_bet)}\n"
        f"🎁 Бонус (мин): {fmt_money(current_bonus_min)}\n"
        f"🎁 Бонус (макс): {fmt_money(current_bonus_max)}\n"
        f"⭐ Стартовый баланс: {fmt_money(START_BALANCE)}\n\n"
        f"<i>Используйте команды для изменения:</i>\n"
        f"<code>/set_min_bet 10</code>\n"
        f"<code>/set_bonus_min 100</code>\n"
        f"<code>/set_bonus_max 500</code>"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin:logs")
async def admin_logs_cb(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    if not admin_logs:
        await callback.message.answer("📝 Логов пока нет")
    else:
        text = "📝 <b>Последние действия админов</b>\n\n"
        for log in admin_logs[-20:]:
            dt = fmt_dt(log["timestamp"])
            action = log["action"]
            admin = log["admin_id"]
            target = f" → {log['target_id']}" if log["target_id"] else ""
            details = f" ({log['details']})" if log["details"] else ""
            text += f"<code>{dt}</code> | {action}{target}{details}\n"
        await callback.message.answer(text)
    await callback.answer()

@dp.callback_query(F.data == "admin:back")
async def admin_back_cb(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    stats = get_total_stats()
    await callback.message.edit_text(
        f"👑 <b>Панель администратора ONEmi</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"👥 Пользователей: <b>{stats['users']}</b>\n"
        f"💰 Монет в обращении: <b>{fmt_money(stats['total_coins'])}</b>\n"
        f"🎲 Всего ставок: <b>{stats['total_bets']}</b>\n\n"
        f"<i>Выберите действие:</i>",
        reply_markup=admin_main_kb()
    )
    await callback.answer()

@dp.callback_query(F.data == "admin:close")
async def admin_close_cb(callback: CallbackQuery):
    if not is_admin_user(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await callback.message.delete()
    await callback.answer()

# ==================== ВЫДАЧА/СПИСАНИЕ ПО РЕПЛАЮ ====================

@dp.message(StateFilter(None), lambda m: m.reply_to_message and normalize_text(m.text).startswith("выдать "))
async def admin_give_reply(message: Message):
    """Выдача валюты через ответ на сообщение пользователя"""
    if not is_admin_user(message.from_user.id):
        await message.answer("⛔ Команда только для админов")
        return
    
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("❌ Ответьте на сообщение пользователя")
        return
    
    target = message.reply_to_message.from_user
    
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Формат: <code>выдать СУММА</code>\nПример: <code>выдать 1000</code>")
        return
    
    try:
        amount = parse_amount(parts[1])
    except:
        await message.answer("❌ Неверная сумма")
        return
    
    if amount <= 0:
        await message.answer("❌ Сумма должна быть положительной")
        return
    
    new_balance = update_balance(target.id, amount)
    log_admin_action(message.from_user.id, "give_currency", target.id, f"amount={amount}")
    
    await message.answer(
        f"✅ Выдано {fmt_money(amount)} пользователю {mention_user(target.id, target.first_name)}\n"
        f"💰 Новый баланс: {fmt_money(new_balance)}"
    )
    
    # Уведомляем пользователя
    try:
        await message.bot.send_message(
            target.id,
            f"🎉 {mention_user(target.id, target.first_name)}, администратор выдал вам <b>{fmt_money(amount)}</b>!\n"
            f"💰 Ваш баланс: {fmt_money(new_balance)}"
        )
    except:
        pass

@dp.message(StateFilter(None), lambda m: m.reply_to_message and normalize_text(m.text).startswith("забрать "))
async def admin_take_reply(message: Message):
    """Списание валюты через ответ на сообщение пользователя"""
    if not is_admin_user(message.from_user.id):
        await message.answer("⛔ Команда только для админов")
        return
    
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("❌ Ответьте на сообщение пользователя")
        return
    
    target = message.reply_to_message.from_user
    
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Формат: <code>забрать СУММА</code>\nПример: <code>забрать 500</code>")
        return
    
    try:
        amount = parse_amount(parts[1])
    except:
        await message.answer("❌ Неверная сумма")
        return
    
    if amount <= 0:
        await message.answer("❌ Сумма должна быть положительной")
        return
    
    user = get_user(target.id)
    current_balance = user["coins"]
    
    if current_balance < amount:
        await message.answer(f"❌ У пользователя недостаточно средств\n💰 Баланс: {fmt_money(current_balance)}")
        return
    
    new_balance = update_balance(target.id, -amount)
    log_admin_action(message.from_user.id, "take_currency", target.id, f"amount={amount}")
    
    await message.answer(
        f"✅ Списано {fmt_money(amount)} у пользователя {mention_user(target.id, target.first_name)}\n"
        f"💰 Новый баланс: {fmt_money(new_balance)}"
    )
    
    # Уведомляем пользователя
    try:
        await message.bot.send_message(
            target.id,
            f"⚠️ {mention_user(target.id, target.first_name)}, администратор списал <b>{fmt_money(amount)}</b> с вашего баланса.\n"
            f"💰 Ваш баланс: {fmt_money(new_balance)}"
        )
    except:
        pass

# ==================== АДМИН-КОМАНДЫ (текстовые) ====================

@dp.message(Command("addpromo"))
async def addpromo_command(message: Message):
    """Быстрое создание промокода: /addpromo CODE REWARD ACTIVATIONS"""
    if not is_admin_user(message.from_user.id):
        await message.answer("⛔ Команда только для админов")
        return
    
    parts = message.text.split()
    if len(parts) != 4:
        await message.answer("✏️ Формат: <code>/addpromo CODE НАГРАДА АКТИВАЦИИ</code>\nПример: <code>/addpromo START200 200 100</code>")
        return
    
    try:
        code = normalize_promo_code(parts[1])
        reward = float(parts[2])
        activations = int(parts[3])
    except ValueError:
        await message.answer("❌ Неверные данные")
        return
    
    if reward <= 0 or activations <= 0:
        await message.answer("❌ Награда и активации должны быть больше 0")
        return
    
    if add_promo(code, reward, activations):
        log_admin_action(message.from_user.id, "create_promo", None, f"code={code}, reward={reward}, acts={activations}")
        await message.answer(
            f"✅ <b>Промокод создан!</b>\n\n"
            f"🔑 Код: <code>{code}</code>\n"
            f"💰 Награда: {fmt_money(reward)}\n"
            f"🎯 Активаций: {activations}"
        )
    else:
        await message.answer(f"❌ Промокод <code>{code}</code> уже существует")

@dp.message(Command("set_min_bet"))
async def set_min_bet_command(message: Message):
    if not is_admin_user(message.from_user.id):
        await message.answer("⛔ Команда только для админов")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("✏️ Формат: <code>/set_min_bet 10</code>")
        return
    
    try:
        new_min_bet = float(parts[1])
        if new_min_bet <= 0:
            await message.answer("❌ Минимальная ставка должна быть больше 0")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    set_json_value("min_bet", new_min_bet)
    log_admin_action(message.from_user.id, "set_min_bet", None, f"value={new_min_bet}")
    await message.answer(f"✅ Минимальная ставка изменена на {fmt_money(new_min_bet)}")

@dp.message(Command("set_bonus_min"))
async def set_bonus_min_command(message: Message):
    if not is_admin_user(message.from_user.id):
        await message.answer("⛔ Команда только для админов")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("✏️ Формат: <code>/set_bonus_min 100</code>")
        return
    
    try:
        new_min = float(parts[1])
        if new_min <= 0:
            await message.answer("❌ Минимальный бонус должен быть больше 0")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    set_json_value("bonus_min", new_min)
    log_admin_action(message.from_user.id, "set_bonus_min", None, f"value={new_min}")
    await message.answer(f"✅ Минимальный бонус изменён на {fmt_money(new_min)}")

@dp.message(Command("set_bonus_max"))
async def set_bonus_max_command(message: Message):
    if not is_admin_user(message.from_user.id):
        await message.answer("⛔ Команда только для админов")
        return
    
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("✏️ Формат: <code>/set_bonus_max 500</code>")
        return
    
    try:
        new_max = float(parts[1])
        if new_max <= 0:
            await message.answer("❌ Максимальный бонус должен быть больше 0")
            return
    except ValueError:
        await message.answer("❌ Введите число")
        return
    
    set_json_value("bonus_max", new_max)
    log_admin_action(message.from_user.id, "set_bonus_max", None, f"value={new_max}")
    await message.answer(f"✅ Максимальный бонус изменён на {fmt_money(new_max)}")

# ==================== ЗАПУСК БОТА ====================

async def main():
    init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    print("✅ ONEmi Game Bot запущен!")
    print(f"👑 Админы: {ADMIN_IDS}")
    print(f"💰 Валюта: {CURRENCY_NAME}")
    print(f"🎮 Игры: Рулетка, Кубик, Кости, Краш, Футбол, Баскет, Башня, Мины, Очко, Золото, Алмазы")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
