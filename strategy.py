import pandas as pd
import numpy as np
from typing import Dict, Optional

class RussoStrategy:
    """RUSSO Strategy implementation for multiple assets"""
    
    def __init__(self, params: Dict = None):
        self.params = params or self.default_params()
    
    def default_params(self) -> Dict:
        return {
            'fast_length': 12,
            'slow_length': 26,
            'signal_length': 9,
            'rsi_period': 14,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'volume_ma_period': 20,
            'volume_threshold': 1.2,
            'ema_trend_period': 50,
            'min_confidence': 60,
            'atr_period': 14,
            'adx_period': 14,
            'adx_threshold': 25
        }
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical indicators"""
        
        # MACD
        exp1 = df['close'].ewm(span=self.params['fast_length'], adjust=False).mean()
        exp2 = df['close'].ewm(span=self.params['slow_length'], adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['signal'] = df['macd'].ewm(span=self.params['signal_length'], adjust=False).mean()
        df['macd_histogram'] = df['macd'] - df['signal']
        
        # MACD Crossovers
        df['macd_buy'] = (df['macd'] > df['signal']) & (df['macd'].shift(1) <= df['signal'].shift(1))
        df['macd_sell'] = (df['macd'] < df['signal']) & (df['macd'].shift(1) >= df['signal'].shift(1))
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.params['rsi_period']).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.params['rsi_period']).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        df['rsi_oversold'] = df['rsi'] < self.params['rsi_oversold']
        df['rsi_overbought'] = df['rsi'] > self.params['rsi_overbought']
        
        # Volume analysis
        df['volume_ma'] = df['volume'].rolling(window=self.params['volume_ma_period']).mean()
        df['volume_surge'] = df['volume'] > df['volume_ma'] * self.params['volume_threshold']
        
        # Trend EMA
        df['trend_ema'] = df['close'].ewm(span=self.params['ema_trend_period'], adjust=False).mean()
        df['trend_up'] = df['close'] > df['trend_ema']
        df['trend_down'] = df['close'] < df['trend_ema']
        
        # ATR (Average True Range)
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr'] = true_range.rolling(window=self.params['atr_period']).mean()
        
        # ADX (Average Directional Index)
        df['plus_dm'] = df['high'].diff()
        df['minus_dm'] = -df['low'].diff()
        df['plus_dm'] = df['plus_dm'].where(df['plus_dm'] > 0, 0)
        df['minus_dm'] = df['minus_dm'].where(df['minus_dm'] > 0, 0)
        df['plus_dm'] = df['plus_dm'].where(df['plus_dm'] > df['minus_dm'], 0)
        df['minus_dm'] = df['minus_dm'].where(df['minus_dm'] > df['plus_dm'], 0)
        
        df['atr_adx'] = true_range.rolling(window=self.params['adx_period']).mean()
        df['plus_di'] = 100 * (df['plus_dm'].ewm(span=self.params['adx_period']).mean() / df['atr_adx'])
        df['minus_di'] = 100 * (df['minus_dm'].ewm(span=self.params['adx_period']).mean() / df['atr_adx'])
        df['dx'] = (abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'])) * 100
        df['adx'] = df['dx'].rolling(window=self.params['adx_period']).mean()
        
        df['trend_strength'] = df['adx'] > self.params['adx_threshold']
        
        return df
    
    def calculate_confidence(self, df: pd.DataFrame, idx: int, direction: str) -> int:
        """Calculate signal confidence score (0-100)"""
        score = 0
        
        if direction == 'buy':
            # MACD strength (25 points)
            macd_strength = abs(df.iloc[idx]['macd_histogram']) / df.iloc[idx]['close']
            if macd_strength > 0.001:
                score += 25
            elif macd_strength > 0.0005:
                score += 15
            else:
                score += 8
            
            # RSI confirmation (20 points)
            if df.iloc[idx]['rsi'] < self.params['rsi_oversold']:
                score += 20
            elif df.iloc[idx]['rsi'] < 40:
                score += 12
            
            # Volume confirmation (20 points)
            volume_ratio = df.iloc[idx]['volume'] / df.iloc[idx]['volume_ma']
            if volume_ratio > 1.5:
                score += 20
            elif volume_ratio > 1.2:
                score += 14
            elif volume_ratio > 1.0:
                score += 8
            
            # Trend alignment (15 points)
            if df.iloc[idx]['trend_up']:
                score += 15
            
            # ADX trend strength (10 points)
            if df.iloc[idx]['trend_strength']:
                score += 10
            
            # ATR volatility (10 points)
            atr_percent = df.iloc[idx]['atr'] / df.iloc[idx]['close'] * 100
            if 0.5 < atr_percent < 2.0:
                score += 10
            
        else:  # sell
            # MACD strength (25 points)
            macd_strength = abs(df.iloc[idx]['macd_histogram']) / df.iloc[idx]['close']
            if macd_strength > 0.001:
                score += 25
            elif macd_strength > 0.0005:
                score += 15
            else:
                score += 8
            
            # RSI confirmation (20 points)
            if df.iloc[idx]['rsi'] > self.params['rsi_overbought']:
                score += 20
            elif df.iloc[idx]['rsi'] > 60:
                score += 12
            
            # Volume confirmation (20 points)
            volume_ratio = df.iloc[idx]['volume'] / df.iloc[idx]['volume_ma']
            if volume_ratio > 1.5:
                score += 20
            elif volume_ratio > 1.2:
                score += 14
            elif volume_ratio > 1.0:
                score += 8
            
            # Trend alignment (15 points)
            if df.iloc[idx]['trend_down']:
                score += 15
            
            # ADX trend strength (10 points)
            if df.iloc[idx]['trend_strength']:
                score += 10
            
            # ATR volatility (10 points)
            atr_percent = df.iloc[idx]['atr'] / df.iloc[idx]['close'] * 100
            if 0.5 < atr_percent < 2.0:
                score += 10
        
        return min(100, score)
    
    def get_signal(self, df: pd.DataFrame, min_confidence: int = 60) -> Optional[Dict]:
        """Generate trading signal based on latest data"""
        if len(df) < max(self.params.values()):
            return None
        
        last_idx = len(df) - 1
        
        # Check for buy signal
        if (df.iloc[last_idx]['macd_buy'] and 
            df.iloc[last_idx]['rsi_oversold'] and 
            df.iloc[last_idx]['volume_surge'] and
            df.iloc[last_idx]['trend_up'] and
            df.iloc[last_idx]['trend_strength']):
            
            confidence = self.calculate_confidence(df, last_idx, 'buy')
            
            if confidence >= min_confidence:
                return {
                    'direction': 'CALL',
                    'entry_price': df.iloc[last_idx]['close'],
                    'confidence': confidence,
                    'timestamp': df.index[last_idx],
                    'rsi': round(df.iloc[last_idx]['rsi'], 1),
                    'macd': round(df.iloc[last_idx]['macd'], 5),
                    'volume_ratio': round(df.iloc[last_idx]['volume'] / df.iloc[last_idx]['volume_ma'], 2),
                    'adx': round(df.iloc[last_idx]['adx'], 1),
                    'atr': round(df.iloc[last_idx]['atr'], 5)
                }
        
        # Check for sell signal
        if (df.iloc[last_idx]['macd_sell'] and 
            df.iloc[last_idx]['rsi_overbought'] and 
            df.iloc[last_idx]['volume_surge'] and
            df.iloc[last_idx]['trend_down'] and
            df.iloc[last_idx]['trend_strength']):
            
            confidence = self.calculate_confidence(df, last_idx, 'sell')
            
            if confidence >= min_confidence:
                return {
                    'direction': 'PUT',
                    'entry_price': df.iloc[last_idx]['close'],
                    'confidence': confidence,
                    'timestamp': df.index[last_idx],
                    'rsi': round(df.iloc[last_idx]['rsi'], 1),
                    'macd': round(df.iloc[last_idx]['macd'], 5),
                    'volume_ratio': round(df.iloc[last_idx]['volume'] / df.iloc[last_idx]['volume_ma'], 2),
                    'adx': round(df.iloc[last_idx]['adx'], 1),
                    'atr': round(df.iloc[last_idx]['atr'], 5)
                }
        
        return None
