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

TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN")
APP_URL = os.environ.get("APPLICATION_URL", "").rstrip("/")
PORT    = int(os.environ.get("PORT", 8080))

ptb = Application.builder().token(TOKEN).build()

async def start(update, context):
    await update.message.reply_text(
        "👋 Welcome to Forex Signal Bot!\n\n"
        "I monitor 7 forex pairs 24/5.\n\n"
        "📌 Pairs: USDJPY | EURUSD | GBPUSD\n"
        "XAUUSD | USDCAD | EURJPY | GBPJPY\n\n"
        "Use /help to see all commands."
    )

async def help_command(update, context):
    await update.message.reply_text(
        "📖 Commands:\n\n"
        "/start     — Welcome message\n"
        "/pairs     — List monitored pairs\n"
        "/signal EURUSD — Get signal\n"
        "/signalall — Scan all 7 pairs\n"
        "/status    — Bot status\n"
        "/debug EURUSD  — Test data fetch\n"
        "/help      — This message"
    )

async def pairs_command(update, context):
    await update.message.reply_text(
        "📊 Monitored Pairs:\n\n"
        "1. USDJPY\n2. EURUSD\n3. GBPUSD\n"
        "4. XAUUSD\n5. USDCAD\n6. EURJPY\n7. GBPJPY\n\n"
        "Use /signal EURUSD to check a pair."
    )

async def signal_command(update, context):
    from strategy import get_signal, is_market_open

    if not context.args:
        await update.message.reply_text(
            "Example: /signal EURUSD"
        )
        return

    pair = context.args[0].upper()
    valid = ["USDJPY","EURUSD","GBPUSD","XAUUSD",
             "USDCAD","EURJPY","GBPJPY"]

    if pair not in valid:
        await update.message.reply_text(
            f"❌ Invalid pair: {pair}\n\n"
            "Valid:\n" + "\n".join(valid)
        )
        return

    if not is_market_open():
        await update.message.reply_text(
            "🔴 Market Closed on weekends.\n"
            "⏰ Opens Monday 00:00 UTC"
        )
        return

    await update.message.reply_text(f"🔍 Analyzing {pair}...")

    try:
        signal = get_signal(pair)

        if signal.get("error"):
            await update.message.reply_text(
                f"⚠️ {signal['message']}\n"
                f"Try /debug {pair}"
            )
            return

        d = "📈" if signal["direction"] == "BUY" else "📉"
        c = "🟢" if signal["direction"] == "BUY" else "🔴"
        s = {"STRONG":"✅","MODERATE":"⚠️","WEAK":"❌"}.get(
            signal["strength"],"⚠️")

        msg = (
            f"📊 SIGNAL — {pair}\n\n"
            f"{d} Direction: {signal['direction']} {c}\n"
            f"💪 Strength: {signal['strength']} {s} "
            f"(Score: {signal['score']}/100)\n\n"
            f"💰 Entry:       {signal['entry']}\n"
            f"🛑 Stop Loss:   {signal['stop_loss']} "
            f"(-{signal['sl_pips']:.1f} pips)\n"
            f"🎯 Take Profit: {signal['take_profit']} "
            f"(+{signal['tp_pips']:.1f} pips)\n"
            f"⚖️ RR: {signal['rr_ratio']}\n\n"
            f"📉 RSI: {signal['rsi']:.1f}\n"
            f"📊 H1 Trend: {signal['h1_trend']}\n"
            f"📈 MACD: {signal['macd_signal']}\n\n"
            f"⚠️ Risk 1-2% per trade only\n"
            f"⏱️ {signal['timestamp']}"
        )
        await update.message.reply_text(msg)

    except Exception as e:
        logger.exception(f"signal error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def signalall_command(update, context):
    from strategy import get_signal, is_market_open

    if not is_market_open():
        await update.message.reply_text(
            "🔴 Market Closed on weekends.\n"
            "⏰ Opens Monday 00:00 UTC"
        )
        return

    await update.message.reply_text("🔍 Scanning all pairs...")
    pairs = ["USDJPY","EURUSD","GBPUSD","XAUUSD",
             "USDCAD","EURJPY","GBPJPY"]
    lines = ["📊 MARKET SCAN\n"]

    for pair in pairs:
        try:
            sig = get_signal(pair)
            if sig.get("error"):
                lines.append(f"{pair} ⚠️ No data")
            else:
                d = "📈" if sig["direction"] == "BUY" else "📉"
                s = {"STRONG":"✅","MODERATE":"⚠️","WEAK":"❌"}.get(
                    sig["strength"],"⚠️")
                lines.append(f"{pair} {d} {sig['direction']} {sig['strength']} {s}")
        except:
            lines.append(f"{pair} ❌ Error")

    lines.append("\n✅STRONG=Trade ⚠️MODERATE=Careful ❌WEAK=Skip")
    lines.append(f"⏱️ {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
    await update.message.reply_text("\n".join(lines))

async def status_command(update, context):
    await update.message.reply_text(
        f"✅ Online\n"
        f"📡 Webhook: Active\n"
        f"📈 Pairs: 7\n"
        f"⏱️ {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
    )

async def debug_command(update, context):
    from data_fetcher import get_m5_candles, get_h1_candles
    pair = context.args[0].upper() if context.args else "EURUSD"
    await update.message.reply_text(f"🔧 Testing {pair}...")
    try:
        m5 = get_m5_candles(pair)
        h1 = get_h1_candles(pair)
        if m5 is not None and not m5.empty:
            await update.message.reply_text(
                f"✅ Data OK!\n"
                f"M5: {len(m5)} candles\n"
                f"H1: {len(h1) if h1 is not None else 0} candles\n"
                f"Close: {float(m5.iloc[-1]['close']):.5f}\n"
                f"Time: {m5.index[-1]}\n"
                f"Cols: {list(m5.columns)}"
            )
        else:
            await update.message.reply_text(
                f"❌ No data for {pair}\n"
                "Market may be closed."
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

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