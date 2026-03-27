"""
Main Telegram Forex Signal Bot (Webhook Mode).

Handles Telegram bot interactions, command processing, and scheduled scanning.
Runs as a Flask web server for webhook mode deployment.
"""

import logging
import os
import asyncio
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
from strategy import Signal

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
    
    def setup_routes(self):
        """Set up Flask routes."""
        
        @self.app.route('/webhook', methods=['POST'])
        def webhook():
            """Handle incoming webhook requests from Telegram."""
            try:
                json_str = request.get_data().decode('UTF-8')
                update = Update.de_json(json.loads(json_str), self.application.bot)
                asyncio.run(self.application.process_update(update))
                return jsonify({'status': 'ok'}), 200
            except Exception as e:
                logger.error(f"Error processing webhook: {e}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
        
        @self.app.route('/health', methods=['GET'])
        def health():
            """Health check endpoint."""
            return "Bot is running", 200
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        # Add subscriber
        self.scanner.add_subscriber(chat_id)
        
        welcome_message = f"""🤖 Welcome to {BOT_NAME}!
{BOT_DESCRIPTION}

I monitor 7 major Forex pairs and send real-time trading signals based on the M5 Scalper v3 strategy.

Available commands:
/start - Start receiving signals
/pairs - List monitored pairs
/signal <pair> - Get signal for specific pair
/signalall - Get signals for all pairs
/status - Bot status and last scan
/help - Show all commands

You will receive automatic signals every {SCAN_INTERVAL_MINUTES} minutes during trading sessions.

Trading sessions: London (07:00-16:00 UTC) and New York (13:00-21:00 UTC)"""
        
        await update.message.reply_text(welcome_message)
        logger.info(f"User {user.username} ({chat_id}) started the bot")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_text = f"""🆘 {BOT_NAME} Help

Available commands:
/start - Start receiving signals and subscribe to updates
/pairs - List all 7 monitored Forex pairs
/signal <pair> - Request signal for specific pair (e.g., /signal EURUSD)
/signalall - Get signals for all monitored pairs
/status - Show bot status and last scan time
/help - Show this help message

Trading Information:
• Pairs monitored: USDJPY, EURUSD, GBPUSD, XAUUSD, USDCAD, EURJPY, GBPJPY
• Timeframe: M5 (5-minute candles)
• Strategy: M5 Scalper v3 with EMA, RSI, and ATR indicators
• Sessions: London (07:00-16:00 UTC) and New York (13:00-21:00 UTC)
• Auto-scan: Every {SCAN_INTERVAL_MINUTES} minutes

Risk Management:
• Stop Loss and Take Profit levels provided
• Risk/Reward ratio validation
• Duplicate signal prevention (15-minute cooldown)
• Breakeven tips when applicable"""
        
        await update.message.reply_text(help_text)
    
    async def pairs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pairs command."""
        message = self.scanner.get_pairs_message()
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
        
        await update.message.reply_text(f"🔍 Analyzing {pair_symbol}...")
        
        try:
            signals = await self.scanner.manual_signal_request(pair_symbol)
            
            if signals:
                for signal in signals:
                    message = self.scanner.format_signal_message(signal)
                    await update.message.reply_text(message)
            else:
                pair_name = self.scanner.get_pair_name(pair_symbol)
                await update.message.reply_text(f"❌ No signals found for {pair_name} at this time.")
                
        except Exception as e:
            logger.error(f"Error in signal command: {e}")
            await update.message.reply_text("❌ Error generating signal. Please try again later.")
    
    async def signalall_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /signalall command."""
        await update.message.reply_text("🔍 Scanning all pairs for signals...")
        
        try:
            signals = await self.scanner.scan_and_generate_signals()
            
            if signals:
                for signal in signals:
                    message = self.scanner.format_signal_message(signal)
                    await update.message.reply_text(message)
            else:
                await update.message.reply_text("❌ No signals found at this time.")
                
        except Exception as e:
            logger.error(f"Error in signalall command: {e}")
            await update.message.reply_text("❌ Error scanning for signals. Please try again later.")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        message = self.scanner.get_status_message()
        await update.message.reply_text(message)
    
    async def send_signal_to_subscribers(self, signal: Signal):
        """Send signal to all subscribers."""
        message = self.scanner.format_signal_message(signal)
        
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
    
    async def register_webhook(self):
        """Register webhook with Telegram."""
        webhook_url = os.getenv('APPLICATION_URL', '')
        if not webhook_url:
            logger.error("APPLICATION_URL environment variable not set")
            return False
        
        webhook_endpoint = f"{webhook_url}/webhook"
        
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{self.token}/setWebhook",
                params={'url': webhook_endpoint}
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    logger.info(f"Webhook registered successfully: {webhook_endpoint}")
                    return True
                else:
                    logger.error(f"Failed to register webhook: {result}")
                    return False
            else:
                logger.error(f"Failed to register webhook: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error registering webhook: {e}")
            return False
    
    async def start_bot(self):
        """Start the Telegram bot in webhook mode."""
        self.application = Application.builder().token(self.token).build()
        
        # Add command handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("pairs", self.pairs_command))
        self.application.add_handler(CommandHandler("signal", self.signal_command))
        self.application.add_handler(CommandHandler("signalall", self.signalall_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        
        # Add error handler
        self.application.add_error_handler(self.error_handler)
        
        # Set up scheduler
        await self.setup_scheduler()
        
        # Register webhook
        webhook_success = await self.register_webhook()
        if not webhook_success:
            logger.warning("Failed to register webhook. Bot may not receive updates.")
        
        # Start the application
        await self.application.initialize()
        await self.application.start()
        
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
        port = int(os.getenv('PORT', 8080))
        
        logger.info(f"Starting Flask server on port {port}")
        self.app.run(host='0.0.0.0', port=port, debug=False)

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
    
    # Create and start bot
    bot = ForexSignalBot(token)
    
    try:
        # Start bot in async context
        asyncio.run(bot.start_bot())
        
        # Run Flask server
        bot.run_flask()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        asyncio.run(bot.stop_bot())

if __name__ == "__main__":
    main()
