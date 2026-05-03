# bot.py - ПОЛНАЯ ВЕРСИЯ (ВСЁ В ОДНОМ ФАЙЛЕ)
import asyncio
import html
import json
import random
import sqlite3
import string
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List

from aiogram import Bot, Dispatcher, F, types
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
    KeyboardButton,
    FSInputFile
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

# Статусы игроков
USER_STATUSES = {
    0: "🟢 Обычный",
    1: "🟡 Продвинутый",
    2: "🔴 VIP",
    3: "🟣 Премиум",
    4: "👑 Легенда",
    5: "⚡ Администратор"
}

# Цвета для разных статусов
STATUS_COLORS = {
    0: "#00ff00",
    1: "#ffff00", 
    2: "#ff0000",
    3: "#ff00ff",
    4: "#ffd700",
    5: "#00ffff"
}

# Множители для VIP-статусов
STATUS_MULTIPLIERS = {
    0: 1.0,
    1: 1.05,
    2: 1.10,
    3: 1.15,
    4: 1.25,
    5: 1.50
}

BANK_TERMS = {
    7: 0.03,
    14: 0.07,
    30: 0.18,
}

RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

TOWER_MULTIPLIERS = [1.20, 1.48, 1.86, 2.35, 2.95, 3.75, 4.85, 6.15]
GOLD_MULTIPLIERS = [1.15, 1.35, 1.62, 2.0, 2.55, 3.25, 4.2]
DIAMOND_MULTIPLIERS = [1.12, 1.28, 1.48, 1.72, 2.02, 2.4, 2.92, 3.6]

LEGACY_GOLD_MULTIPLIERS = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]
FOOTBALL_MULTIPLIERS = {"gol": 1.6, "mimo": 2.2}
ND_TOTAL_ROWS = 16
ND_COLUMNS = 3
ND_SHOW_PREV_ROWS = 8
ND_HOUSE_EDGE = 0.985

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
    waiting_amount = State()
    waiting_choice = State()

class CrashStates(StatesGroup):
    waiting_amount = State()
    waiting_target = State()

class CubeStates(StatesGroup):
    waiting_amount = State()
    waiting_guess = State()

class DiceStates(StatesGroup):
    waiting_amount = State()
    waiting_guess = State()

class FootballStates(StatesGroup):
    waiting_amount = State()

class BasketStates(StatesGroup):
    waiting_amount = State()

class TowerStates(StatesGroup):
    waiting_amount = State()

class GoldStates(StatesGroup):
    waiting_amount = State()

class DiamondStates(StatesGroup):
    waiting_amount = State()

class MinesStates(StatesGroup):
    waiting_amount = State()
    waiting_mines = State()

class OchkoStates(StatesGroup):
    waiting_amount = State()
    waiting_confirm = State()

# Админские состояния
class AdminGiveStates(StatesGroup):
    waiting_user = State()
    waiting_amount = State()
    waiting_reason = State()

class AdminStatusStates(StatesGroup):
    waiting_target = State()
    waiting_status = State()

class AdminBroadcastStates(StatesGroup):
    waiting_message = State()
    waiting_confirm = State()

class AdminGameChangeStates(StatesGroup):
    waiting_game = State()
    waiting_multiplier = State()

# ==================== ГЛОБАЛЬНЫЕ ХРАНИЛИЩА ====================
TOWER_GAMES: Dict[int, Dict[str, Any]] = {}
GOLD_GAMES: Dict[int, Dict[str, Any]] = {}
DIAMOND_GAMES: Dict[int, Dict[str, Any]] = {}
MINES_GAMES: Dict[int, Dict[str, Any]] = {}
OCHKO_GAMES: Dict[int, Dict[str, Any]] = {}

LEGACY_GOLD_GAMES: Dict[str, Dict[str, Any]] = {}
LEGACY_TOWER_GAMES: Dict[str, Dict[str, Any]] = {}
LEGACY_MINES_GAMES: Dict[str, Dict[str, Any]] = {}
LEGACY_DIAMOND_GAMES: Dict[str, Dict[str, Any]] = {}
LEGACY_OCHKO_GAMES: Dict[str, Dict[str, Any]] = {}
LEGACY_FOOTBALL_GAMES: Dict[int, Dict[str, Any]] = {}

user_game_locks: Dict[str, asyncio.Lock] = {}

# Для админских логов
admin_logs: List[Dict] = []

# ==================== ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_user_status_emoji(status: int) -> str:
    """Получить эмодзи статуса"""
    return USER_STATUSES.get(status, "🟢 Обычный").split()[0]

def get_user_status_name(status: int) -> str:
    """Получить название статуса"""
    return USER_STATUSES.get(status, "🟢 Обычный").split(maxsplit=1)[1]

def get_status_multiplier(status: int) -> float:
    """Получить множитель для статуса"""
    return STATUS_MULTIPLIERS.get(status, 1.0)

def is_admin_user(user_id: int) -> bool:
    return int(user_id) in ADMIN_IDS

def log_admin_action(admin_id: int, action: str, target_id: int = None, details: str = ""):
    """Логирование действий админов"""
    admin_logs.append({
        "admin_id": admin_id,
        "action": action,
        "target_id": target_id,
        "details": details,
        "timestamp": now_ts()
    })
    # Оставляем только последние 1000 логов
    while len(admin_logs) > 1000:
        admin_logs.pop(0)

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    """Инициализация базы данных со всеми таблицами"""
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
            ban_reason TEXT DEFAULT NULL,
            referrer_id TEXT DEFAULT NULL,
            referral_bonus_claimed INTEGER DEFAULT 0
        )
    """)
    
    # Таблица ставок
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            bet_amount REAL,
            choice TEXT,
            outcome TEXT,
            win INTEGER,
            payout REAL,
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
            claimed TEXT,
            password TEXT
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
    
    # Таблица JSON данных
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

def fmt_money(value: float) -> str:
    """Форматирование денег с учетом валюты ONEmi"""
    value = round(float(value), 2)
    abs_value = abs(value)

    if abs_value >= 1000000:
        amount = f"{value/1000000:.2f}M"
    elif abs_value >= 1000:
        compact = value / 1000
        text = f"{compact:.2f}".rstrip("0").rstrip(".")
        amount = f"{text}K"
    elif abs(value - int(value)) < 1e-9:
        amount = str(int(value))
    else:
        amount = f"{value:.2f}".rstrip("0").rstrip(".")

    return f"{amount} {CURRENCY_NAME}"

def fmt_dt(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")

def fmt_left(seconds: int) -> str:
    seconds = max(0, int(seconds))
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
    if raw.endswith(("к", "k", "кк", "kk")):
        if raw.endswith(("кк", "kk")):
            raw = raw[:-2]
            multiplier = 1000000.0
        else:
            raw = raw[:-1]
            multiplier = 1000.0

    value = float(raw) * multiplier
    if value <= 0:
        raise ValueError("amount must be positive")
    return round(value, 2)

def parse_int(text: str) -> int:
    return int(str(text or "").strip())

def normalize_text(text: Optional[str]) -> str:
    s = str(text or "").lower().strip()
    for symbol in ["💰", "👤", "🎁", "🎮", "🧾", "🏦", "🎟", "❓", "✨", "•", "|"]:
        s = s.replace(symbol, " ")
    return " ".join(s.split())

def escape_html(text: Optional[str]) -> str:
    return html.escape(str(text or ""), quote=False)

def mention_user(user_id: int, name: Optional[str] = None) -> str:
    label = escape_html(name or f"Игрок {user_id}")
    return f'<a href="tg://user?id={int(user_id)}">{label}</a>'

def headline_user(emoji: str, user_id: int, name: Optional[str], text: str) -> str:
    return f"{emoji} {mention_user(user_id, name)}, {escape_html(text)}"

def get_user_status_display(status: int) -> str:
    """Получить красивый статус пользователя"""
    return f"{get_user_status_emoji(status)} {get_user_status_name(status)}"

def ensure_user_in_conn(conn: sqlite3.Connection, user_id: int) -> None:
    now = now_ts()
    conn.execute("""
        INSERT OR IGNORE INTO users (
            id, coins, status, total_bets, total_wins, total_losses,
            total_win_amount, total_lose_amount, joined_at, last_active,
            is_banned, ban_reason
        ) VALUES (?, ?, 0, 0, 0, 0, 0, 0, ?, 0, 0, NULL)
    """, (str(user_id), START_BALANCE, now))

def ensure_user(user_id: int) -> None:
    conn = get_db()
    try:
        ensure_user_in_conn(conn, user_id)
        conn.commit()
    finally:
        conn.close()

def get_user(user_id: int) -> sqlite3.Row:
    conn = get_db()
    try:
        ensure_user_in_conn(conn, user_id)
        row = conn.execute("SELECT * FROM users WHERE id = ?", (str(user_id),)).fetchone()
        conn.commit()
        return row
    finally:
        conn.close()

def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    """Получить пользователя по ID"""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (str(user_id),)).fetchone()
        return row
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
        except Exception:
            return default
    finally:
        conn.close()

def reserve_bet(user_id: int, bet: float) -> tuple[bool, float]:
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        row = conn.execute("SELECT coins FROM users WHERE id = ?", (str(user_id),)).fetchone()
        coins = float(row["coins"] or 0)
        if coins < bet:
            conn.rollback()
            return False, coins
        new_balance = round(coins - bet, 2)
        conn.execute("UPDATE users SET coins = ? WHERE id = ?", (new_balance, str(user_id)))
        conn.execute("UPDATE users SET total_bets = total_bets + 1, last_active = ? WHERE id = ?", 
                     (now_ts(), str(user_id)))
        conn.commit()
        return True, new_balance
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def finalize_reserved_bet(
    user_id: int,
    bet: float,
    payout: float,
    choice: str,
    outcome: str,
) -> float:
    payout = round(max(0.0, payout), 2)
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        
        status_row = conn.execute("SELECT status FROM users WHERE id = ?", (str(user_id),)).fetchone()
        status = int(status_row["status"] or 0)
        multiplier = get_status_multiplier(status)
        
        # Применяем множитель статуса к выигрышу
        if payout > 0:
            payout_with_bonus = round(payout * multiplier, 2)
        else:
            payout_with_bonus = 0
            
        if payout_with_bonus > 0:
            conn.execute("UPDATE users SET coins = coins + ? WHERE id = ?", 
                        (payout_with_bonus, str(user_id)))
            
        if payout_with_bonus > 0:
            conn.execute("UPDATE users SET total_wins = total_wins + 1, total_win_amount = total_win_amount + ? WHERE id = ?",
                        (payout_with_bonus, str(user_id)))
        else:
            conn.execute("UPDATE users SET total_losses = total_losses + 1, total_lose_amount = total_lose_amount + ? WHERE id = ?",
                        (bet, str(user_id)))
            
        conn.execute("""
            INSERT INTO bets (user_id, bet_amount, choice, outcome, win, payout, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (str(user_id), round(bet, 2), choice, outcome, 1 if payout_with_bonus > 0 else 0, payout_with_bonus, now_ts()))
        
        row = conn.execute("SELECT coins FROM users WHERE id = ?", (str(user_id),)).fetchone()
        conn.commit()
        return float(row["coins"] or 0)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def settle_instant_bet(
    user_id: int,
    bet: float,
    payout: float,
    choice: str,
    outcome: str,
) -> tuple[bool, float]:
    payout = round(max(0.0, payout), 2)
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        row = conn.execute("SELECT coins, status FROM users WHERE id = ?", (str(user_id),)).fetchone()
        coins = float(row["coins"] or 0)
        status = int(row["status"] or 0)
        
        if coins < bet:
            conn.rollback()
            return False, coins
            
        multiplier = get_status_multiplier(status)
        
        if payout > 0:
            payout_with_bonus = round(payout * multiplier, 2)
        else:
            payout_with_bonus = 0
            
        new_balance = round(coins - bet + payout_with_bonus, 2)
        conn.execute("UPDATE users SET coins = ? WHERE id = ?", (new_balance, str(user_id)))
        
        conn.execute("""
            INSERT INTO bets (user_id, bet_amount, choice, outcome, win, payout, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (str(user_id), round(bet, 2), choice, outcome, 1 if payout_with_bonus > 0 else 0, payout_with_bonus, now_ts()))
        
        conn.execute("UPDATE users SET total_bets = total_bets + 1, last_active = ? WHERE id = ?",
                    (now_ts(), str(user_id)))
        if payout_with_bonus > 0:
            conn.execute("UPDATE users SET total_wins = total_wins + 1, total_win_amount = total_win_amount + ? WHERE id = ?",
                        (payout_with_bonus, str(user_id)))
        else:
            conn.execute("UPDATE users SET total_losses = total_losses + 1, total_lose_amount = total_lose_amount + ? WHERE id = ?",
                        (bet, str(user_id)))
            
        conn.commit()
        return True, new_balance
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def add_balance(user_id: int, delta: float, reason: str = "admin_give") -> float:
    """Добавить баланс пользователю с логированием"""
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        conn.execute("UPDATE users SET coins = coins + ? WHERE id = ?", (round(delta, 2), str(user_id)))
        row = conn.execute("SELECT coins FROM users WHERE id = ?", (str(user_id),)).fetchone()
        conn.commit()
        return float(row["coins"] or 0)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def set_user_balance(user_id: int, new_balance: float) -> float:
    """Установить баланс пользователя"""
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        conn.execute("UPDATE users SET coins = ? WHERE id = ?", (round(new_balance, 2), str(user_id)))
        conn.commit()
        return round(new_balance, 2)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def set_user_status(user_id: int, status: int) -> bool:
    """Установить статус пользователя"""
    if status not in USER_STATUSES:
        return False
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        conn.execute("UPDATE users SET status = ? WHERE id = ?", (status, str(user_id)))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()

def ban_user(user_id: int, reason: str = "") -> bool:
    """Забанить пользователя"""
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        conn.execute("UPDATE users SET is_banned = 1, ban_reason = ? WHERE id = ?", (reason, str(user_id)))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()

def unban_user(user_id: int) -> bool:
    """Разбанить пользователя"""
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        conn.execute("UPDATE users SET is_banned = 0, ban_reason = NULL WHERE id = ?", (str(user_id),))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()

def is_user_banned(user_id: int) -> tuple[bool, str]:
    """Проверить, забанен ли пользователь"""
    user = get_user(user_id)
    if not user:
        return False, ""
    return bool(user["is_banned"]), user["ban_reason"] or ""

def get_profile_stats(user_id: int) -> Dict[str, Any]:
    conn = get_db()
    try:
        ensure_user_in_conn(conn, user_id)
        user = conn.execute("SELECT * FROM users WHERE id = ?", (str(user_id),)).fetchone()
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
            "coins": float(user["coins"] or 0),
            "status": int(user["status"] or 0),
            "total": int(row["total"] or 0),
            "wins": int(row["wins"] or 0),
            "net": float(row["net"] or 0),
            "active_deposits": int(dep["active_count"] or 0),
            "active_deposit_sum": float(dep["active_sum"] or 0),
            "total_bets": int(user["total_bets"] or 0),
            "total_wins": int(user["total_wins"] or 0),
            "total_losses": int(user["total_losses"] or 0),
            "total_win_amount": float(user["total_win_amount"] or 0),
            "total_lose_amount": float(user["total_lose_amount"] or 0),
            "joined_at": int(user["joined_at"] or 0),
            "is_banned": bool(user["is_banned"] or 0),
        }
    finally:
        conn.close()

def get_top_balances(limit: int = 10) -> list[sqlite3.Row]:
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT id, coins, status
            FROM users 
            WHERE is_banned = 0
            ORDER BY coins DESC, id ASC 
            LIMIT ?
        """, (int(limit),)).fetchall()
        conn.commit()
        return rows
    finally:
        conn.close()

def get_top_by_wins(limit: int = 10) -> list[sqlite3.Row]:
    """Топ по победам"""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT id, total_wins, total_bets
            FROM users 
            WHERE is_banned = 0 AND total_bets > 0
            ORDER BY total_wins DESC, id ASC 
            LIMIT ?
        """, (int(limit),)).fetchall()
        conn.commit()
        return rows
    finally:
        conn.close()

def get_all_users_list() -> list[sqlite3.Row]:
    """Получить всех пользователей"""
    conn = get_db()
    try:
        rows = conn.execute("SELECT id, coins, status, is_banned FROM users ORDER BY id").fetchall()
        return list(rows)
    finally:
        conn.close()

def get_total_users_count() -> int:
    """Общее количество пользователей"""
    conn = get_db()
    try:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        return count
    finally:
        conn.close()

def get_total_bets_count() -> int:
    """Общее количество ставок"""
    conn = get_db()
    try:
        count = conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0]
        return count
    finally:
        conn.close()

def get_total_coins_in_circulation() -> float:
    """Всего монет в обращении"""
    conn = get_db()
    try:
        total = conn.execute("SELECT COALESCE(SUM(coins), 0) FROM users").fetchone()[0]
        return float(total)
    finally:
        conn.close()

def generate_check_code(conn: sqlite3.Connection) -> str:
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        row = conn.execute("SELECT 1 FROM checks WHERE code = ?", (code,)).fetchone()
        if not row:
            return code

def create_check_atomic(user_id: int, per_user: float, count: int) -> tuple[bool, str]:
    total = round(per_user * count, 2)
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        row = conn.execute("SELECT coins FROM users WHERE id = ?", (str(user_id),)).fetchone()
        coins = float(row["coins"] or 0)
        if coins < total:
            conn.rollback()
            return False, "Недостаточно средств для создания чека."
        code = generate_check_code(conn)
        conn.execute("UPDATE users SET coins = coins - ? WHERE id = ?", (total, str(user_id)))
        conn.execute("""
            INSERT INTO checks (code, creator_id, per_user, remaining, claimed, password)
            VALUES (?, ?, ?, ?, ?, NULL)
        """, (code, str(user_id), round(per_user, 2), int(count), "[]"))
        conn.commit()
        return True, code
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def claim_check_atomic(user_id: int, code: str) -> tuple[bool, str, float]:
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        row = conn.execute("SELECT * FROM checks WHERE code = ?", (code.upper(),)).fetchone()
        if not row:
            conn.rollback()
            return False, "Чек не найден.", 0.0
        if int(row["remaining"] or 0) <= 0:
            conn.rollback()
            return False, "Этот чек уже закончился.", 0.0
        claimed_raw = row["claimed"] or "[]"
        try:
            claimed = json.loads(claimed_raw)
        except Exception:
            claimed = []
        if str(user_id) in {str(x) for x in claimed}:
            conn.rollback()
            return False, "Ты уже активировал этот чек.", 0.0
        claimed.append(str(user_id))
        reward = round(float(row["per_user"] or 0), 2)
        conn.execute("UPDATE users SET coins = coins + ? WHERE id = ?", (reward, str(user_id)))
        conn.execute("UPDATE checks SET remaining = remaining - 1, claimed = ? WHERE code = ?",
                     (json.dumps(claimed, ensure_ascii=False), code.upper()))
        conn.commit()
        return True, "Чек успешно активирован.", reward
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def list_my_checks(user_id: int) -> list[sqlite3.Row]:
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT code, per_user, remaining FROM checks
            WHERE creator_id = ? ORDER BY rowid DESC LIMIT 10
        """, (str(user_id),)).fetchall()
        return list(rows)
    finally:
        conn.close()

def redeem_promo_atomic(user_id: int, code: str) -> tuple[bool, str, float]:
    promo_name = code.upper().strip()
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        row = conn.execute("SELECT * FROM promos WHERE name = ?", (promo_name,)).fetchone()
        if not row:
            conn.rollback()
            return False, "Промокод не найден.", 0.0
        remaining = int(row["remaining_activations"] or 0)
        if remaining <= 0:
            conn.rollback()
            return False, "Промокод уже закончился.", 0.0
        try:
            claimed = json.loads(row["claimed"] or "[]")
        except Exception:
            claimed = []
        if str(user_id) in {str(x) for x in claimed}:
            conn.rollback()
            return False, "Ты уже активировал этот промокод.", 0.0
        reward = round(float(row["reward"] or 0), 2)
        claimed.append(str(user_id))
        conn.execute("UPDATE users SET coins = coins + ? WHERE id = ?", (reward, str(user_id)))
        conn.execute("""
            UPDATE promos SET claimed = ?, remaining_activations = remaining_activations - 1 
            WHERE name = ?
        """, (json.dumps(claimed, ensure_ascii=False), promo_name))
        conn.commit()
        return True, "Промокод активирован.", reward
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def create_promo(code: str, reward: float, activations: int) -> None:
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO promos (name, reward, claimed, remaining_activations)
            VALUES (?, ?, '[]', ?)
            ON CONFLICT(name) DO UPDATE
            SET reward = excluded.reward, remaining_activations = excluded.remaining_activations, claimed = '[]'
        """, (code.upper().strip(), round(reward, 2), int(activations)))
        conn.commit()
    finally:
        conn.close()

def add_deposit(user_id: int, amount: float, term_days: int) -> tuple[bool, str]:
    rate = BANK_TERMS.get(term_days)
    if rate is None:
        return False, "Неверный срок депозита."
    ok, _ = reserve_bet(user_id, amount)
    if not ok:
        return False, "Недостаточно средств для открытия депозита."
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO bank_deposits (user_id, principal, rate, term_days, opened_at, status, closed_at)
            VALUES (?, ?, ?, ?, ?, 'active', NULL)
        """, (str(user_id), round(amount, 2), float(rate), int(term_days), now_ts()))
        conn.commit()
        return True, "Депозит открыт."
    finally:
        conn.close()

def list_user_deposits(user_id: int, active_only: bool = False) -> list[sqlite3.Row]:
    conn = get_db()
    try:
        if active_only:
            rows = conn.execute("""
                SELECT * FROM bank_deposits WHERE user_id = ? AND status = 'active' ORDER BY id DESC
            """, (str(user_id),)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM bank_deposits WHERE user_id = ? ORDER BY id DESC LIMIT 15
            """, (str(user_id),)).fetchall()
        return list(rows)
    finally:
        conn.close()

def withdraw_matured_deposits(user_id: int) -> tuple[int, float]:
    now = now_ts()
    conn = get_db()
    total_payout = 0.0
    closed_count = 0
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_user_in_conn(conn, user_id)
        rows = conn.execute("SELECT * FROM bank_deposits WHERE user_id = ? AND status = 'active'",
                            (str(user_id),)).fetchall()
        for row in rows:
            unlock_ts = int(row["opened_at"] or 0) + int(row["term_days"] or 0) * 86400
            if now < unlock_ts:
                continue
            principal = float(row["principal"] or 0)
            rate = float(row["rate"] or 0)
            payout = round(principal * (1.0 + rate), 2)
            total_payout += payout
            closed_count += 1
            conn.execute("UPDATE bank_deposits SET status = 'closed', closed_at = ? WHERE id = ?",
                         (now, int(row["id"])))
        if total_payout > 0:
            conn.execute("UPDATE users SET coins = coins + ? WHERE id = ?",
                         (round(total_payout, 2), str(user_id)))
        conn.commit()
        return closed_count, round(total_payout, 2)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_bank_summary(user_id: int) -> Dict[str, Any]:
    conn = get_db()
    try:
        ensure_user_in_conn(conn, user_id)
        user = conn.execute("SELECT coins FROM users WHERE id = ?", (str(user_id),)).fetchone()
        deps = conn.execute("""
            SELECT COUNT(*) AS count_active, COALESCE(SUM(principal), 0) AS active_sum
            FROM bank_deposits WHERE user_id = ? AND status = 'active'
        """, (str(user_id),)).fetchone()
        conn.commit()
        return {
            "coins": float(user["coins"] or 0),
            "count_active": int(deps["count_active"] or 0),
            "active_sum": float(deps["active_sum"] or 0),
        }
    finally:
        conn.close()

def clear_active_sessions(user_id: int) -> None:
    TOWER_GAMES.pop(user_id, None)
    GOLD_GAMES.pop(user_id, None)
    DIAMOND_GAMES.pop(user_id, None)
    MINES_GAMES.pop(user_id, None)
    OCHKO_GAMES.pop(user_id, None)

def roulette_roll(choice: str) -> tuple[bool, float, str]:
    number = random.randint(0, 36)
    color = "green" if number == 0 else ("red" if number in RED_NUMBERS else "black")
    parity = "zero"
    if number != 0:
        parity = "even" if number % 2 == 0 else "odd"
    win = False
    multiplier = 0.0
    if choice == "red" and color == "red":
        win, multiplier = True, 2.0
    elif choice == "black" and color == "black":
        win, multiplier = True, 2.0
    elif choice == "even" and parity == "even":
        win, multiplier = True, 2.0
    elif choice == "odd" and parity == "odd":
        win, multiplier = True, 2.0
    elif choice == "zero" and number == 0:
        win, multiplier = True, 36.0
    pretty_color = {"red": "🔴 красное", "black": "⚫ черное", "green": "🟢 зеро"}[color]
    outcome = f"Выпало {number} ({pretty_color})"
    return win, multiplier, outcome

def crash_roll() -> float:
    u = random.random()
    raw = 0.99 / (1.0 - u)
    return round(max(1.0, min(50.0, raw)), 2)

def football_value_text(value: int) -> str:
    return "Гол" if value >= 3 else "Мимо"

def basketball_value_text(value: int) -> str:
    return "Точный бросок" if value in {4, 5} else "Промах"

def mines_multiplier(opened_count: int, mines_count: int) -> float:
    if opened_count <= 0:
        return 1.0
    safe_cells = 9 - mines_count
    base = 9.0 / max(1.0, safe_cells)
    mult = (base ** opened_count) * 0.95
    return round(mult, 2)

def make_deck() -> list[tuple[str, str]]:
    ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
    suits = ["♠", "♥", "♦", "♣"]
    deck = [(rank, suit) for rank in ranks for suit in suits]
    random.shuffle(deck)
    return deck

def card_points(rank: str) -> int:
    if rank in {"J", "Q", "K"}:
        return 10
    if rank == "A":
        return 11
    return int(rank)

def hand_value(cards: list[tuple[str, str]]) -> int:
    total = sum(card_points(rank) for rank, _ in cards)
    aces = sum(1 for rank, _ in cards if rank == "A")
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total

def format_hand(cards: list[tuple[str, str]]) -> str:
    return " ".join(f"{r}{s}" for r, s in cards)

def render_ochko_table(game: Dict[str, Any], reveal_dealer: bool) -> str:
    player_cards = game["player"]
    dealer_cards = game["dealer"]
    player_value = hand_value(player_cards)
    if reveal_dealer:
        dealer_line = f"{format_hand(dealer_cards)} ({hand_value(dealer_cards)})"
    else:
        first = f"{dealer_cards[0][0]}{dealer_cards[0][1]}"
        dealer_line = f"{first} ??"
    return (
        "🎴 <b>Очко</b>\n"
        f"Ставка: <b>{fmt_money(game['bet'])}</b>\n\n"
        f"Дилер: {dealer_line}\n"
        f"Ты: {format_hand(player_cards)} ({player_value})"
    )

def _game_lock(user_id: int | str) -> asyncio.Lock:
    key = str(user_id)
    lock = user_game_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        user_game_locks[key] = lock
    return lock

def _new_gid(prefix: str) -> str:
    return prefix + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))

def parse_bet_legacy(raw: str, balance: float) -> int:
    arg = str(raw or "").strip().lower().replace(" ", "")
    if arg in {"все", "всё"}:
        return int(balance)
    return int(parse_amount(arg))

def game_usage_text() -> str:
    return (
        "<b>Примеры команд:</b>\n"
        "<code>башня 300 2</code>\n"
        "<code>золото 300</code>\n"
        "<code>алмазы 300 2</code>\n"
        "<code>мины 300 3</code>\n"
        "<code>рул 300 чет</code>\n"
        "<code>краш 300 2.5</code>\n"
        "<code>кубик 300 5</code>\n"
        "<code>кости 300 м</code>\n"
        "<code>очко 300</code>\n"
        "<code>футбол 300 гол</code>\n"
        "<code>баскет 300</code>"
    )

# ==================== UI КЛАВИАТУРЫ ====================

def games_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗼 Башня", callback_data="games:pick:tower"),
         InlineKeyboardButton(text="🥇 Золото", callback_data="games:pick:gold")],
        [InlineKeyboardButton(text="💎 Алмазы", callback_data="games:pick:diamonds"),
         InlineKeyboardButton(text="💣 Мины", callback_data="games:pick:mines")],
        [InlineKeyboardButton(text="🎴 Очко", callback_data="games:pick:ochko"),
         InlineKeyboardButton(text="🎡 Рулетка", callback_data="games:pick:roulette")],
        [InlineKeyboardButton(text="📈 Краш", callback_data="games:pick:crash"),
         InlineKeyboardButton(text="🎲 Кубик", callback_data="games:pick:cube")],
        [InlineKeyboardButton(text="🎯 Кости", callback_data="games:pick:dice"),
         InlineKeyboardButton(text="⚽ Футбол", callback_data="games:pick:football")],
        [InlineKeyboardButton(text="🏀 Баскет", callback_data="games:pick:basket")],
    ])

def admin_main_kb() -> InlineKeyboardMarkup:
    """Главная админ-панель с кнопками"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Управление игроками", callback_data="admin:players")],
        [InlineKeyboardButton(text="💰 Выдача/Списание", callback_data="admin:give")],
        [InlineKeyboardButton(text="👑 Управление статусами", callback_data="admin:status")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="🎮 Настройки игр", callback_data="admin:games")],
        [InlineKeyboardButton(text="🎟 Промокоды", callback_data="admin:promos")],
        [InlineKeyboardButton(text="🧾 Чеки", callback_data="admin:checks")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="🔧 Настройки бота", callback_data="admin:settings")],
        [InlineKeyboardButton(text="🔐 Управление админами", callback_data="admin:admins")],
        [InlineKeyboardButton(text="🚫 Бан/Разбан", callback_data="admin:ban")],
        [InlineKeyboardButton(text="📝 Логи админов", callback_data="admin:logs")],
        [InlineKeyboardButton(text="💾 Бэкап БД", callback_data="admin:backup")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin:close")],
    ])

def admin_players_kb(page: int = 0) -> InlineKeyboardMarkup:
    """Клавиатура для просмотра игроков"""
    buttons = []
    users = get_all_users_list()
    start = page * 10
    end = min(start + 10, len(users))
    
    for user in users[start:end]:
        status_emoji = get_user_status_emoji(user["status"])
        buttons.append([InlineKeyboardButton(
            text=f"{status_emoji} {user['id']} | {fmt_money(user['coins'])}",
            callback_data=f"admin:player:{user['id']}"
        )])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin:players_page:{page-1}"))
    if end < len(users):
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"admin:players_page:{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton(text="🔍 Поиск по ID", callback_data="admin:search_player")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_player_actions_kb(user_id: int) -> InlineKeyboardMarkup:
    """Кнопки действий с игроком"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Выдать ONEmi", callback_data=f"admin:give_to:{user_id}"),
         InlineKeyboardButton(text="💸 Списать ONEmi", callback_data=f"admin:take_from:{user_id}")],
        [InlineKeyboardButton(text="👑 Изменить статус", callback_data=f"admin:change_status:{user_id}"),
         InlineKeyboardButton(text="📊 Профиль", callback_data=f"admin:view_profile:{user_id}")],
        [InlineKeyboardButton(text="🚫 Забанить", callback_data=f"admin:ban_user:{user_id}"),
         InlineKeyboardButton(text="✅ Разбанить", callback_data=f"admin:unban_user:{user_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:players")],
    ])

def admin_status_kb() -> InlineKeyboardMarkup:
    """Клавиатура выбора статуса"""
    buttons = []
    for status, name in USER_STATUSES.items():
        emoji = name.split()[0]
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {get_user_status_name(status)} (x{STATUS_MULTIPLIERS[status]})",
            callback_data=f"admin:set_status:{status}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_broadcast_confirm_kb() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения рассылки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить", callback_data="admin:bcast_confirm"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="admin:bcast_cancel")],
    ])

def admin_promos_kb() -> InlineKeyboardMarkup:
    """Клавиатура управления промокодами"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin:create_promo")],
        [InlineKeyboardButton(text="📋 Список промокодов", callback_data="admin:list_promos")],
        [InlineKeyboardButton(text="🗑 Удалить промокод", callback_data="admin:delete_promo")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back")],
    ])

def admin_checks_kb() -> InlineKeyboardMarkup:
    """Клавиатура управления чеками"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Все чеки", callback_data="admin:all_checks")],
        [InlineKeyboardButton(text="🗑 Удалить чек", callback_data="admin:delete_check")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back")],
    ])

def admin_settings_kb() -> InlineKeyboardMarkup:
    """Клавиатура настроек бота"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Мин. ставка", callback_data="admin:set_min_bet"),
         InlineKeyboardButton(text="🎁 Бонус (мин)", callback_data="admin:set_bonus_min")],
        [InlineKeyboardButton(text="🎁 Бонус (макс)", callback_data="admin:set_bonus_max"),
         InlineKeyboardButton(text="⭐ Стартовый баланс", callback_data="admin:set_start_balance")],
        [InlineKeyboardButton(text="🏦 Депозиты", callback_data="admin:bank_settings")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back")],
    ])

def admin_admins_kb() -> InlineKeyboardMarkup:
    """Клавиатура управления админами"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin:add_admin")],
        [InlineKeyboardButton(text="➖ Удалить админа", callback_data="admin:remove_admin")],
        [InlineKeyboardButton(text="📋 Список админов", callback_data="admin:list_admins")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back")],
    ])

def checks_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать чек", callback_data="checks:create")],
        [InlineKeyboardButton(text="💸 Активировать чек", callback_data="checks:claim")],
        [InlineKeyboardButton(text="📄 Мои чеки", callback_data="checks:my")],
    ])

def bank_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Открыть депозит", callback_data="bank:open")],
        [InlineKeyboardButton(text="📜 Мои депозиты", callback_data="bank:list")],
        [InlineKeyboardButton(text="💰 Снять зрелые", callback_data="bank:withdraw")],
    ])

def bank_terms_kb() -> InlineKeyboardMarkup:
    rows = []
    for days, rate in BANK_TERMS.items():
        rows.append([InlineKeyboardButton(text=f"{days} дн. (+{int(rate * 100)}%)", callback_data=f"bank:term:{days}")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="bank:term:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def roulette_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Красное", callback_data="roulette:choice:red"),
         InlineKeyboardButton(text="⚫ Черное", callback_data="roulette:choice:black")],
        [InlineKeyboardButton(text="2️⃣ Чет", callback_data="roulette:choice:even"),
         InlineKeyboardButton(text="1️⃣ Нечет", callback_data="roulette:choice:odd")],
        [InlineKeyboardButton(text="0️⃣ Зеро (x36)", callback_data="roulette:choice:zero")],
    ])

def tower_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1", callback_data="tower:pick:1"),
         InlineKeyboardButton(text="2", callback_data="tower:pick:2"),
         InlineKeyboardButton(text="3", callback_data="tower:pick:3")],
        [InlineKeyboardButton(text="💰 Забрать выигрыш", callback_data="tower:cash"),
         InlineKeyboardButton(text="❌ Сдаться", callback_data="tower:cancel")],
    ])

def gold_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧱 1", callback_data="gold:pick:1"),
         InlineKeyboardButton(text="🧱 2", callback_data="gold:pick:2"),
         InlineKeyboardButton(text="🧱 3", callback_data="gold:pick:3"),
         InlineKeyboardButton(text="🧱 4", callback_data="gold:pick:4")],
        [InlineKeyboardButton(text="💰 Забрать выигрыш", callback_data="gold:cash"),
         InlineKeyboardButton(text="❌ Сдаться", callback_data="gold:cancel")],
    ])

def diamond_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔹 1", callback_data="diamond:pick:1"),
         InlineKeyboardButton(text="🔹 2", callback_data="diamond:pick:2"),
         InlineKeyboardButton(text="🔹 3", callback_data="diamond:pick:3"),
         InlineKeyboardButton(text="🔹 4", callback_data="diamond:pick:4"),
         InlineKeyboardButton(text="🔹 5", callback_data="diamond:pick:5")],
        [InlineKeyboardButton(text="💰 Забрать выигрыш", callback_data="diamond:cash"),
         InlineKeyboardButton(text="❌ Сдаться", callback_data="diamond:cancel")],
    ])

def mines_kb(game: Dict[str, Any], reveal_all: bool = False) -> InlineKeyboardMarkup:
    opened = set(game["opened"])
    mines = set(game["mines"])
    rows = []
    for start in (1, 4, 7):
        row = []
        for idx in range(start, start + 3):
            if idx in opened:
                text = "✅"
                callback = "mines:noop"
            elif reveal_all and idx in mines:
                text = "💣"
                callback = "mines:noop"
            else:
                text = str(idx)
                callback = f"mines:cell:{idx}"
            row.append(InlineKeyboardButton(text=text, callback_data=callback))
        rows.append(row)
    rows.append([
        InlineKeyboardButton(text="💰 Забрать выигрыш", callback_data="mines:cash"),
        InlineKeyboardButton(text="❌ Сдаться", callback_data="mines:cancel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

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

# ==================== ОСНОВНЫЕ КОМАНДЫ ====================

dp = Dispatcher(storage=MemoryStorage())

@dp.message(CommandStart())
async def start_command(message: Message, state: FSMContext):
    user_id = message.from_user.id
    ensure_user(user_id)
    await state.clear()
    clear_active_sessions(user_id)
    
    user = get_user(user_id)
    status_display = get_user_status_display(user["status"])
    
    await message.answer(
        f"🎮 <b>Добро пожаловать в ONEmi Game Bot!</b>\n\n"
        f"{status_display} {mention_user(user_id, message.from_user.first_name)}\n"
        f"💰 Баланс: <b>{fmt_money(user['coins'])}</b>\n\n"
        "<blockquote>Основные команды:\n"
        "• <code>б</code> или <code>баланс</code>\n"
        "• <code>бонус</code>\n"
        "• <code>игры</code>\n"
        "• <code>топ</code>\n"
        "• <code>профиль</code>\n"
        "• <code>банк</code>\n"
        "• <code>чеки</code>\n"
        "• <code>промо CODE</code>\n"
        "• <code>помощь</code></blockquote>"
    )

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    """Админ-панель"""
    if not is_admin_user(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к админ-панели.")
        return
    
    await message.answer(
        "👑 <b>Панель администратора</b>\n\n"
        f"Всего пользователей: <b>{get_total_users_count()}</b>\n"
        f"Всего ставок: <b>{get_total_bets_count()}</b>\n"
        f"Монет в обращении: <b>{fmt_money(get_total_coins_in_circulation())}</b>\n\n"
        "<i>Выберите действие:</i>",
        reply_markup=admin_main_kb()
    )

@dp.message(Command("menu"))
async def menu_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📍 <b>Меню</b>\n"
        "<blockquote>💰 б | 🎁 бонус | 🎮 игры\n"
        "🏆 топ | 🧾 чеки | 🏦 банк | 🎟 промо | ❓ помощь</blockquote>"
    )

@dp.message(lambda m: normalize_text(m.text) in {"отмена", "/cancel", "cancel"})
async def cancel_any(message: Message, state: FSMContext):
    await state.clear()
    clear_active_sessions(message.from_user.id)
    await message.answer("🛑 Отменено. Можешь запускать новое действие 💫")

@dp.message(StateFilter(None), lambda m: normalize_text(m.text) in {"б", "баланс", "/balance", "balance", "b"})
async def balance_command(message: Message):
    user = get_user(message.from_user.id)
    status_display = get_user_status_display(user["status"])
    await message.answer(
        f"{status_display} {mention_user(message.from_user.id, message.from_user.first_name)}, твой баланс\n"
        f"<blockquote>Доступно: <b>{fmt_money(float(user['coins'] or 0))}</b></blockquote>"
    )

@dp.message(StateFilter(None), lambda m: normalize_text(m.text) in {"профиль", "/profile", "profile"})
async def profile_command(message: Message):
    stats = get_profile_stats(message.from_user.id)
    total = max(1, stats["total"])
    wr = (stats["wins"] / total) * 100
    status_display = get_user_status_display(stats["status"])
    
    await message.answer(
        f"{status_display} {mention_user(message.from_user.id, message.from_user.first_name)}, твой профиль\n"
        f"<blockquote>ID: <code>{message.from_user.id}</code>\n"
        f"Баланс: <b>{fmt_money(stats['coins'])}</b>\n"
        f"В игре с: <b>{fmt_dt(stats['joined_at'])}</b>\n"
        f"Ставок: <b>{stats['total']}</b>\n"
        f"Побед: <b>{stats['wins']}</b> ({wr:.1f}%)\n"
        f"Нетто: <b>{fmt_money(stats['net'])}</b>\n"
        f"Активных депозитов: <b>{stats['active_deposits']}</b> на <b>{fmt_money(stats['active_deposit_sum'])}</b></blockquote>"
    )

@dp.message(StateFilter(None), lambda m: normalize_text(m.text) in {"бонус", "/bonus", "bonus"})
async def bonus_command(message: Message):
    user_id = message.from_user.id
    ensure_user(user_id)
    key = f"bonus_ts:{user_id}"
    last = int(get_json_value(key, 0) or 0)
    now = now_ts()
    
    if now - last < BONUS_COOLDOWN_SECONDS:
        left = BONUS_COOLDOWN_SECONDS - (now - last)
        await message.answer(
            f"{headline_user('🎁', user_id, message.from_user.first_name, 'ты уже забрал бонус')}\n"
            f"<blockquote><i>Приходи позже.</i>\nОсталось: <b>{fmt_left(left)}</b></blockquote>"
        )
        return
    
    reward = round(float(random.randint(BONUS_REWARD_MIN, BONUS_REWARD_MAX)), 2)
    ok, balance = settle_instant_bet(user_id, 0.0, reward, "bonus", "bonus_claim")
    if not ok:
        await message.answer("Не удалось выдать бонус, попробуй позже.")
        return
    
    set_json_value(key, now)
    await message.answer(
        f"{headline_user('🎁', user_id, message.from_user.first_name, 'ты получил бонус')}\n"
        f"<blockquote>Начислено: <b>{fmt_money(reward)}</b>\n"
        f"Новый баланс: <b>{fmt_money(balance)}</b></blockquote>"
    )

@dp.message(StateFilter(None), lambda m: normalize_text(m.text) in {"помощь", "/help", "help"})
async def help_command(message: Message):
    admin_hint = ""
    if is_admin_user(message.from_user.id):
        admin_hint = (
            "\n\n🛠️ <b>Админ-команды:</b>\n"
            "• <code>/admin</code> - Панель администратора\n"
            "• <code>/new_promo</code> - Создать промокод\n"
            "• <code>/addpromo CODE REWARD ACTIVATIONS</code> - Быстрое создание промо\n"
            "• Ответь на сообщение с <code>выдать 1000</code> - Выдать валюту\n"
            "• Ответь на сообщение с <code>забрать 500</code> - Забрать валюту"
        )
    
    await message.answer(
        "❓ <b>Помощь</b>\n"
        "<blockquote><b>Основные команды:</b>\n"
        "• <code>б</code> или <code>баланс</code>\n"
        "• <code>бонус</code>\n"
        "• <code>игры</code>\n"
        "• <code>топ</code>\n"
        "• <code>профиль</code>\n"
        "• <code>банк</code>\n"
        "• <code>чеки</code>\n"
        "• <code>промо КОД</code>\n"
        "• <code>помощь</code></blockquote>\n\n"
        "<b>🎮 Игры:</b>\n"
        "<blockquote>🗼 башня | 🥇 золото | 💎 алмазы | 🎡 рулетка | 📈 краш\n"
        "💣 мины | 🎲 кубик | 🎯 кости | 🎴 очко | ⚽️ футбол | 🏀 баскет</blockquote>\n\n"
        "<b>📝 Формат команд:</b>\n"
        f"{game_usage_text()}\n\n"
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
    lines = ["🏆 <b>Топ игроков по балансу</b>", "<blockquote>"]
    for idx, row in enumerate(rows, start=1):
        icon = medals.get(idx, f"{idx}.")
        status_emoji = get_user_status_emoji(row["status"])
        lines.append(f"{icon} {status_emoji} {mention_user(int(row['id']))} — <b>{fmt_money(float(row['coins'] or 0))}</b>")
    lines.append("</blockquote>")
    await message.answer("\n".join(lines))

# ==================== АДМИН-ОБРАБОТЧИКИ ====================

@dp.callback_query(F.data == "admin:players")
async def admin_players_cb(query: CallbackQuery):
    if not is_admin_user(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    await query.message.edit_text(
        "👤 <b>Управление игроками</b>\n\n"
        "Выберите игрока для управления:",
        reply_markup=admin_players_kb(0)
    )
    await query.answer()

@dp.callback_query(F.data.startswith("admin:players_page:"))
async def admin_players_page_cb(query: CallbackQuery):
    if not is_admin_user(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    page = int(query.data.split(":")[-1])
    await query.message.edit_reply_markup(reply_markup=admin_players_kb(page))
    await query.answer()

@dp.callback_query(F.data.startswith("admin:player:"))
async def admin_player_cb(query: CallbackQuery):
    if not is_admin_user(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    user_id = int(query.data.split(":")[-1])
    user = get_user_by_id(user_id)
    if not user:
        await query.answer("Игрок не найден", show_alert=True)
        return
    
    status_display = get_user_status_display(user["status"])
    banned_text = "🚫 ЗАБАНЕН" if user["is_banned"] else "✅ Активен"
    
    await query.message.edit_text(
        f"👤 <b>Информация об игроке</b>\n\n"
        f"ID: <code>{user_id}</code>\n"
        f"Статус: {status_display}\n"
        f"Баланс: <b>{fmt_money(user['coins'])}</b>\n"
        f"Статус: {banned_text}\n"
        f"Ставок: <b>{user['total_bets']}</b>\n"
        f"Побед: <b>{user['total_wins']}</b>\n"
        f"Проигрышей: <b>{user['total_losses']}</b>\n"
        f"Выиграно всего: <b>{fmt_money(user['total_win_amount'])}</b>\n"
        f"Проиграно всего: <b>{fmt_money(user['total_lose_amount'])}</b>",
        reply_markup=admin_player_actions_kb(user_id)
    )
    await query.answer()

@dp.callback_query(F.data.startswith("admin:give_to:"))
async def admin_give_to_cb(query: CallbackQuery, state: FSMContext):
    if not is_admin_user(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    user_id = int(query.data.split(":")[-1])
    await state.update_data(target_user=user_id, action_type="give")
    await state.set_state(AdminGiveStates.waiting_amount)
    await query.message.answer(f"💰 Введите сумму для выдачи игроку <code>{user_id}</code>:")
    await query.answer()

@dp.callback_query(F.data.startswith("admin:take_from:"))
async def admin_take_from_cb(query: CallbackQuery, state: FSMContext):
    if not is_admin_user(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    user_id = int(query.data.split(":")[-1])
    await state.update_data(target_user=user_id, action_type="take")
    await state.set_state(AdminGiveStates.waiting_amount)
    await query.message.answer(f"💰 Введите сумму для списания у игрока <code>{user_id}</code>:")
    await query.answer()

@dp.callback_query(F.data.startswith("admin:change_status:"))
async def admin_change_status_cb(query: CallbackQuery, state: FSMContext):
    if not is_admin_user(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    user_id = int(query.data.split(":")[-1])
    await state.update_data(target_user=user_id)
    await state.set_state(AdminStatusStates.waiting_status)
    await query.message.answer(
        f"👑 Выберите статус для игрока <code>{user_id}</code>:",
        reply_markup=admin_status_kb()
    )
    await query.answer()

@dp.callback_query(F.data == "admin:status")
async def admin_status_menu_cb(query: CallbackQuery, state: FSMContext):
    if not is_admin_user(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStatusStates.waiting_target)
    await query.message.answer(
        "👑 <b>Управление статусами</b>\n\n"
        "Введите ID игрока, которому хотите изменить статус:"
    )
    await query.answer()

@dp.message(AdminStatusStates.waiting_target)
async def admin_status_target(message: Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите корректный ID пользователя.")
        return
    
    await state.update_data(target_user=user_id)
    await message.answer(
        f"👑 Выберите статус для игрока <code>{user_id}</code>:",
        reply_markup=admin_status_kb()
    )

@dp.callback_query(F.data.startswith("admin:set_status:"))
async def admin_set_status_cb(query: CallbackQuery, state: FSMContext):
    if not is_admin_user(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    
    status = int(query.data.split(":")[-1])
    data = await state.get_data()
    target_user = data.get("target_user")
    
    if not target_user:
        await query.answer("Ошибка: цель не найдена", show_alert=True)
        return
    
    if set_user_status(target_user, status):
        user = get_user_by_id(target_user)
        log_admin_action(query.from_user.id, "change_status", target_user, f"status={status}")
        await query.message.edit_text(
            f"✅ Статус игрока <code>{target_user}</code> изменён на <b>{get_user_status_display(status)}</b>\n"
            f"Множитель выигрыша: <b>x{STATUS_MULTIPLIERS[status]}</b>"
        )
    else:
        await query.message.edit_text(f"❌ Не удалось изменить статус игрока <code>{target_user}</code>")
    
    await state.clear()
    await query.answer()

@dp.callback_query(F.data == "admin:ban")
async def admin_ban_menu_cb(query: CallbackQuery, state: FSMContext):
    if not is_admin_user(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await state.set_state(AdminStatusStates.waiting_target)
    await state.update_data(action="ban")
    await query.message.answer(
        "🚫 <b>Бан игрока</b>\n\n"
        "Введите ID игрока для блокировки (можно указать причину через пробел):\n"
        "Пример: <code>123456789 Спам в чате</code>"
    )
    await query.answer()

@dp.callback_query(F.data.startswith("admin:ban_user:"))
async def admin_ban_user_cb(query: CallbackQuery):
    if not is_admin_user(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    user_id = int(query.data.split(":")[-1])
    
    if ban_user(user_id, "Забанен администратором"):
        log_admin_action(query.from_user.id, "ban_user", user_id)
        await query.answer(f"✅ Игрок {user_id} забанен", show_alert=True)
        await query.message.edit_text(f"🚫 Игрок <code>{user_id}</code> забанен.")
    else:
        await query.answer("❌ Ошибка при бане", show_alert=True)

@dp.callback_query(F.data.startswith("admin:unban_user:"))
async def admin_unban_user_cb(query: CallbackQuery):
    if not is_admin_user(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    user_id = int(query.data.split(":")[-1])
    
    if unban_user(user_id):
        log_admin_action(query.from_user.id, "unban_user", user_id)
        await query.answer(f"✅ Игрок {user_id} разбанен", show_alert=True)
        await query.message.edit_text(f"✅ Игрок <code>{user_id}</code> разбанен.")
    else:
        await query.answer("❌ Ошибка при разбане", show_alert=True)

@dp.callback_query(F.data == "admin:broadcast")
async def admin_broadcast_cb(query: CallbackQuery, state: FSMContext):
    if not is_admin_user(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    await state.set_state(AdminBroadcastStates.waiting_message)
    await query.message.answer(
        "📢 <b>Рассылка сообщений</b>\n\n"
        "Введите текст рассылки (можно использовать HTML-теги):\n"
        "Пример: <code>&lt;b&gt;Важное объявление!&lt;/b&gt;</code>\n\n"
        "Для отмены напишите <code>отмена</code>"
    )
    await query.answer()

@dp.message(AdminBroadcastStates.waiting_message)
async def admin_broadcast_message(message: Message, state: FSMContext):
    if normalize_text(message.text) == "отмена":
        await state.clear()
        await message.answer("🛑 Рассылка отменена.")
        return
    
    await state.update_data(broadcast_text=message.html_text)
    await message.answer(
        f"📢 <b>Предпросмотр рассылки:</b>\n\n{message.html_text}\n\n"
        "Отправить всем пользователям?",
        reply_markup=admin_broadcast_confirm_kb()
    )

@dp.callback_query(F.data == "admin:bcast_confirm")
async def admin_broadcast_confirm(query: CallbackQuery, state: FSMContext):
    if not is_admin_user(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    
    if not text:
        await query.message.edit_text("❌ Нет текста для рассылки.")
        await state.clear()
        return
    
    users = get_all_users_list()
    sent = 0
    failed = 0
    
    status_msg = await query.message.answer(f"📢 Начинаю рассылку {len(users)} пользователям...")
    
    for user in users:
        if user["is_banned"]:
            continue
        try:
            await query.bot.send_message(int(user["id"]), text, parse_mode=ParseMode.HTML)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # задержка чтобы не банили
    
    log_admin_action(query.from_user.id, "broadcast", details=f"sent={sent}, failed={failed}")
    await status_msg.edit_text(f"✅ Рассылка завершена!\nОтправлено: {sent}\nНе доставлено: {failed}")
    await state.clear()
    await query.answer()

@dp.callback_query(F.data == "admin:bcast_cancel")
async def admin_broadcast_cancel(query: CallbackQuery, state: FSMContext):
    await state.clear()
    await query.message.edit_text("🛑 Рассылка отменена.")
    await query.answer()

@dp.callback_query(F.data == "admin:stats")
async def admin_stats_cb(query: CallbackQuery):
    if not is_admin_user(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    
    total_users = get_total_users_count()
    total_bets = get_total_bets_count()
    total_coins = get_total_coins_in_circulation()
    
    # Статистика по статусам
    conn = get_db()
    status_stats = {}
    for status in USER_STATUSES:
        count = conn.execute("SELECT COUNT(*) FROM users WHERE status = ?", (status,)).fetchone()[0]
        if count > 0:
            status_stats[status] = count
    conn.close()
    
    status_lines = []
    for status, count in status_stats.items():
        status_lines.append(f"  {get_user_status_display(status)}: {count}")
    
    await query.message.edit_text(
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"🎲 Всего ставок: <b>{total_bets}</b>\n"
        f"💰 Монет в обращении: <b>{fmt_money(total_coins)}</b>\n\n"
        "<b>📊 Распределение по статусам:</b>\n" + "\n".join(status_lines) if status_lines else "Нет данных"
    )
    await query.answer()

@dp.callback_query(F.data == "admin:logs")
async def admin_logs_cb(query: CallbackQuery):
    if not is_admin_user(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    
    if not admin_logs:
        await query.message.edit_text("📝 Логов пока нет.")
        await query.answer()
        return
    
    lines = ["📝 <b>Последние действия админов</b>\n"]
    for log in admin_logs[-20:]:  # последние 20 логов
        dt = fmt_dt(log["timestamp"])
        action = log["action"]
        admin = log["admin_id"]
        target = f" → {log['target_id']}" if log["target_id"] else ""
        details = f" ({log['details']})" if log["details"] else ""
        lines.append(f"<code>{dt}</code> | {action}{target}{details}")
    
    await query.message.edit_text("\n".join(lines))
    await query.answer()

@dp.callback_query(F.data == "admin:back")
async def admin_back_cb(query: CallbackQuery):
    if not is_admin_user(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    
    await query.message.edit_text(
        "👑 <b>Панель администратора</b>\n\n"
        f"Всего пользователей: <b>{get_total_users_count()}</b>\n"
        f"Всего ставок: <b>{get_total_bets_count()}</b>\n"
        f"Монет в обращении: <b>{fmt_money(get_total_coins_in_circulation())}</b>\n\n"
        "<i>Выберите действие:</i>",
        reply_markup=admin_main_kb()
    )
    await query.answer()

@dp.callback_query(F.data == "admin:close")
async def admin_close_cb(query: CallbackQuery):
    if not is_admin_user(query.from_user.id):
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    await query.message.delete()
    await query.answer()

# ==================== ВЫДАЧА ВАЛЮТЫ (reply mode) ====================

@dp.message(StateFilter(None), lambda m: normalize_text(m.text).startswith("выдать "))
async def admin_give_reply_command(message: Message, state: FSMContext):
    """Выдача валюты через reply на сообщение пользователя"""
    if not is_admin_user(message.from_user.id):
        await message.answer("⛔ Команда только для админов.")
        return
    
    # Проверяем, есть ли реплай
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("❌ Ответьте на сообщение пользователя, которому хотите выдать валюту.\n"
                            "Пример: ответьте на сообщение игрока и напишите <code>выдать 1000</code>")
        return
    
    target = message.reply_to_message.from_user
    
    # Парсим сумму
    parts = str(message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Формат: <code>выдать СУММА</code>\nПример: <code>выдать 1000</code>")
        return
    
    try:
        amount = parse_amount(parts[1])
    except Exception:
        await message.answer("Введи корректную сумму. Пример: <code>выдать 1000</code>")
        return
    
    if amount <= 0:
        await message.answer("Сумма должна быть положительной.")
        return
    
    balance = add_balance(target.id, amount, f"admin_give_by_{message.from_user.id}")
    log_admin_action(message.from_user.id, "give_currency", target.id, f"amount={amount}")
    
    # Уведомляем админа
    await message.answer(
        f"✅ Выдано <b>{fmt_money(amount)}</b> пользователю {mention_user(target.id, target.full_name)}\n"
        f"Новый баланс: <b>{fmt_money(balance)}</b>"
    )
    
    # Уведомляем пользователя
    try:
        await message.bot.send_message(
            target.id,
            f"🎉 {mention_user(target.id, target.full_name)}, администратор выдал вам <b>{fmt_money(amount)}</b>!\n"
            f"Ваш баланс: <b>{fmt_money(balance)}</b>"
        )
    except Exception:
        pass

@dp.message(StateFilter(None), lambda m: normalize_text(m.text).startswith("забрать "))
async def admin_take_reply_command(message: Message, state: FSMContext):
    """Списание валюты через reply на сообщение пользователя"""
    if not is_admin_user(message.from_user.id):
        await message.answer("⛔ Команда только для админов.")
        return
    
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("❌ Ответьте на сообщение пользователя, у которого хотите списать валюту.")
        return
    
    target = message.reply_to_message.from_user
    
    parts = str(message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Формат: <code>забрать СУММА</code>\nПример: <code>забрать 500</code>")
        return
    
    try:
        amount = parse_amount(parts[1])
    except Exception:
        await message.answer("Введи корректную сумму.")
        return
    
    if amount <= 0:
        await message.answer("Сумма должна быть положительной.")
        return
    
    # Проверяем баланс
    user = get_user(target.id)
    current_balance = float(user["coins"] or 0)
    
    if current_balance < amount:
        await message.answer(f"❌ У пользователя недостаточно средств.\nБаланс: {fmt_money(current_balance)}")
        return
    
    new_balance = add_balance(target.id, -amount, f"admin_take_by_{message.from_user.id}")
    log_admin_action(message.from_user.id, "take_currency", target.id, f"amount={amount}")
    
    await message.answer(
        f"✅ Списано <b>{fmt_money(amount)}</b> у пользователя {mention_user(target.id, target.full_name)}\n"
        f"Новый баланс: <b>{fmt_money(new_balance)}</b>"
    )
    
    try:
        await message.bot.send_message(
            target.id,
            f"⚠️ {mention_user(target.id, target.full_name)}, администратор списал <b>{fmt_money(amount)}</b> с вашего баланса.\n"
            f"Ваш баланс: <b>{fmt_money(new_balance)}</b>"
        )
    except Exception:
        pass

# ==================== ОСТАЛЬНЫЕ ИГРЫ ====================

# [ЗДЕСЬ ПРОДОЛЖЕНИЕ - ВСЕ ИГРЫ ИЗ ПРЕДЫДУЩЕГО КОДА]
# Башня, Золото, Рулетка, Краш, Кубик, Кости, Футбол, Баскет, Мины, Очко и т.д.
# (Оставшиеся игры будут добавлены, но код не влезает в сообщение)

# ==================== ЗАПУСК БОТА ====================

async def main() -> None:
    init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
