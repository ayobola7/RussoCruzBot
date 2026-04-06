import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional

class Database:
    def __init__(self, db_path='russo_bot.db'):
        self.db_path = db_path
        self.init_tables()
    
    def init_tables(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Signals table (expanded for multi-asset)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                asset TEXT,
                direction TEXT,
                entry_price REAL,
                confidence INTEGER,
                status TEXT,
                result TEXT,
                exit_price REAL,
                profit REAL,
                rsi REAL,
                macd REAL,
                volume_ratio REAL
            )
        ''')
        
        # Assets table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT UNIQUE,
                name TEXT,
                is_active INTEGER DEFAULT 1,
                min_confidence INTEGER DEFAULT 60,
                trade_amount REAL DEFAULT 10
            )
        ''')
        
        # Insert default assets
        default_assets = [
            ('EURUSD', 'Euro/US Dollar', 1, 60, 10),
            ('GBPUSD', 'British Pound/US Dollar', 1, 60, 10),
            ('USDJPY', 'US Dollar/Japanese Yen', 1, 60, 10),
            ('USDCHF', 'US Dollar/Swiss Franc', 1, 60, 10),
            ('AUDUSD', 'Australian Dollar/US Dollar', 1, 60, 10),
            ('USDCAD', 'US Dollar/Canadian Dollar', 1, 60, 10),
            ('NZDUSD', 'New Zealand Dollar/US Dollar', 1, 60, 10),
            ('XAUUSD', 'Gold/US Dollar', 1, 60, 10),
            ('EURGBP', 'Euro/British Pound', 1, 60, 10),
            ('XAGUSD', 'Silver/US Dollar', 1, 60, 10)
        ]
        
        for asset in default_assets:
            cursor.execute('''
                INSERT OR IGNORE INTO assets (symbol, name, is_active, min_confidence, trade_amount)
                VALUES (?, ?, ?, ?, ?)
            ''', asset)
        
        # Optimized parameters table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS optimized_params (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset TEXT,
                created_at TEXT,
                params TEXT,
                fitness REAL,
                win_rate REAL,
                total_trades INTEGER,
                is_active INTEGER DEFAULT 0
            )
        ''')
        
        # Performance snapshot table (for dashboard)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS performance_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                asset TEXT,
                total_signals INTEGER,
                wins INTEGER,
                losses INTEGER,
                win_rate REAL,
                total_profit REAL,
                avg_confidence REAL
            )
        ''')
        
        # User settings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_signal(self, signal_data: Dict):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO signals 
            (timestamp, asset, direction, entry_price, confidence, status, rsi, macd, volume_ratio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            signal_data['timestamp'],
            signal_data['asset'],
            signal_data['direction'],
            signal_data['entry_price'],
            signal_data['confidence'],
            'pending',
            signal_data.get('rsi'),
            signal_data.get('macd'),
            signal_data.get('volume_ratio')
        ))
        conn.commit()
        signal_id = cursor.lastrowid
        conn.close()
        return signal_id
    
    def update_signal_result(self, signal_id: int, result: str, exit_price: float, profit: float):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE signals 
            SET result = ?, exit_price = ?, profit = ?, status = 'closed'
            WHERE id = ?
        ''', (result, exit_price, profit, signal_id))
        conn.commit()
        conn.close()
    
    def get_assets(self, active_only=True) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM assets"
        if active_only:
            query += " WHERE is_active = 1"
        
        cursor.execute(query)
        assets = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return assets
    
    def update_asset_status(self, symbol: str, is_active: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE assets SET is_active = ? WHERE symbol = ?", (is_active, symbol))
        conn.commit()
        conn.close()
    
    def get_performance_stats(self, asset: str = None, days: int = 30) -> Dict:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        where_clause = "WHERE timestamp > datetime('now', ?)"
        params = [f'-{days} days']
        
        if asset:
            where_clause += " AND asset = ?"
            params.append(asset)
        
        cursor.execute(f'''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
                AVG(confidence) as avg_confidence,
                SUM(profit) as total_profit,
                AVG(CASE WHEN result='win' THEN confidence ELSE NULL END) as avg_win_confidence,
                AVG(CASE WHEN result='loss' THEN confidence ELSE NULL END) as avg_loss_confidence
            FROM signals 
            {where_clause}
        ''', params)
        
        stats = cursor.fetchone()
        conn.close()
        
        total = stats[0] or 0
        wins = stats[1] or 0
        
        return {
            'total_signals': total,
            'wins': wins,
            'losses': stats[2] or 0,
            'win_rate': (wins / total * 100) if total > 0 else 0,
            'avg_confidence': round(stats[3] or 0, 1),
            'total_profit': round(stats[4] or 0, 2),
            'avg_win_confidence': round(stats[5] or 0, 1),
            'avg_loss_confidence': round(stats[6] or 0, 1)
        }
    
    def get_trade_history(self, asset: str = None, limit: int = 100) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM signals WHERE status = 'closed' ORDER BY timestamp DESC LIMIT ?"
        params = [limit]
        
        if asset:
            query = "SELECT * FROM signals WHERE asset = ? AND status = 'closed' ORDER BY timestamp DESC LIMIT ?"
            params = [asset, limit]
        
        cursor.execute(query, params)
        trades = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return trades
    
    def save_optimized_params(self, asset: str, params: Dict, fitness: float, win_rate: float, total_trades: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Deactivate old params for this asset
        cursor.execute("UPDATE optimized_params SET is_active = 0 WHERE asset = ?", (asset,))
        
        # Insert new params
        cursor.execute('''
            INSERT INTO optimized_params (asset, created_at, params, fitness, win_rate, total_trades, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (asset, datetime.now().isoformat(), json.dumps(params), fitness, win_rate, total_trades, 1))
        
        conn.commit()
        conn.close()
    
    def get_active_params(self, asset: str) -> Optional[Dict]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT params FROM optimized_params 
            WHERE asset = ? AND is_active = 1 
            ORDER BY id DESC LIMIT 1
        ''', (asset,))
        row = cursor.fetchone()
        conn.close()
        return json.loads(row[0]) if row else None
    
    def save_performance_snapshot(self, asset: str, stats: Dict):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO performance_snapshots (timestamp, asset, total_signals, wins, losses, win_rate, total_profit, avg_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            asset,
            stats['total_signals'],
            stats['wins'],
            stats['losses'],
            stats['win_rate'],
            stats['total_profit'],
            stats['avg_confidence']
        ))
        conn.commit()
        conn.close()
