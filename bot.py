import os
import asyncio
import logging
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

# ── Build PTB Application ─────────────────────────────
ptb_app = Application.builder().token(TOKEN).build()

# ── Command Handlers ──────────────────────────────────
async def start(update, context):
    await update.message.reply_text(
        "👋 Welcome to Forex Signal Bot!\n\n"
        "I monitor 7 forex pairs 24/5 and alert you\n"
        "when a high-probability trade setup is found.\n\n"
        "📌 Monitored Pairs:\n"
        "USDJPY | EURUSD | GBPUSD | XAUUSD\n"
        "USDCAD | EURJPY | GBPJPY\n\n"
        "Use /help to see all commands."
    )

async def help_command(update, context):
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

async def pairs_command(update, context):
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

async def signal_command(update, context):
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

async def signalall_command(update, context):
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

async def status_command(update, context):
    await update.message.reply_text(
        "✅ Bot Status: Online\n"
        "📡 Webhook: Active\n"
        "📈 Pairs Monitored: 7\n"
    )

async def debug_command(update, context):
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

async def unknown(update, context):
    await update.message.reply_text(
        "❓ Unknown command.\nUse /help to see available commands."
    )

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
    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)
    return web.Response(text="ok")

# ── Startup / Shutdown ────────────────────────────────
async def on_startup(app):
    await ptb_app.initialize()
    await ptb_app.start()
    webhook_url = f"{APP_URL}/webhook"
    await ptb_app.bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook set: {webhook_url}")

async def on_shutdown(app):
    await ptb_app.stop()
    await ptb_app.shutdown()

# ── aiohttp App ───────────────────────────────────────
def main():
    aio_app = web.Application()
    aio_app.router.add_get("/", health)
    aio_app.router.add_get("/health", health)
    aio_app.router.add_post("/webhook", webhook_handler)
    aio_app.on_startup.append(on_startup)
    aio_app.on_shutdown.append(on_shutdown)

    web.run_app(aio_app, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()