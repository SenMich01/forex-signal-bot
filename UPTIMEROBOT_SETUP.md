# UptimeRobot Setup Guide for Forex Signal Bot

## Overview
This guide explains how to set up UptimeRobot to keep your Forex Signal Bot alive on Render's free tier.

## Why UptimeRobot?
- Render's free tier spins down web services after 15 minutes of inactivity
- The built-in keep-alive mechanism helps but external monitoring provides additional reliability
- UptimeRobot is free and reliable for monitoring your bot's health

## Setup Instructions

### 1. Create UptimeRobot Account
1. Go to [UptimeRobot.com](https://uptimerobot.com/)
2. Sign up for a free account
3. Verify your email address

### 2. Add Monitor
1. Log in to your UptimeRobot account
2. Click "Add New Monitor"
3. Configure the monitor settings:

**Monitor Type:** HTTP(s)
**Monitor Friendly Name:** Forex Signal Bot
**URL:** `https://your-bot-name.onrender.com/health`
**Monitoring Interval:** 5 minutes (300 seconds)

### 3. Configure Alert Contacts
1. In UptimeRobot dashboard, go to "My Settings"
2. Add your email address under "Alert Contacts"
3. Set up notification preferences

### 4. Test the Setup
1. Visit your bot's health endpoint: `https://your-bot-name.onrender.com/health`
2. You should see a JSON response with status "ok"
3. UptimeRobot should show your monitor as "Online"

## Alternative: Multiple Monitors
For extra reliability, you can set up multiple monitors:

1. **Health Monitor:** `https://your-bot-name.onrender.com/health`
2. **Webhook Status Monitor:** `https://your-bot-name.onrender.com/webhook-status`
3. **Main Endpoint Monitor:** `https://your-bot-name.onrender.com/`

## Monitoring Endpoints

### `/health` - Basic Health Check
Returns basic service status and timestamp.

### `/webhook-status` - Webhook Verification
Returns webhook configuration status and expected URL.

### `/` - Main Health Check
Returns comprehensive status including webhook verification.

## Troubleshooting

### Monitor Shows "Down"
1. Check that your bot is deployed and running on Render
2. Verify the URL is correct
3. Check Render logs for any errors
4. Ensure environment variables are set correctly

### Frequent False Alarms
1. Increase monitoring interval to 10 minutes
2. Check if your bot is timing out
3. Review Render logs for performance issues

## Benefits of This Setup

1. **Automatic Wake-up:** UptimeRobot pings keep your service awake
2. **Health Monitoring:** Know immediately if your bot goes down
3. **Webhook Verification:** Monitor endpoint shows if webhook is properly configured
4. **Free Service:** UptimeRobot free tier is sufficient for this use case

## Render Environment Variables
Ensure these are set in your Render dashboard:
- `TELEGRAM_BOT_TOKEN` - Your bot token from @BotFather
- `RENDER_EXTERNAL_URL` - Should be auto-set by Render (e.g., https://your-bot.onrender.com)

## Expected Behavior
- Bot starts automatically when Render service wakes up
- Webhook is automatically registered on startup
- Keep-alive mechanism prevents spin-down
- UptimeRobot provides additional monitoring and wake-up calls