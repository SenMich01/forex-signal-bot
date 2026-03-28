import os
import asyncio
import logging
import time
from aiohttp import web
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
APP_URL = os.environ.get("APPLICATION_URL")
PORT = int(os.environ.get("PORT", 8080))

# Global variables to track webhook status
webhook_registered = False
webhook_registration_failed = False

# ── Build PTB Application ─────────────────────────────
ptb_app = Application.builder().token(TOKEN).build()

# ── Command Handlers ──────────────────────────────────
async def start(update, context):
    try:
        await update.message.reply_text(
            "👋 Welcome to Forex Signal Bot!\n\n"
            "I monitor 7 forex pairs 24/5 and alert you\n"
            "when a high-probability trade setup is found.\n\n"
            "📌 Monitored Pairs:\n"
            "USDJPY | EURUSD | GBPUSD | XAUUSD\n"
            "USDCAD | EURJPY | GBPJPY\n\n"
            "Use /help to see all commands."
        )
        logger.info(f"User {update.effective_user.username} started the bot")
    except Exception as e:
        logger.error(f"Error in start command: {e}")

async def help_command(update, context):
    try:
        await update.message.reply_text(
            "📖 Available Commands:\n\n"
            "/start — Welcome message\n"
            "/pairs — List monitored pairs\n"
            "/signal EURUSD — Get signal for one pair\n"
            "/signalall — Scan all 7 pairs now\n"
            "/status — Bot status\n"
            "/debug EURUSD — Test data fetch\n"
            "/help — Show this message"
        )
    except Exception as e:
        logger.error(f"Error in help command: {e}")

async def pairs_command(update, context):
    try:
        await update.message.reply_text(
            "📊 Monitored Forex Pairs:\n\n"
            "1. USDJPY — US Dollar / Japanese Yen\n"
            "2. EURUSD — Euro / US Dollar\n"
            "3. GBPUSD — British Pound / US Dollar\n"
            "4. XAUUSD — Gold / US Dollar\n"
            "5. USDCAD — US Dollar / Canadian Dollar\n"
            "6. EURJPY — Euro / Japanese Yen\n"
            "7. GBPJPY — British Pound / Japanese Yen\n\n"
            "Use /signal EURUSD to check a specific pair."
        )
    except Exception as e:
        logger.error(f"Error in pairs command: {e}")

async def signal_command(update, context):
    try:
        from strategy import get_signal, is_market_open

        if not context.args:
            await update.message.reply_text(
                "Please specify a pair.\nExample: /signal EURUSD"
            )
            return

        pair = context.args[0].upper()
        valid_pairs = ["USDJPY","EURUSD","GBPUSD","XAUUSD",
                       "USDCAD","EURJPY","GBPJPY"]

        if pair not in valid_pairs:
            await update.message.reply_text(
                f"❌ Invalid pair: {pair}\n\n"
                f"Valid pairs:\n" + "\n".join(valid_pairs)
            )
            return

        if not is_market_open():
            await update.message.reply_text(
                "🔴 Market Closed\n\n"
                "Forex market is closed on weekends.\n"
                "⏰ Opens Monday 00:00 UTC"
            )
            return

        await update.message.reply_text(f"🔍 Analyzing {pair}...")

        signal = get_signal(pair)

        if signal.get("error"):
            await update.message.reply_text(
                f"⚠️ {signal['message']}\n\n"
                "Try again in a few minutes."
            )
            return

        direction_emoji = "📈" if signal["direction"] == "BUY" else "📉"
        color = "🟢" if signal["direction"] == "BUY" else "🔴"
        strength_emoji = {
            "STRONG": "✅",
            "MODERATE": "⚠️",
            "WEAK": "❌"
        }.get(signal["strength"], "⚠️")

        msg = (
            f"📊 FOREX SIGNAL — {pair}\n\n"
            f"{direction_emoji} Direction: {signal['direction']} {color}\n"
            f"💪 Strength: {signal['strength']} {strength_emoji} "
            f"(Score: {signal['score']}/100)\n\n"
            f"💰 Entry:       {signal['entry']}\n"
            f"🛑 Stop Loss:   {signal['stop_loss']}  "
            f"(-{signal['sl_pips']:.1f} pips)\n"
            f"🎯 Take Profit: {signal['take_profit']}  "
            f"(+{signal['tp_pips']:.1f} pips)\n"
            f"⚖️ Risk/Reward: {signal['rr_ratio']}\n\n"
            f"📉 RSI (14):    {signal['rsi']:.1f}\n"
            f"📊 H1 Trend:    {signal['h1_trend']}\n"
            f"📈 MACD:        {signal['macd_signal']}\n\n"
            f"⚠️ Risk Warning:\n"
            f"- Only risk 1-2% per trade\n"
            f"- Move SL to breakeven at +1x ATR profit\n"
            f"- WEAK signals = skip or small size\n\n"
            f"⏱️ Generated: {signal['timestamp']}"
        )
        await update.message.reply_text(msg)
    except Exception as e:
        logger.error(f"Error in signal command: {e}")
        await update.message.reply_text("❌ Error processing signal. Please try again later.")

async def signalall_command(update, context):
    try:
        from strategy import get_signal, is_market_open

        if not is_market_open():
            await update.message.reply_text(
                "🔴 Market Closed on weekends.\n"
                "⏰ Opens Monday 00:00 UTC"
            )
            return

        await update.message.reply_text("🔍 Scanning all 7 pairs...")

        pairs = ["USDJPY","EURUSD","GBPUSD","XAUUSD",
                 "USDCAD","EURJPY","GBPJPY"]

        lines = ["📊 FULL MARKET SCAN\n"]
        for pair in pairs:
            signal = get_signal(pair)
            if signal.get("error"):
                lines.append(f"{pair}  ⚠️ No data")
            else:
                d = "📈" if signal["direction"] == "BUY" else "📉"
                s = {"STRONG":"✅","MODERATE":"⚠️","WEAK":"❌"}.get(
                    signal["strength"], "⚠️")
                lines.append(
                    f"{pair}  {d} {signal['direction']}  "
                    f"{signal['strength']} {s}"
                )

        lines.append("\n✅ STRONG = High confidence")
        lines.append("⚠️ MODERATE = Manage risk")
        lines.append("❌ WEAK = Avoid")
        lines.append("\nUse /signal EURUSD for full details.")
        lines.append(
            f"⏱️ Scanned: "
            f"{__import__('datetime').datetime.utcnow().strftime('%H:%M UTC')}"
        )

        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        logger.error(f"Error in signalall command: {e}")
        await update.message.reply_text("❌ Error scanning pairs. Please try again later.")

async def status_command(update, context):
    try:
        global webhook_registered, webhook_registration_failed
        
        webhook_status = "✅ Active" if webhook_registered else "❌ Not Registered"
        if webhook_registration_failed:
            webhook_status += " (Failed)"
            
        await update.message.reply_text(
            f"✅ Bot Status: Online\n"
            f"📡 Webhook: {webhook_status}\n"
            f"📈 Pairs Monitored: 7\n"
            f"🔧 Last Check: {time.strftime('%H:%M:%S UTC', time.gmtime())}"
        )
    except Exception as e:
        logger.error(f"Error in status command: {e}")

async def debug_command(update, context):
    try:
        from data_fetcher import get_m5_candles, get_h1_candles
        pair = context.args[0].upper() if context.args else "EURUSD"
        await update.message.reply_text(f"🔧 Testing {pair}...")
        m5 = get_m5_candles(pair)
        h1 = get_h1_candles(pair)
        if m5 is not None and not m5.empty:
            await update.message.reply_text(
                f"✅ Data OK!\n"
                f"M5 candles: {len(m5)}\n"
                f"H1 candles: {len(h1) if h1 is not None else 0}\n"
                f"Latest close: {m5.iloc[-1]['close']:.5f}\n"
                f"Latest time: {m5.index[-1]}"
            )
        else:
            await update.message.reply_text(
                f"❌ Data fetch FAILED for {pair}\n"
                "Market may be closed or API issue."
            )
    except Exception as e:
        logger.error(f"Error in debug command: {e}")
        await update.message.reply_text("❌ Error running debug. Please try again later.")

async def unknown(update, context):
    try:
        await update.message.reply_text(
            "❓ Unknown command.\nUse /help to see available commands."
        )
    except Exception as e:
        logger.error(f"Error in unknown command: {e}")

# ── Register Handlers ─────────────────────────────────
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("help", help_command))
ptb_app.add_handler(CommandHandler("pairs", pairs_command))
ptb_app.add_handler(CommandHandler("signal", signal_command))
ptb_app.add_handler(CommandHandler("signalall", signalall_command))
ptb_app.add_handler(CommandHandler("status", status_command))
ptb_app.add_handler(CommandHandler("debug", debug_command))
ptb_app.add_handler(MessageHandler(filters.COMMAND, unknown))

# ── aiohttp Routes ────────────────────────────────────
async def health(request):
    return web.Response(text="Bot is running ✅")

async def webhook_handler(request):
    try:
        data = await request.json()
        update = Update.de_json(data, ptb_app.bot)
        await ptb_app.process_update(update)
        return web.Response(text="ok")
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return web.Response(text="error", status=500)

async def check_webhook_status(request):
    """Endpoint to check webhook registration status"""
    global webhook_registered, webhook_registration_failed
    
    status = {
        "webhook_registered": webhook_registered,
        "webhook_registration_failed": webhook_registration_failed,
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
    }
    return web.json_response(status)

# ── Webhook Registration with Retry Logic ───────────────
async def register_webhook_with_retry(max_retries=5, delay=2):
    """Register webhook with retry logic and exponential backoff"""
    global webhook_registered, webhook_registration_failed
    
    webhook_url = f"{APP_URL}/webhook"
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting webhook registration (attempt {attempt + 1}/{max_retries})")
            await ptb_app.bot.set_webhook(webhook_url)
            webhook_registered = True
            webhook_registration_failed = False
            logger.info(f"✅ Webhook successfully registered: {webhook_url}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Webhook registration failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                wait_time = delay * (2 ** attempt)  # Exponential backoff
                logger.info(f"Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
    
    # If all retries failed
    webhook_registration_failed = True
    logger.error("❌ Failed to register webhook after all retry attempts")
    return False

# ── Startup / Shutdown ────────────────────────────────
async def on_startup(app):
    global webhook_registered, webhook_registration_failed
    
    try:
        logger.info("🚀 Starting Forex Signal Bot...")
        await ptb_app.initialize()
        await ptb_app.start()
        
        # Register webhook with retry logic
        success = await register_webhook_with_retry()
        
        if not success:
            logger.warning("⚠️ Webhook registration failed, but bot will continue running")
            logger.warning("You may need to manually register the webhook using:")
            logger.warning(f"curl -X POST https://api.telegram.org/bot{TOKEN}/setWebhook?url={APP_URL}/webhook")
    
    except Exception as e:
        logger.error(f"❌ Error during startup: {e}")
        webhook_registration_failed = True

async def on_shutdown(app):
    try:
        logger.info("🛑 Shutting down Forex Signal Bot...")
        await ptb_app.stop()
        await ptb_app.shutdown()
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

# ── aiohttp App ───────────────────────────────────────
def main():
    aio_app = web.Application()
    
    # Routes
    aio_app.router.add_get("/", health)
    aio_app.router.add_get("/health", health)
    aio_app.router.add_get("/webhook-status", check_webhook_status)
    aio_app.router.add_post("/webhook", webhook_handler)
    
    # Startup/Shutdown
    aio_app.on_startup.append(on_startup)
    aio_app.on_shutdown.append(on_shutdown)

    logger.info(f"🌐 Starting web server on port {PORT}")
    logger.info(f"📍 Application URL: {APP_URL}")
    logger.info(f"🔗 Webhook URL: {APP_URL}/webhook")
    
    web.run_app(aio_app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()