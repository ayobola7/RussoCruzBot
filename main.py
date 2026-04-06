#!/usr/bin/env python3
"""
RUSSO Trading Bot - Multi-Asset Telegram Bot
Monitors 10 forex and metals pairs, sends signals to Telegram
"""

import asyncio
import logging
import yfinance as yf
import pandas as pd
from datetime import datetime
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import threading
import time

from database import Database
from strategy import RussoStrategy
from optimizer import GeneticOptimizer

# ============================================
# CONFIGURATION
# ============================================

TELEGRAM_TOKEN = "8736985730:AAFh4vhgeL6_IXPN1IHmvJ_ErbIeSMGhT2U
Kee"
CHAT_ID = "688759657"

# Asset list
ASSETS = [
    {'symbol': 'EURUSD', 'name': 'Euro/US Dollar', 'yf_symbol': 'EURUSD=X'},
    {'symbol': 'GBPUSD', 'name': 'British Pound/US Dollar', 'yf_symbol': 'GBPUSD=X'},
    {'symbol': 'USDJPY', 'name': 'US Dollar/Japanese Yen', 'yf_symbol': 'USDJPY=X'},
    {'symbol': 'USDCHF', 'name': 'US Dollar/Swiss Franc', 'yf_symbol': 'USDCHF=X'},
    {'symbol': 'AUDUSD', 'name': 'Australian Dollar/US Dollar', 'yf_symbol': 'AUDUSD=X'},
    {'symbol': 'USDCAD', 'name': 'US Dollar/Canadian Dollar', 'yf_symbol': 'USDCAD=X'},
    {'symbol': 'NZDUSD', 'name': 'New Zealand Dollar/US Dollar', 'yf_symbol': 'NZDUSD=X'},
    {'symbol': 'XAUUSD', 'name': 'Gold/US Dollar', 'yf_symbol': 'GC=F'},
    {'symbol': 'EURGBP', 'name': 'Euro/British Pound', 'yf_symbol': 'EURGBP=X'},
    {'symbol': 'XAGUSD', 'name': 'Silver/US Dollar', 'yf_symbol': 'SI=F'}
]

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = Database()
monitoring_active = False
monitor_task = None

# ============================================
# SIGNAL GENERATION
# ============================================

def fetch_asset_data(symbol: str, yf_symbol: str) -> pd.DataFrame:
    """Fetch latest data for an asset"""
    try:
        df = yf.download(yf_symbol, period='1d', interval='1m', progress=False)
        
        if df.empty:
            logger.warning(f"No data for {symbol}")
            return None
        
        df.rename(columns={'Volume': 'volume'}, inplace=True)
        if 'volume' not in df.columns:
            df['volume'] = 1
        
        return df
    except Exception as e:
        logger.error(f"Error fetching {symbol}: {e}")
        return None

def check_asset_signal(asset: Dict) -> dict:
    """Check for trading signal on a single asset"""
    try:
        df = fetch_asset_data(asset['symbol'], asset['yf_symbol'])
        
        if df is None or df.empty:
            return None
        
        # Get optimized params for this asset
        params = db.get_active_params(asset['symbol'])
        strategy = RussoStrategy(params)
        
        df = strategy.calculate_indicators(df)
        min_confidence = db.get_assets(active_only=True)
        min_conf = next((a['min_confidence'] for a in min_confidence if a['symbol'] == asset['symbol']), 60)
        
        signal = strategy.get_signal(df, min_conf)
        
        if signal:
            return {
                'asset': asset['symbol'],
                'asset_name': asset['name'],
                'direction': signal['direction'],
                'entry_price': signal['entry_price'],
                'confidence': signal['confidence'],
                'rsi': signal.get('rsi'),
                'adx': signal.get('adx'),
                'timestamp': datetime.now()
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error checking {asset['symbol']}: {e}")
        return None

# ============================================
# TELEGRAM BOT HANDLERS
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    keyboard = [
        [InlineKeyboardButton("📊 Status", callback_data='status'),
         InlineKeyboardButton("🎯 Check All", callback_data='check_all')],
        [InlineKeyboardButton("⚙️ Optimize All", callback_data='optimize_all'),
         InlineKeyboardButton("📈 Stats", callback_data='stats')],
        [InlineKeyboardButton("🔔 Monitor On", callback_data='monitor_on'),
         InlineKeyboardButton("🔕 Monitor Off", callback_data='monitor_off')],
        [InlineKeyboardButton("📋 Assets", callback_data='assets')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🤖 *RUSSO Trading Bot - Multi-Asset*\n\n"
        "Monitoring 10 currency pairs and metals:\n"
        "EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD,\n"
        "USDCAD, NZDUSD, XAUUSD, EURGBP, XAGUSD\n\n"
        "Use the buttons below to control the bot.",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'status':
        await send_status(query)
    elif query.data == 'check_all':
        await check_all_signals(query)
    elif query.data == 'optimize_all':
        await optimize_all(query, context)
    elif query.data == 'stats':
        await send_stats(query)
    elif query.data == 'monitor_on':
        await start_monitoring(query, context)
    elif query.data == 'monitor_off':
        await stop_monitoring(query)
    elif query.data == 'assets':
        await show_assets(query)

async def send_status(query):
    """Send bot status"""
    assets = db.get_assets()
    active_count = sum(1 for a in assets if a['is_active'])
    
    # Get today's stats
    today_stats = db.get_performance_stats(days=1)
    
    status_msg = (
        "📊 *Bot Status*\n\n"
        f"🟢 Status: {'Monitoring' if monitoring_active else 'Idle'}\n"
        f"📈 Active Assets: {active_count}/{len(assets)}\n"
        f"📊 Today's Signals: {today_stats['total_signals']}\n"
        f"✅ Today's Wins: {today_stats['wins']}\n"
        f"📉 Today's Win Rate: {today_stats['win_rate']:.1f}%\n"
        f"💰 Today's Profit: ${today_stats['total_profit']:.2f}\n\n"
        "Use /check to scan all assets manually."
    )
    
    await query.edit_message_text(status_msg, parse_mode='Markdown')
    await show_main_menu(query)

async def check_all_signals(query):
    """Check all assets for signals"""
    await query.edit_message_text("🔍 Scanning all assets... Please wait.")
    
    assets = db.get_assets(active_only=True)
    signals = []
    
    for asset in assets:
        signal = check_asset_signal(asset)
        if signal:
            signals.append(signal)
    
    if signals:
        msg = "🚨 *SIGNALS DETECTED*\n\n"
        for s in signals:
            emoji = "🟢" if s['direction'] == 'CALL' else "🔴"
            msg += f"{emoji} *{s['asset']}*: {s['direction']}\n"
            msg += f"   Price: {s['entry_price']:.5f} | Conf: {s['confidence']}%\n"
            msg += f"   RSI: {s['rsi']} | ADX: {s['adx']}\n\n"
        
        msg += "💡 *Suggested Action:*\n"
        msg += "• Use 1-5 minute expiration\n"
        msg += "• Start with demo account\n"
        msg += "• Never risk more than 2% per trade"
        
        await query.edit_message_text(msg, parse_mode='Markdown')
        
        # Save signals to database
        for s in signals:
            db.save_signal({
                'timestamp': s['timestamp'].isoformat(),
                'asset': s['asset'],
                'direction': s['direction'],
                'entry_price': s['entry_price'],
                'confidence': s['confidence'],
                'rsi': s.get('rsi'),
                'macd': None,
                'volume_ratio': None
            })
    else:
        await query.edit_message_text(
            "📭 *No Signals Found*\n\n"
            "No assets currently meet the RUSSO strategy criteria.\n"
            "Try again in a few minutes.",
            parse_mode='Markdown'
        )
    
    await show_main_menu(query)

async def optimize_all(query, context):
    """Run optimization for all assets"""
    await query.edit_message_text(
        "🧬 *Starting Optimization*\n\n"
        "This will optimize parameters for all 10 assets.\n"
        "Estimated time: 10-15 minutes.\n\n"
        "Progress will be reported here...",
        parse_mode='Markdown'
    )
    
    assets = db.get_assets()
    results = []
    
    for i, asset in enumerate(assets):
        await query.edit_message_text(
            f"🔄 Optimizing {asset['symbol']}... ({i+1}/{len(assets)})\n"
            f"Please wait...",
            parse_mode='Markdown'
        )
        
        try:
            optimizer = GeneticOptimizer(asset['symbol'], period='1mo', interval='5m')
            best_params, fitness, result = optimizer.run_optimization()
            
            db.save_optimized_params(asset['symbol'], best_params, fitness, 0, 0)
            
            results.append({
                'asset': asset['symbol'],
                'fitness': fitness,
                'params': best_params
            })
            
            await asyncio.sleep(2)  # Rate limiting
            
        except Exception as e:
            results.append({'asset': asset['symbol'], 'error': str(e)})
    
    # Send summary
    summary = "✅ *Optimization Complete*\n\n"
    for r in results:
        if 'error' in r:
            summary += f"❌ {r['asset']}: Failed - {r['error']}\n"
        else:
            summary += f"✅ {r['asset']}: Fitness {r['fitness']:.1f}\n"
    
    await query.edit_message_text(summary, parse_mode='Markdown')
    await show_main_menu(query)

async def send_stats(query):
    """Send performance statistics"""
    assets = db.get_assets()
    stats_msg = "📈 *30-Day Performance*\n\n"
    
    for asset in assets:
        stats = db.get_performance_stats(asset['symbol'], days=30)
        if stats['total_signals'] > 0:
            emoji = "🟢" if stats['win_rate'] >= 55 else ("🟡" if stats['win_rate'] >= 45 else "🔴")
            stats_msg += f"{emoji} *{asset['symbol']}*: {stats['win_rate']:.1f}% ({stats['wins']}/{stats['total_signals']})\n"
            stats_msg += f"   Profit: ${stats['total_profit']:.2f} | Conf: {stats['avg_confidence']:.0f}%\n"
    
    await query.edit_message_text(stats_msg, parse_mode='Markdown')
    await show_main_menu(query)

async def show_assets(query):
    """Show asset list with toggles"""
    assets = db.get_assets(active_only=False)
    
    keyboard = []
    for asset in assets:
        status = "✅" if asset['is_active'] else "❌"
        keyboard.append([InlineKeyboardButton(
            f"{status} {asset['symbol']} - {asset['name']}",
            callback_data=f"toggle_{asset['symbol']}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='status')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📋 *Assets*\n\nTap to toggle monitoring:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def toggle_asset_from_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle asset from menu"""
    query = update.callback_query
    symbol = query.data.replace('toggle_', '')
    
    assets = db.get_assets(active_only=False)
    asset = next((a for a in assets if a['symbol'] == symbol), None)
    
    if asset:
        new_status = 0 if asset['is_active'] else 1
        db.update_asset_status(symbol, new_status)
        await query.answer(f"{symbol} {'activated' if new_status else 'deactivated'}")
        await show_assets(query)

async def start_monitoring(query, context):
    """Start automatic monitoring"""
    global monitoring_active, monitor_task
    
    if monitoring_active:
        await query.edit_message_text("⚠️ Monitoring is already active!")
        await show_main_menu(query)
        return
    
    monitoring_active = True
    await query.edit_message_text(
        "🔔 *Monitoring Started*\n\n"
        "I will check all active assets every 5 minutes.\n"
        "You will receive alerts when signals are found.\n\n"
        "Use /stop to disable.",
        parse_mode='Markdown'
    )
    
    # Start monitoring in background
    monitor_task = asyncio.create_task(monitor_loop(context))
    await show_main_menu(query)

async def stop_monitoring(query):
    """Stop automatic monitoring"""
    global monitoring_active, monitor_task
    
    if not monitoring_active:
        await query.edit_message_text("⚠️ Monitoring is not active!")
        await show_main_menu(query)
        return
    
    monitoring_active = False
    if monitor_task:
        monitor_task.cancel()
    
    await query.edit_message_text(
        "🔕 *Monitoring Stopped*\n\n"
        "Automatic signal alerts have been disabled.",
        parse_mode='Markdown'
    )
    await show_main_menu(query)

async def monitor_loop(context: ContextTypes.DEFAULT_TYPE):
    """Background monitoring loop"""
    last_signals = {}
    
    while monitoring_active:
        try:
            assets = db.get_assets(active_only=True)
            
            for asset in assets:
                signal = check_asset_signal(asset)
                
                if signal:
                    # Avoid duplicate alerts (same asset, same direction within 10 minutes)
                    key = f"{asset['symbol']}_{signal['direction']}"
                    if key in last_signals:
                        time_diff = (datetime.now() - last_signals[key]).total_seconds()
                        if time_diff < 600:
                            continue
                    
                    last_signals[key] = datetime.now()
                    
                    # Send alert
                    emoji = "🟢" if signal['direction'] == 'CALL' else "🔴"
                    alert_msg = (
                        f"{emoji} *AUTO SIGNAL ALERT*\n\n"
                        f"📈 *Asset:* {signal['asset']} ({signal['asset_name']})\n"
                        f"🎯 *Direction:* {signal['direction']}\n"
                        f"💰 *Entry:* {signal['entry_price']:.5f}\n"
                        f"📊 *Confidence:* {signal['confidence']}%\n"
                        f"📉 *RSI:* {signal['rsi']} | *ADX:* {signal['adx']}\n\n"
                        f"⏰ *Time:* {signal['timestamp'].strftime('%H:%M:%S')}\n\n"
                        f"💡 Consider a 1-5 minute trade"
                    )
                    
                    await context.bot.send_message(chat_id=CHAT_ID, text=alert_msg, parse_mode='Markdown')
                    
                    # Save to database
                    db.save_signal({
                        'timestamp': signal['timestamp'].isoformat(),
                        'asset': signal['asset'],
                        'direction': signal['direction'],
                        'entry_price': signal['entry_price'],
                        'confidence': signal['confidence'],
                        'rsi': signal.get('rsi'),
                        'macd': None,
                        'volume_ratio': None
                    })
            
            await asyncio.sleep(300)  # Check every 5 minutes
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Monitor loop error: {e}")
            await asyncio.sleep(60)

async def show_main_menu(query):
    """Show main menu"""
    keyboard = [
        [InlineKeyboardButton("📊 Status", callback_data='status'),
         InlineKeyboardButton("🎯 Check All", callback_data='check_all')],
        [InlineKeyboardButton("⚙️ Optimize All", callback_data='optimize_all'),
         InlineKeyboardButton("📈 Stats", callback_data='stats')],
        [InlineKeyboardButton("🔔 Monitor On", callback_data='monitor_on'),
         InlineKeyboardButton("🔕 Monitor Off", callback_data='monitor_off')],
        [InlineKeyboardButton("📋 Assets", callback_data='assets')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text("Main Menu:", reply_markup=reply_markup)

# ============================================
# MAIN
# ============================================

def main():
    """Main entry point"""
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(CallbackQueryHandler(toggle_asset_from_menu, pattern='^toggle_'))
    
    logger.info("Bot started! Monitoring 10 assets...")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
