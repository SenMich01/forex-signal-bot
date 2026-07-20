import os
import logging
from datetime import datetime, timezone
from aiohttp import web
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
# Render auto-injects RENDER_EXTERNAL_URL for every web service — no manual
# setup needed there. APPLICATION_URL is kept as a manual override for other
# hosts (or if you want to force a specific URL).
APP_URL = (
    os.environ.get("APPLICATION_URL")
    or os.environ.get("RENDER_EXTERNAL_URL")
    or ""
).rstrip("/")
PORT = int(os.environ.get("PORT", 8080))

if not TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN not set. Exiting.")
    raise SystemExit(1)

ptb = Application.builder().token(TOKEN).build()

VALID_PAIRS = ["USDJPY", "EURUSD", "GBPUSD", "XAUUSD",
               "USDCAD", "EURJPY", "GBPJPY"]


def _format_signal(signal: dict) -> str:
    """Convert a signal dict into a Telegram message."""
    pair = signal["pair"]
    direction = signal["direction"]
    strength = signal["strength"]

    d = "📈" if direction == "BUY" else "📉"
    c = "🟢" if direction == "BUY" else "🔴"
    s = {"STRONG": "✅", "MODERATE": "⚠️", "WEAK": "❌"}.get(strength, "⚠️")

    return (
        f"📊 SIGNAL — {pair} ({signal['timeframe']})\n\n"
        f"{d} Direction: {direction} {c}\n"
        f"💪 Strength: {strength} {s} "
        f"(Score: {signal['score']}/100)\n\n"
        f"💰 Entry:       {signal['entry']}\n"
        f"🛑 Stop Loss:   {signal['stop_loss']} "
        f"(-{signal['sl_pips']:.1f} pips)\n"
        f"🎯 Take Profit: {signal['take_profit']} "
        f"(+{signal['tp_pips']:.1f} pips)\n"
        f"⚖️ RR: {signal['rr_ratio']}\n\n"
        f"📉 RSI (14):  {signal['rsi']:.1f}\n"
        f"📶 ADX:       {signal['adx']:.1f}\n"
        f"📊 HTF Trend: {signal['htf_trend']}\n"
        f"📈 MACD:      {signal['macd_signal']}\n"
        f"🧩 Confluence: {signal.get('reasons', '')}\n"
        f"{signal.get('rn_note', '')}\n"
        f"⚠️ STRONG signals only for best results\n"
        f"⚠️ Risk 1-2% per trade only\n"
        f"⏱️ {signal['timestamp']}"
    )


async def start(update, context):
    await update.message.reply_text(
        "👋 Welcome to Forex Signal Bot!\n\n"
        "I monitor 7 forex pairs and generate high-probability "
        "pullback signals on M5 and H1 timeframes.\n\n"
        "📌 Pairs: USDJPY | EURUSD | GBPUSD\n"
        "XAUUSD | USDCAD | EURJPY | GBPJPY\n\n"
        "Use /help to see all commands."
    )


async def help_command(update, context):
    await update.message.reply_text(
        "📖 Commands:\n\n"
        "/start               — Welcome message\n"
        "/pairs               — List monitored pairs\n"
        "/signal EURUSD M5    — M5 signal for a pair\n"
        "/signal EURUSD H1    — H1 signal for a pair\n"
        "/signalall M5        — Scan all pairs on M5\n"
        "/signalall H1        — Scan all pairs on H1\n"
        "/status              — Bot status\n"
        "/debug EURUSD        — Test data fetch\n"
        "/webhookinfo         — Check Telegram webhook status\n"
        "/help                — This message"
    )


async def pairs_command(update, context):
    await update.message.reply_text(
        "📊 Monitored Pairs:\n\n"
        "1. USDJPY\n2. EURUSD\n3. GBPUSD\n"
        "4. XAUUSD\n5. USDCAD\n6. EURJPY\n7. GBPJPY\n\n"
        "Use /signal EURUSD M5 or /signal EURUSD H1 to check a pair."
    )


async def signal_command(update, context):
    from strategy import get_signal, is_market_open

    if len(context.args) < 1:
        await update.message.reply_text(
            "Example: /signal EURUSD M5\n"
            "or       /signal EURUSD H1"
        )
        return

    pair = context.args[0].upper()
    timeframe = context.args[1].upper() if len(context.args) > 1 else "M5"

    if pair not in VALID_PAIRS:
        await update.message.reply_text(
            f"❌ Invalid pair: {pair}\n\n"
            "Valid:\n" + "\n".join(VALID_PAIRS)
        )
        return

    if timeframe not in ("M5", "H1"):
        await update.message.reply_text(
            "❌ Invalid timeframe. Use M5 or H1."
        )
        return

    if not is_market_open():
        await update.message.reply_text(
            "🔴 Market Closed on weekends.\n"
            "⏰ Opens Sunday 22:00 UTC"
        )
        return

    await update.message.reply_text(f"🔍 Analyzing {pair} on {timeframe}...")

    try:
        signal = get_signal(pair, timeframe)

        if signal.get("error"):
            await update.message.reply_text(
                f"⚠️ {signal['message']}\n"
                f"Try /debug {pair}"
            )
            return

        if not signal.get("signal"):
            await update.message.reply_text(
                f"🔍 {pair} {timeframe}: {signal['message']}"
            )
            return

        await update.message.reply_text(_format_signal(signal))

    except Exception as e:
        logger.exception(f"signal error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def signalall_command(update, context):
    from strategy import get_signal, is_market_open

    timeframe = context.args[0].upper() if context.args else "M5"
    if timeframe not in ("M5", "H1"):
        await update.message.reply_text("❌ Use M5 or H1. Example: /signalall M5")
        return

    if not is_market_open():
        await update.message.reply_text(
            "🔴 Market Closed on weekends.\n"
            "⏰ Opens Sunday 22:00 UTC"
        )
        return

    await update.message.reply_text(f"🔍 Scanning all pairs on {timeframe}...")
    lines = [f"📊 MARKET SCAN — {timeframe}\n"]
    found = 0

    for pair in VALID_PAIRS:
        try:
            sig = get_signal(pair, timeframe)
            if sig.get("error"):
                lines.append(f"{pair} ⚠️ No data")
            elif sig.get("signal"):
                d = "📈" if sig["direction"] == "BUY" else "📉"
                s = {"STRONG": "✅", "MODERATE": "⚠️", "WEAK": "❌"}.get(
                    sig["strength"], "⚠️")
                lines.append(
                    f"{pair} {d} {sig['direction']} {sig['strength']} {s} "
                    f"({sig['score']}/100)"
                )
                found += 1
            else:
                lines.append(f"{pair} — {sig.get('message', 'No signal')}")
        except Exception as e:
            logger.exception(f"scan error {pair}: {e}")
            lines.append(f"{pair} ❌ Error")

    if found == 0:
        lines.append("\n🕸 No valid setups right now. Patience.")
    else:
        lines.append("\n✅STRONG=Trade ⚠️MODERATE=Careful")

    lines.append(f"⏱️ {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
    await update.message.reply_text("\n".join(lines))


async def status_command(update, context):
    await update.message.reply_text(
        f"✅ Online\n"
        f"📡 Webhook: Active\n"
        f"📈 Pairs: {len(VALID_PAIRS)}\n"
        f"⏱️ {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
    )


async def debug_command(update, context):
    from data_fetcher import get_candles
    pair = context.args[0].upper() if context.args else "EURUSD"
    if pair not in VALID_PAIRS:
        await update.message.reply_text(f"❌ Invalid pair: {pair}")
        return

    await update.message.reply_text(f"🔧 Testing {pair}...")
    try:
        m5 = get_candles(pair, "5m", "2d")
        h1 = get_candles(pair, "1h", "7d")
        h4 = get_candles(pair, "4h", "30d")
        await update.message.reply_text(
            f"✅ Data check for {pair}:\n"
            f"M5: {len(m5) if m5 is not None else 0} candles\n"
            f"H1: {len(h1) if h1 is not None else 0} candles\n"
            f"H4: {len(h4) if h4 is not None else 0} candles\n"
            f"Close: {float(m5.iloc[-1]['close']):.5f}\n"
            f"Time: {m5.index[-1]}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def webhookinfo_command(update, context):
    """Diagnostic: show Telegram's current webhook registration for this bot."""
    info = await ptb.bot.get_webhook_info()
    await update.message.reply_text(
        f"🔗 Webhook URL: {info.url or '(none set!)'}\n"
        f"📬 Pending updates: {info.pending_update_count}\n"
        f"❌ Last error: {info.last_error_message or 'None'}\n"
        f"🖥️ Configured APP_URL: {APP_URL or '(empty — this is the problem if URL above is blank)'}"
    )


async def unknown(update, context):
    await update.message.reply_text(
        "❓ Unknown command. Use /help"
    )


ptb.add_handler(CommandHandler("start",     start))
ptb.add_handler(CommandHandler("help",      help_command))
ptb.add_handler(CommandHandler("pairs",     pairs_command))
ptb.add_handler(CommandHandler("signal",    signal_command))
ptb.add_handler(CommandHandler("signalall", signalall_command))
ptb.add_handler(CommandHandler("status",    status_command))
ptb.add_handler(CommandHandler("debug",     debug_command))
ptb.add_handler(CommandHandler("webhookinfo", webhookinfo_command))
ptb.add_handler(MessageHandler(filters.COMMAND, unknown))


async def health(request):
    return web.Response(text="Bot is running")


async def webhook_handler(request):
    try:
        data = await request.json()
        logger.info(f"Update received: {data}")
        update = Update.de_json(data, ptb.bot)
        await ptb.process_update(update)
        logger.info("Update processed OK")
    except Exception as e:
        logger.exception(f"Webhook error: {e}")
    return web.Response(text="ok")


async def on_startup(app):
    await ptb.initialize()
    await ptb.start()

    # Register Telegram webhook if APPLICATION_URL is set
    if APP_URL:
        webhook_url = f"{APP_URL}/webhook"
        await ptb.bot.set_webhook(webhook_url)
        logger.info(f"✅ Webhook set to {webhook_url}")
    else:
        logger.warning("APPLICATION_URL not set; webhook not registered.")

    logger.info("✅ PTB started and ready")


async def on_shutdown(app):
    await ptb.stop()
    await ptb.shutdown()


def main():
    app = web.Application()
    app.router.add_get("/",         health)
    app.router.add_get("/health",   health)
    app.router.add_post("/webhook", webhook_handler)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    logger.info(f"Starting on port {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
