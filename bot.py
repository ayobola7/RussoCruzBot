#!/usr/bin/env python3
"""
RUSSO Trading Bot - Multi-Asset Telegram Bot
Monitors 10 forex and metals pairs, sends signals to Telegram
"""

import os
import logging
import yfinance as yf
import pandas as pd
from datetime import datetime
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import asyncio
import threading
import time

# ============================================
# CONFIGURATION - Get from environment variables
# ============================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")
CHAT_ID = os.environ.get("CHAT_ID", "YOUR_CHAT_ID_HERE")

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

monitoring_active = False
monitor_task = None

# ============================================
# SIGNAL GENERATION
# ============================================

def check_asset_signal(asset: dict) -> dict:
    """Simple signal check using MACD crossover"""
    try:
        df = yf.download(asset['yf_symbol'], period='1d', interval='5m', progress=False)
        
        if df.empty or len(df) < 50:
            return None
        
        # Calculate MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        
        # Check for crossover
        macd_prev = macd.iloc[-2]
        macd_curr = macd.iloc[-1]
        signal_prev = signal.iloc[-2]
        signal_curr = signal.iloc[-1]
        
        # Calculate RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]
        
        # Determine signal
        if macd_curr > signal_curr and macd_prev <= signal_prev:
            if current_rsi < 70:  # Avoid overbought
                return {
                    'asset': asset['symbol'],
                    'asset_name': asset['name'],
                    'direction': 'CALL',
                    'entry_price': df['Close'].iloc[-1],
                    'confidence': 70,
                    'rsi': round(current_rsi, 1),
                    'timestamp': datetime.now()
                }
        elif macd_curr < signal_curr and macd_prev >= signal_prev:
            if current_rsi > 30:  # Avoid oversold
                return {
                    'asset': asset['symbol'],
                    'asset_name': asset['name'],
                    'direction': 'PUT',
                    'entry_price': df['Close'].iloc[-1],
                    'confidence': 70,
                    'rsi': round(current_rsi, 1),
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
        [InlineKeyboardButton("🔔 Monitor On", callback_data='monitor_on'),
         InlineKeyboardButton("🔕 Monitor Off", callback_data='monitor_off')]
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
    elif query.data == 'monitor_on':
        await start_monitoring(query, context)
    elif query.data == 'monitor_off':
        await stop_monitoring(query)

async def send_status(query):
    """Send bot status"""
    status_msg = (
        "📊 *Bot Status*\n\n"
        f"🟢 Status: {'Monitoring' if monitoring_active else 'Idle'}\n"
        f"📈 Active Assets: {len(ASSETS)}\n\n"
        "Use /check to scan all assets manually."
    )
    
    await query.edit_message_text(status_msg, parse_mode='Markdown')
    await show_main_menu(query)

async def check_all_signals(query):
    """Check all assets for signals"""
    await query.edit_message_text("🔍 Scanning all assets... Please wait.")
    
    signals = []
    
    for asset in ASSETS:
        signal = check_asset_signal(asset)
        if signal:
            signals.append(signal)
    
    if signals:
        msg = "🚨 *SIGNALS DETECTED*\n\n"
        for s in signals:
            emoji = "🟢" if s['direction'] == 'CALL' else "🔴"
            msg += f"{emoji} *{s['asset']}*: {s['direction']}\n"
            msg += f"   Price: {s['entry_price']:.5f} | Conf: {s['confidence']}%\n"
            msg += f"   RSI: {s['rsi']}\n\n"
        
        msg += "💡 *Suggested Action:*\n"
        msg += "• Use 1-5 minute expiration\n"
        msg += "• Start with demo account\n"
        msg += "• Never risk more than 2% per trade"
        
        await query.edit_message_text(msg, parse_mode='Markdown')
    else:
        await query.edit_message_text(
            "📭 *No Signals Found*\n\n"
            "No assets currently meet the RUSSO strategy criteria.\n"
            "Try again in a few minutes.",
            parse_mode='Markdown'
        )
    
    await show_main_menu(query)

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
            for asset in ASSETS:
                signal = check_asset_signal(asset)
                
                if signal:
                    # Avoid duplicate alerts (same asset within 10 minutes)
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
                        f"📉 *RSI:* {signal['rsi']}\n\n"
                        f"💡 Consider a 1-5 minute trade"
                    )
                    
                    await context.bot.send_message(chat_id=CHAT_ID, text=alert_msg, parse_mode='Markdown')
            
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
        [InlineKeyboardButton("🔔 Monitor On", callback_data='monitor_on'),
         InlineKeyboardButton("🔕 Monitor Off", callback_data='monitor_off')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text("Main Menu:", reply_markup=reply_markup)

# ============================================
# MAIN
# ============================================

def main():
    """Main entry point"""
    if TELEGRAM_TOKEN == "YOUR_BOT_TOKEN_HERE" or CHAT_ID == "YOUR_CHAT_ID_HERE":
        print("ERROR: Please set TELEGRAM_TOKEN and CHAT_ID environment variables")
        print("On Render: Go to Environment tab and add these variables")
        return
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("Bot started! Monitoring 10 assets...")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
