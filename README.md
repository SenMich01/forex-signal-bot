# Forex Signal Bot

A real-time Forex trading signal bot built with Python, using yfinance for market data and Telegram for signal distribution. Implements the M5 Scalper v3 strategy with EMA, RSI, and ATR indicators.

## Features

- **Real-time Signal Generation**: Monitors 7 major Forex pairs and generates signals based on technical indicators
- **Telegram Integration**: Sends signals to subscribers via Telegram bot
- **Smart Risk Management**: Includes Stop Loss, Take Profit, and Risk/Reward ratio validation
- **Trading Session Awareness**: Only generates signals during London and New York trading sessions
- **Duplicate Prevention**: 15-minute cooldown to prevent duplicate signals
- **Manual Signal Requests**: Users can request signals for specific pairs
- **Auto-scaling**: Scans all pairs every 5 minutes during trading sessions

## Monitored Pairs

The bot monitors these 7 major Forex pairs:
- USD/JPY
- EUR/USD
- GBP/USD
- XAU/USD (Gold)
- USD/CAD
- EUR/JPY
- GBP/JPY

## Strategy Overview

The M5 Scalper v3 strategy uses:
- **EMA Stack**: EMA8, EMA21, and EMA50 for trend direction
- **RSI**: For momentum and overbought/oversold conditions
- **ATR**: For volatility-based stop loss and take profit levels
- **Candle Analysis**: Body-to-range ratios for signal confirmation

### Buy Signal Conditions
1. EMA8 > EMA50 (bullish trend)
2. RSI dropped below 35 within last 5 candles (oversold)
3. RSI recovering: RSI > RSI[1] and RSI > RSI[2] and 35 < RSI < 60
4. Price near EMA50: low ≤ EMA50 + ATR×1.5 and close > EMA50 - ATR×0.5
5. Recaptured EMA21: close > EMA21 and previous candle low < EMA21
6. Strong bullish candle: bullBody > candleRange × 0.5
7. EMA50 flat or rising
8. Current time within trading sessions

### Sell Signal Conditions
1. EMA8 < EMA21 < EMA50 (bearish stack)
2. EMA21 and EMA50 slopes negative over last 5 candles
3. Price touched EMA21 within last 2 candles and close < EMA50
4. Clear of EMA50: close < EMA50 - ATR×0.3
5. RSI falling: RSI < RSI[2] and 35 < RSI < 60
6. Strong bearish candle: bearBody > candleRange × 0.5
7. Current time within trading sessions

## Installation

### Prerequisites
- Python 3.8+
- Telegram Bot Token (get from @BotFather)

### Setup

1. **Clone the repository**
```bash
git clone <repository-url>
cd forex-signal-bot
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure environment**
```bash
cp .env.example .env
```

Edit `.env` file with your Telegram bot token:
```bash
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
```

4. **Run the bot**
```bash
python bot.py
```

## Usage

### Telegram Commands

- `/start` - Subscribe to signals
- `/help` - Show help information
- `/pairs` - List monitored pairs
- `/signal <pair>` - Get signal for specific pair (e.g., `/signal EURUSD`)
- `/signalall` - Get signals for all pairs
- `/status` - Show bot status

### Signal Format

The bot sends formatted signals like this:

```
🔔 FOREX SIGNAL — EUR/USD
📈 Direction: BUY
💰 Entry Price: 1.08545
🛑 Stop Loss: 1.08320  (+22.5 pips)
🎯 Take Profit: 1.09000  (+45.5 pips)
⚖️ Risk/Reward: 1:2.0
📊 RSI: 42.5
⏰ Timeframe: M5 | Session: London/New York
💡 Tip: Move SL to breakeven once +1x ATR in profit
⏱️ Signal Time: 2024-01-15 14:30 UTC
```

## Configuration

### Trading Sessions
- **London Session**: 07:00-16:00 UTC
- **New York Session**: 13:00-21:00 UTC

### Scan Intervals
- **Auto-scan**: Every 5 minutes during trading sessions
- **Manual scans**: On-demand via Telegram commands

### Risk Management
- **Max Risk**: 1% of account per trade
- **Min Risk/Reward**: 1:1 ratio
- **Duplicate Cooldown**: 15 minutes

## Deployment

### Render.com (Recommended - Free Tier)

1. **Create Render account** and connect your GitHub repository
2. **Create Web Service** (NOT Background Worker) and select this repository
3. **Configure settings**:
   - Runtime: Python 3.11
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python bot.py`
4. **Add environment variables**:
   - `TELEGRAM_BOT_TOKEN`: Your bot token from @BotFather
   - `APPLICATION_URL`: Your Render app URL (e.g., `https://your-app-name.onrender.com`)
   - `PORT`: `8080` (default)
5. **Deploy**

### GitHub Setup

1. **Initialize Git** (if not already done):
   ```bash
   cd forex-signal-bot
   git init
   git add .
   git commit -m "Initial commit - forex signal bot"
   git branch -M main
   ```

2. **Create GitHub Repository**:
   - Go to github.com and create a new empty repo called `forex-signal-bot`
   - Copy the repo URL

3. **Push to GitHub**:
   ```bash
   git remote add origin <your-github-repo-url>
   git push -u origin main
   ```

### Heroku

1. **Install Heroku CLI** and login
2. **Create app**:
   ```bash
   heroku create your-app-name
   ```
3. **Set environment variables**:
   ```bash
   heroku config:set TELEGRAM_BOT_TOKEN=your_token
   heroku config:set APPLICATION_URL=https://your-app-name.herokuapp.com
   heroku config:set PORT=8080
   ```
4. **Deploy**:
   ```bash
   git push heroku main
   ```

### Getting Your Telegram Bot Token

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` command
3. Follow the instructions to create your bot
4. Copy the bot token and add it to your `.env` file or Render environment variables

### Local Development

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd forex-signal-bot
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env file with your Telegram bot token
   ```

4. **Run the bot**:
   ```bash
   python bot.py
   ```

### Updating Your Bot

After every code change, remember to:
```bash
git add .
git commit -m "your change description"
git push
```

This will trigger automatic redeployment on Render.

## Monitoring and Logging

The bot provides comprehensive logging:
- Signal generation events
- Telegram message delivery status
- Error handling and recovery
- Performance metrics

### Log Levels
- `DEBUG`: Detailed debugging information
- `INFO`: General information (recommended)
- `WARNING`: Warning messages
- `ERROR`: Error messages only

## Troubleshooting

### Common Issues

1. **Bot not responding**
   - Check internet connection
   - Verify Telegram bot token
   - Check logs for errors

2. **No signals generated**
   - Ensure current time is within trading sessions
   - Check market data availability
   - Verify strategy conditions are met

3. **Telegram messages not delivered**
   - Check if users have started the bot
   - Verify bot hasn't been blocked
   - Check Telegram API status

### Webhook Issues

If the bot is not responding to commands:

1. **Manual Webhook Reset**: Visit this URL in your browser (replace with your actual bot token and app URL):
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=https://your-app-name.onrender.com/webhook
   ```

2. **Check Webhook Status**: 
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo
   ```

3. **Verify Environment Variables**:
   - `TELEGRAM_BOT_TOKEN` is correct
   - `APPLICATION_URL` matches your Render app URL
   - `PORT` is set to `8080`

### Debug Mode

Enable debug mode in `.env`:
```bash
DEBUG=true
LOG_LEVEL=DEBUG
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Risk Disclaimer

⚠️ **Trading involves substantial risk and is not suitable for every investor. The signals provided by this bot are for educational and informational purposes only. Past performance is not indicative of future results. Always do your own research and never risk more than you can afford to lose.**

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Create an issue on GitHub
- Check the troubleshooting section
- Review the configuration options

## Changelog

### v1.0.0
- Initial release
- M5 Scalper v3 strategy implementation
- Telegram bot integration
- Real-time signal generation
- Risk management features