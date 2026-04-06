from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import threading
import time
import json
from database import Database
from strategy import RussoStrategy

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*")

db = Database()

# Store latest signals for real-time updates
latest_signals = {}
monitoring_active = True

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/stats')
def get_stats():
    """Get overall statistics"""
    assets = db.get_assets()
    all_stats = []
    
    for asset in assets:
        stats = db.get_performance_stats(asset['symbol'])
        stats['symbol'] = asset['symbol']
        stats['name'] = asset['name']
        stats['is_active'] = asset['is_active']
        all_stats.append(stats)
    
    # Overall totals
    total_signals = sum(s['total_signals'] for s in all_stats)
    total_wins = sum(s['wins'] for s in all_stats)
    total_profit = sum(s['total_profit'] for s in all_stats)
    
    return jsonify({
        'assets': all_stats,
        'overall': {
            'total_signals': total_signals,
            'total_wins': total_wins,
            'total_losses': total_signals - total_wins,
            'win_rate': (total_wins / total_signals * 100) if total_signals > 0 else 0,
            'total_profit': total_profit
        }
    })

@app.route('/api/trades')
def get_trades():
    """Get recent trades"""
    asset = request.args.get('asset')
    limit = int(request.args.get('limit', 50))
    trades = db.get_trade_history(asset, limit)
    return jsonify(trades)

@app.route('/api/assets')
def get_assets():
    """Get all assets"""
    assets = db.get_assets(active_only=False)
    return jsonify(assets)

@app.route('/api/asset/<symbol>/toggle', methods=['POST'])
def toggle_asset(symbol):
    """Enable/disable an asset"""
    assets = db.get_assets(active_only=False)
    asset = next((a for a in assets if a['symbol'] == symbol), None)
    if asset:
        new_status = 0 if asset['is_active'] else 1
        db.update_asset_status(symbol, new_status)
        return jsonify({'success': True, 'is_active': new_status})
    return jsonify({'success': False}), 404

@app.route('/api/optimize/<symbol>', methods=['POST'])
def optimize_asset(symbol):
    """Run optimization for an asset"""
    from optimizer import GeneticOptimizer
    
    try:
        optimizer = GeneticOptimizer(symbol, period='1mo', interval='5m')
        best_params, fitness, result = optimizer.run_optimization()
        
        # Save optimized params
        db.save_optimized_params(symbol, best_params, fitness, 0, 0)
        
        return jsonify({
            'success': True,
            'params': best_params,
            'fitness': fitness
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/current-signals')
def get_current_signals():
    """Get current signals for all assets"""
    assets = db.get_assets(active_only=True)
    signals = {}
    
    for asset in assets:
        try:
            # Fetch latest data
            symbol = asset['symbol']
            ticker = symbol + '=X' if symbol not in ['XAUUSD', 'XAGUSD'] else symbol
            df = yf.download(ticker, period='1d', interval='1m')
            
            if not df.empty:
                df.rename(columns={'Volume': 'volume'}, inplace=True)
                if 'volume' not in df.columns:
                    df['volume'] = 1
                
                # Get active params or use default
                params = db.get_active_params(symbol) or None
                strategy = RussoStrategy(params)
                df = strategy.calculate_indicators(df)
                
                signal = strategy.get_signal(df, asset['min_confidence'])
                
                if signal:
                    signals[asset['symbol']] = {
                        'direction': signal['direction'],
                        'entry_price': signal['entry_price'],
                        'confidence': signal['confidence'],
                        'rsi': signal.get('rsi'),
                        'adx': signal.get('adx')
                    }
                else:
                    signals[asset['symbol']] = None
        except Exception as e:
            signals[asset['symbol']] = {'error': str(e)}
    
    return jsonify(signals)

@app.route('/api/performance-chart')
def performance_chart():
    """Get performance chart data"""
    asset = request.args.get('asset')
    days = int(request.args.get('days', 30))
    
    trades = db.get_trade_history(asset, limit=1000)
    
    if not trades:
        return jsonify({'dates': [], 'cumulative': [], 'win_rate': []})
    
    # Calculate cumulative profit
    cumulative = []
    running_total = 0
    dates = []
    wins = []
    losses = []
    
    for trade in trades:
        running_total += trade.get('profit', 0)
        cumulative.append(running_total)
        dates.append(trade['timestamp'][:10])
        
        if trade.get('result') == 'win':
            wins.append(1)
            losses.append(0)
        else:
            wins.append(0)
            losses.append(1)
    
    # Calculate rolling win rate
    window = 20
    win_rate = []
    for i in range(len(wins)):
        if i < window:
            win_rate.append(sum(wins[:i+1]) / (i+1) * 100 if i > 0 else 0)
        else:
            win_rate.append(sum(wins[i-window:i]) / window * 100)
    
    return jsonify({
        'dates': dates[-100:],
        'cumulative': cumulative[-100:],
        'win_rate': win_rate[-100:]
    })

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    emit('connected', {'data': 'Connected to dashboard'})
    start_realtime_updates()

def send_realtime_update():
    """Send real-time updates to connected clients"""
    global monitoring_active
    
    while monitoring_active:
        try:
            signals = get_current_signals().json
            socketio.emit('signal_update', signals)
            
            # Get latest stats
            stats = get_stats().json
            socketio.emit('stats_update', stats)
            
            time.sleep(30)  # Update every 30 seconds
        except Exception as e:
            print(f"Update error: {e}")
            time.sleep(5)

def start_realtime_updates():
    """Start background thread for real-time updates"""
    thread = threading.Thread(target=send_realtime_update)
    thread.daemon = True
    thread.start()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
