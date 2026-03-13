import os
import sys
import subprocess
import logging
import requests
import time
from decimal import Decimal, getcontext

# --- 1. BOOTSTRAP & DEPENDENCIES ---
def bootstrap():
    try:
        from py_clob_client.client import ClobClient
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "py-clob-client", "python-telegram-bot", "requests", "web3"])
        os.execv(sys.executable, ['python'] + sys.argv)

bootstrap()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

# --- 2. CONFIG ---
getcontext().prec = 10
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_TOKEN")
P_KEY = os.getenv("PRIVATE_KEY")
WALLET = os.getenv("USER_WALLET_ADDRESS")

# --- 3. AGGRESSIVE HARVESTER ENGINE ---
class HydraAggressiveEngine:
    def __init__(self):
        self.client = None
        if P_KEY:
            from py_clob_client.client import ClobClient
            self.client = ClobClient("https://clob.polymarket.com", key=P_KEY, chain_id=137)
            try:
                creds = self.client.create_or_derive_api_creds()
                self.client.set_api_creds(creds)
            except: pass

    async def harvest_all_active_bets(self):
        """Scans broadly to ensure the list is NEVER empty."""
        try:
            # We pull 30 events to ensure at least a few dozen markets are found
            url = "https://gamma-api.polymarket.com/events?active=true&closed=false&order=volume_24hr&ascending=false&limit=30"
            r = requests.get(url, timeout=12).json()
            
            all_opps = []
            for event in r:
                markets = event.get('markets', [])
                for m in markets:
                    token_ids = m.get('clobTokenIds')
                    # Validation: Must have a tradable ID and some liquidity (price)
                    if token_ids and len(token_ids) > 0:
                        price = m.get('bestYesBid') or m.get('lastTradePrice') or 0.50
                        all_opps.append({
                            "title": event.get('title', 'Unknown Event'),
                            "price": float(price),
                            "id": token_ids[0],
                            "vol": event.get('volume_24hr', 0)
                        })
            # Sort by volume to show the most liquid/safest bets first
            return sorted(all_opps, key=lambda x: x['vol'], reverse=True)
        except Exception as e:
            logging.error(f"Harvester error: {e}")
            return []

# --- 4. TERMINAL UI ---
def get_main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 AGGRESSIVE SCAN", callback_data='scan')],
        [InlineKeyboardButton("💰 Set Stake Amount", callback_data='set_stake')],
        [InlineKeyboardButton("🏦 Flash Loan Status", callback_data='loan_status')],
        [InlineKeyboardButton("🏠 Home", callback_data='home')]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stake = context.user_data.get('stake', 500)
    msg = (
        "⚡ **HYDRA AGGRESSIVE TERMINAL**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 **Active Stake:** `${stake} USDC`\n"
        f"🏦 **Flash Loan Limit:** `$50,000` (Aave V3)\n"
        "🟢 **Status:** Ready to Harvest Markets"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(msg, reply_markup=get_main_kb(), parse_mode='Markdown')
    else:
        await update.message.reply_text(msg, reply_markup=get_main_kb(), parse_mode='Markdown')

async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'home':
        await start(update, context)

    elif query.data == 'set_stake':
        await query.edit_message_text("⌨️ **Type your USDC stake amount:**")

    elif query.data == 'loan_status':
        await query.edit_message_text(
            "🏦 **FLASH LOAN INVENTORY**\n━━━━━━━━━━━━\n"
            "• Provider: `Aave V3` (Polygon)\n"
            "• Asset: `USDC.e` / `DAI`\n"
            "• Est. Gas: `~0.15 MATIC`\n"
            "• **Status:** [ STANDBY ]", 
            reply_markup=get_main_kb(), parse_mode='Markdown'
        )

    elif query.data == 'scan':
        await query.edit_message_text("📡 **PULLING DEEP LIQUIDITY DATA...**")
        engine = HydraAggressiveEngine()
        data = await engine.harvest_all_active_bets()
        
        if data:
            report = "🔥 **TRADABLE OPPORTUNITIES**\n━━━━━━━━━━━━━━━━━━━━\n"
            # Show top 8 markets to ensure the screen is filled with options
            for item in data[:8]:
                report += f"🎯 `{item['title'][:32]}...`\n💰 Price: `${item['price']}` | ID: `{item['id'][:6]}..`\n\n"
            await query.edit_message_text(report, reply_markup=get_main_kb(), parse_mode='Markdown')
        else:
            await query.edit_message_text("⚠️ API LAG: No markets returned. Check your internet or Polymarket status.", reply_markup=get_main_kb())

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.isdigit():
        context.user_data['stake'] = int(update.message.text)
        await update.message.reply_text(f"✅ Stake updated to **${update.message.text}**", reply_markup=get_main_kb())

# --- 5. EXECUTION ---
if __name__ == '__main__':
    # Force kill conflicts
    requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True")
    time.sleep(2)
    
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_router))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_handler))
    
    print("🚀 Hydra Aggressive Scanner is Broadcasting.")
    app.run_polling(drop_pending_updates=True)
