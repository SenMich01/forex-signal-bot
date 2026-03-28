"""
Main Telegram Forex Signal Bot (Webhook Mode).

Handles Telegram bot interactions, command processing, and scheduled scanning.
Runs as a Flask web server for webhook mode deployment with proper async integration.
"""

import logging
import os
import asyncio
import threading
import requests
from datetime import datetime
from typing import Dict, Any
from flask import Flask, request, jsonify

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import BOT_NAME, BOT_DESCRIPTION, SCAN_INTERVAL_MINUTES
from scanner import get_scanner
from strategy import generate_signals_for_pair, Signal

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
SELECTING_PAIR = 1

class ForexSignalBot:
    """Main Forex Signal Bot class."""
    
    def __init__(self, token: str):
        self.token = token
        self.application = None
        self.scheduler = None
        self.scanner = get_scanner()
        self.app = Flask(__name__)
        
        # Set up Flask routes
        self.setup_routes()
        # Set up Telegram handlers
        self.setup_handlers()
    
    def setup_routes(self):
        """Set up Flask routes."""
        
        @self.app.route('/webhook', methods=['POST'])
        def webhook():
            """Handle incoming webhook requests from Telegram."""
            try:
                data = request.get_json(force=True)
                logger.info(f"Received update: {data}")
                
                # Return 200 immediately so Telegram stops retrying
                threading.Thread(
                    target=self.run_async,
                    args=(self.process_update(data),)
                ).start()
                return "ok", 200
            except Exception as e:
                logger.error(f"Error processing webhook: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        @self.app.route('/', methods=['GET'])
        def health():
            """Health check endpoint."""
            return "Bot is running", 200
    
    async def process_update(self, data):
        """Process update in background thread."""
        update = Update.de_json(data, self.application.bot)
        await self.application.process_update(update)
    
    def setup_handlers(self):
        """Set up Telegram command handlers."""
        # Initialize application
        self.application = Application.builder().token(self.token).build()
        
        # Add command handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("pairs", self.pairs_command))
        self.application.add_handler(CommandHandler("signal", self.signal_command))
        self.application.add_handler(CommandHandler("signalall", self.signalall_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("debug", self.debug_command))
        
        # Add unknown command handler
        self.application.add_handler(MessageHandler(filters.COMMAND, self.unknown))
        
        # Add error handler
        self.application.add_error_handler(self.error_handler)
    
    def run_async(self, coro):
        """Run async function in sync context."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        # Add subscriber
        self.scanner.add_subscriber(chat_id)
        
        welcome_message = """👋 Welcome to Forex Signal Bot!
I monitor 7 forex pairs 24/5 and alert you
when a high-probability trade setup is found.

📌 Monitored Pairs:
USDJPY | EURUSD | GBPUSD | XAUUSD
USDCAD | EURJPY | GBPJPY

Use /help to see all commands."""
        
        await update.message.reply_text(welcome_message)
        logger.info(f"User {user.username} ({chat_id}) started the bot")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_text = """📖 Available Commands:

/start — Welcome message
/pairs — List monitored pairs
/signal USDJPY — Get signal for one pair
/signalall — Scan all 7 pairs now
/status — Bot status and last scan time
/help — Show this message"""
        
        await update.message.reply_text(help_text)
    
    async def pairs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pairs command."""
        message = """📊 Monitored Forex Pairs:

USDJPY — US Dollar / Japanese Yen
EURUSD — Euro / US Dollar
GBPUSD — British Pound / US Dollar
XAUUSD — Gold / US Dollar
USDCAD — US Dollar / Canadian Dollar
EURJPY — Euro / Japanese Yen
GBPJPY — British Pound / Japanese Yen

Use /signal EURUSD to check a specific pair."""
        
        await update.message.reply_text(message)
    
    async def signal_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /signal command for specific pair."""
        if not context.args:
            await update.message.reply_text("Please specify a pair. Usage: /signal EURUSD")
            return
        
        pair_symbol = context.args[0].upper()
        
        # Add =X suffix if not present
        if not pair_symbol.endswith("=X"):
            pair_symbol += "=X"
        
        # Validate pair
        from config import FOREX_PAIRS
        if pair_symbol not in FOREX_PAIRS:
            valid_pairs = [p.replace("=X", "") for p in FOREX_PAIRS]
            await update.message.reply_text(f"❌ Invalid pair: {pair_symbol}\n\nValid pairs:\n" + "\n".join(valid_pairs))
            return
        
        await update.message.reply_text(f"🔍 Analyzing {pair_symbol}...")
        
        try:
            # Import the new signal generation function
            from strategy import generate_signal_for_pair
            
            signal_data = generate_signal_for_pair(pair_symbol)
            
            if signal_data:
                # Check if it's an error signal
                if signal_data.get("error"):
                    await update.message.reply_text(
                        f"⚠️ {signal_data['message']}\n\n"
                        f"This usually means:\n"
                        f"- Market is closed (weekend/holiday)\n"
                        f"- Data provider temporarily unavailable\n"
                        f"- Try again in a few minutes"
                    )
                    return
                
                message = self.format_signal_message_new(signal_data)
                await update.message.reply_text(message)
            else:
                pair_name = self.get_pair_name(pair_symbol)
                await update.message.reply_text(f"🔍 No signal found for {pair_name} right now.\nMarket conditions don't meet entry criteria.\nTry again in a few minutes.")
                
        except Exception as e:
            logger.error(f"Error in signal command: {e}")
            await update.message.reply_text("❌ Error generating signal. Please try again later.")
    
    async def signalall_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /signalall command."""
        await update.message.reply_text("🔍 Scanning all pairs for signals...")
        
        try:
            # Import the new signal generation function
            from strategy import generate_signals_for_all_pairs
            
            signals_data = generate_signals_for_all_pairs()
            
            if signals_data:
                # Show summary table first
                summary_message = "📊 FULL MARKET SCAN\n"
                for signal_data in signals_data:
                    pair = signal_data["pair"]
                    direction_emoji = "📈" if signal_data["direction"] == "BUY" else "📉"
                    strength_emoji = "✅" if signal_data["strength"] == "STRONG" else "⚠️" if signal_data["strength"] == "MODERATE" else "❌"
                    summary_message += f"{pair:<8} {direction_emoji} {signal_data['direction']:<6} {signal_data['strength']:<8} {strength_emoji}\n"
                
                summary_message += "\n✅ STRONG — High confidence trade\n⚠️ MODERATE — Decent setup, manage risk\n❌ WEAK — Avoid or use small size\n"
                summary_message += "Use /signal USDJPY for full details.\n"
                summary_message += f"⏱️ Scanned: {datetime.now().strftime('%H:%M UTC')}"
                
                await update.message.reply_text(summary_message)
                
                # Show full details for each signal
                for signal_data in signals_data:
                    message = self.format_signal_message_new(signal_data)
                    await update.message.reply_text(message)
            else:
                await update.message.reply_text("🔍 No signals found across all pairs right now.\nNext auto-scan in a few minutes.")
                
        except Exception as e:
            logger.error(f"Error in signalall command: {e}")
            await update.message.reply_text("❌ Error scanning for signals. Please try again later.")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        status_time = self.scanner.last_scan_time.strftime('%Y-%m-%d %H:%M:%S') if self.scanner.last_scan_time else "Never"
        
        message = f"""✅ Bot Status: Online
📡 Webhook: Active
⏰ Last Scan: {status_time}
👥 Subscribers: {self.scanner.get_subscriber_count()}
📈 Pairs Monitored: 7"""
        
        await update.message.reply_text(message)
    
    async def debug_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /debug command for testing data fetch."""
        pair = "EURUSD"
        if context.args:
            pair = context.args[0].upper()
        
        await update.message.reply_text(f"🔧 Testing data fetch for {pair}...")
        
        try:
            # Import data fetching functions
            from data_fetcher import get_m5_candles, get_h1_candles
            
            m5 = get_m5_candles(pair)
            h1 = get_h1_candles(pair)
            
            if m5 is not None and not m5.empty:
                latest = m5.iloc[-1]
                msg = (
                    f"✅ Data fetch working!\n\n"
                    f"Pair: {pair}\n"
                    f"M5 candles: {len(m5)}\n"
                    f"H1 candles: {len(h1) if h1 is not None else 0}\n"
                    f"Latest close: {latest['close']:.5f}\n"
                    f"Latest time: {m5.index[-1]}"
                )
            else:
                msg = (
                    f"❌ Data fetch FAILED for {pair}\n"
                    f"Market may be closed or API issue."
                )
            
            await update.message.reply_text(msg)
            
        except Exception as e:
            logger.error(f"Debug command error: {e}")
            await update.message.reply_text(f"❌ Debug error: {str(e)}")
    
    async def unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle unknown commands."""
        await update.message.reply_text(
            "❓ Unknown command. Use /help to see available commands."
        )
    
    def format_signal_message(self, signal: Signal) -> str:
        """Format a signal into a Telegram message."""
        pair_name = self.get_pair_name(signal.pair)
        
        message = f"""🔔 FOREX SIGNAL — {pair_name}
📈 Direction: {signal.direction}
💰 Entry Price: {signal.entry:.5f}
🛑 Stop Loss: {signal.stop_loss:.5f}  ({signal.pips_risk:+.1f} pips)
🎯 Take Profit: {signal.take_profit:.5f}  ({signal.pips_reward:+.1f} pips)
⚖️ Risk/Reward: 1:{signal.risk_reward:.1f}
📊 RSI: {signal.rsi:.1f}
⏰ Timeframe: M5 | Session: London/New York
⏱️ Signal Time: {signal.timestamp.strftime('%Y-%m-%d %H:%M UTC')}"""
        
        return message
    
    def format_signal_message_new(self, signal_data: Dict) -> str:
        """Format a new signal into a Telegram message."""
        pair_name = signal_data["pair"]
        direction_emoji = "🟢" if signal_data["direction"] == "BUY" else "🔴"
        
        message = f"""📊 FOREX SIGNAL — {pair_name}
📈 Direction: {signal_data["direction"]} {direction_emoji}
💪 Signal Strength: {signal_data["strength"]} (Score: {signal_data["score"]}/100)
💰 Entry Price:   {signal_data["entry"]}
🛑 Stop Loss:     {signal_data["stop_loss"]}  ({signal_data["sl_pips"]:+.1f} pips)
🎯 Take Profit:   {signal_data["take_profit"]}  ({signal_data["tp_pips"]:+.1f} pips)
⚖️ Risk/Reward:   {signal_data["rr_ratio"]}
📉 RSI (14):      {signal_data["rsi"]}
📊 H1 Trend:      {signal_data["h1_trend"]} {"✅" if signal_data["h1_trend"] == "BULLISH" else "❌"}
📈 MACD:          {signal_data["macd_signal"]} {"✅" if signal_data["macd_signal"] == "BULLISH" else "❌"}
⚠️ Risk Warning:

Only risk 1-2% of your account per trade
Move SL to breakeven when +1x ATR in profit
WEAK signals = smaller position size"""
        
        # Add WEAK signal warning
        if signal_data["strength"] == "WEAK":
            message += f"""

⚠️ WEAK SIGNAL — Market is ranging/unclear.
Trade with caution or wait for stronger setup."""
        
        message += f"""

⏱️ Generated: {signal_data["timestamp"]}"""
        
        return message
    
    def get_pair_name(self, symbol):
        """Get human-readable name for a forex pair symbol."""
        from config import PAIR_NAMES
        return PAIR_NAMES.get(symbol, symbol.replace("=X", ""))
    
    async def send_signal_to_subscribers(self, signal: Signal):
        """Send signal to all subscribers."""
        message = self.format_signal_message(signal)
        
        for chat_id in self.scanner.subscribers:
            try:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=message
                )
                logger.info(f"Signal sent to subscriber {chat_id}")
            except Exception as e:
                logger.error(f"Failed to send signal to {chat_id}: {e}")
                # Remove inactive subscribers
                if "bot was blocked" in str(e).lower() or "user is deactivated" in str(e).lower():
                    self.scanner.remove_subscriber(chat_id)
    
    async def scheduled_scan(self):
        """Perform scheduled scan and send signals."""
        try:
            signals = await self.scanner.scan_and_generate_signals()
            
            for signal in signals:
                await self.send_signal_to_subscribers(signal)
                
        except Exception as e:
            logger.error(f"Error in scheduled scan: {e}")
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors from the Telegram bot."""
        logger.error(f"Update {update} caused error: {context.error}")
    
    async def setup_scheduler(self):
        """Set up the scheduled scanning."""
        self.scheduler = AsyncIOScheduler()
        
        # Schedule scans every SCAN_INTERVAL_MINUTES
        self.scheduler.add_job(
            self.scheduled_scan,
            IntervalTrigger(minutes=SCAN_INTERVAL_MINUTES),
            id='signal_scan',
            replace_existing=True
        )
        
        logger.info(f"Scheduled scans every {SCAN_INTERVAL_MINUTES} minutes")
    
    async def setup_webhook(self):
        """Set up webhook registration."""
        application_url = os.environ.get('APPLICATION_URL', '')
        if not application_url:
            logger.error("APPLICATION_URL environment variable not set")
            return False
        
        webhook_url = f"{application_url}/webhook"
        
        try:
            await self.application.bot.set_webhook(url=webhook_url)
            logger.info(f"Webhook set to: {webhook_url}")
            return True
        except Exception as e:
            logger.error(f"Error setting webhook: {e}")
            return False
    
    async def start_bot(self):
        """Start the Telegram bot in webhook mode."""
        # Initialize application
        await self.application.initialize()
        
        # Set up scheduler
        await self.setup_scheduler()
        
        # Set up webhook
        webhook_success = await self.setup_webhook()
        if not webhook_success:
            logger.warning("Failed to register webhook. Bot may not receive updates.")
        
        # Start scheduler
        self.scheduler.start()
        
        logger.info("Bot started in webhook mode")
        
        return True
    
    async def stop_bot(self):
        """Stop the bot gracefully."""
        if self.scheduler:
            self.scheduler.shutdown()
        
        if self.application:
            await self.application.stop()
            await self.application.shutdown()
        
        logger.info("Bot stopped")
    
    def run_flask(self):
        """Run the Flask application."""
        port = int(os.environ.get("PORT", 8080))
        
        logger.info(f"Starting Flask server on port {port}")
        self.app.run(host="0.0.0.0", port=port)

def set_webhook():
    """Auto-register webhook on startup."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    app_url = os.environ.get("APPLICATION_URL")
    webhook_url = f"{app_url}/webhook"
    
    api_url = f"https://api.telegram.org/bot{token}/setWebhook"
    response = requests.post(api_url, json={"url": webhook_url})
    result = response.json()
    
    if result.get("ok"):
        print(f"✅ Webhook set successfully: {webhook_url}")
    else:
        print(f"❌ Webhook failed: {result}")

def main():
    """Main entry point."""
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
        logger.error("Please create a .env file with your bot token")
        return
    
    # Auto-register webhook on startup
    set_webhook()
    
    # Create and start bot
    bot = ForexSignalBot(token)
    
    try:
        # Start bot in async context
        bot.run_async(bot.start_bot())
        
        # Run Flask server
        bot.run_flask()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        bot.run_async(bot.stop_bot())

if __name__ == "__main__":
    main()
