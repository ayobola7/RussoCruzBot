from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
import yfinance as yf
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Use eventlet for production
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

ASSETS = ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD', 'XAUUSD', 'EURGBP', 'XAGUSD']

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/stats')
def get_stats():
    """Get current stats"""
    return jsonify({
        'assets': [{'symbol': a, 'is_active': True} for a in ASSETS],
        'overall': {'total_signals': 0, 'win_rate': 0, 'total_profit': 0}
    })

@app.route('/api/current-signals')
def get_current_signals():
    """Get current signals"""
    signals = {}
    for asset in ASSETS:
        try:
            yf_symbol = asset + '=X' if asset not in ['XAUUSD', 'XAGUSD'] else ('GC=F' if asset == 'XAUUSD' else 'SI=F')
            df = yf.download(yf_symbol, period='1d', interval='5m', progress=False)
            
            if not df.empty and len(df) > 26:
                exp1 = df['Close'].ewm(span=12).mean()
                exp2 = df['Close'].ewm(span=26).mean()
                macd = exp1 - exp2
                signal = macd.ewm(span=9).mean()
                
                if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] <= signal.iloc[-2]:
                    signals[asset] = {'direction': 'CALL', 'confidence': 70}
                elif macd.iloc[-1] < signal.iloc[-1] and macd.iloc[-2] >= signal.iloc[-2]:
                    signals[asset] = {'direction': 'PUT', 'confidence': 70}
                else:
                    signals[asset] = None
            else:
                signals[asset] = None
        except Exception as e:
            signals[asset] = None
    
    return jsonify(signals)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
