import sqlite3
import os
from typing import Dict, Any, List, Optional

class DBManager:
    def __init__(self, db_path="trading_bot.db"):
        self.db_path = db_path
        self._initialize_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _initialize_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Trades table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    symbol TEXT,
                    side TEXT,
                    price REAL,
                    amount REAL,
                    cost REAL,
                    pnl REAL DEFAULT 0.0,
                    status TEXT
                )
            ''')
            # Logs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    level TEXT,
                    message TEXT
                )
            ''')
            conn.commit()

    def log_trade(self, symbol: str, side: str, price: float, amount: float, cost: float, status: str = "OPEN") -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO trades (symbol, side, price, amount, cost, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (symbol, side, price, amount, cost, status))
            conn.commit()
            return cursor.lastrowid

    def update_trade_pnl(self, trade_id: int, pnl: float, status: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE trades
                SET pnl = ?, status = ?
                WHERE id = ?
            ''', (pnl, status, trade_id))
            conn.commit()

    def log_message(self, level: str, message: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO logs (level, message)
                VALUES (?, ?)
            ''', (level, message))
            conn.commit()

    def get_recent_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM trades
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
