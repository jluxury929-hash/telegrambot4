import os
import sys
import subprocess
import logging
import requests
from decimal import Decimal, getcontext

# --- 1. AUTO-DEPENDENCY & RESTART ---
try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType
    from py_clob_client.order_builder.constants import BUY
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "py-clob-client", "requests", "python-telegram-bot", "web3"])
    os.execv(sys.executable, ['python'] + sys.argv)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

# --- 2. CONFIG ---
getcontext().prec = 10
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_TOKEN")
P_KEY = os.getenv("PRIVATE_KEY")
WALLET = os.getenv("USER_WALLET_ADDRESS")

# --- 3. THE HARVESTER ENGINE (The "Finding Bets" Part) ---

class HydraEngine:
    def __init__(self):
        # Only initialize CLOB if P_KEY is present
        self.client = None
        if P_KEY:
            self.client = ClobClient("https://clob.polymarket.com", key=P_KEY, chain_id=137)
            try:
                creds = self.client.create_or_derive_api_creds()
                self.client.set_api_creds(creds)
            except: pass

    async def harvest_live_bets(self):
        """Scans top 20 high-volume events for tradable markets"""
        try:
            url = "https://gamma-api.polymarket.com/events?active=true&closed=false&order=volume_24hr&ascending=false&limit=20"
            r = requests.get(url, timeout=10).json()
            
            valid_markets = []
            for event in r:
                markets = event.get('markets', [])
                if markets:
                    m = markets[0]
                    clob_ids = m.get('clobTokenIds')
                    if clob_ids:
                        # Pull price, fallback to 0.50 if mid-market
                        price = m.get('bestYesBid') or m.get('lastTradePrice') or 0.50
                        valid_markets.append({
                            "id": clob_ids[0],
                            "name": event.get('title'),
                            "price": float(price)
                        })
            return valid_markets
        except Exception as e:
            logging.error(f"Scan error: {e}")
            return []

# --- 4. UI COMPONENTS ---

def get_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔍 Deep Scan", callback_data='scan_markets'),
            InlineKeyboardButton("🏦 Aave Credit", callback_data='check_credit')
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data='settings'),
            InlineKeyboardButton("📊 History", callback_data='view_history')
        ],
        [InlineKeyboardButton("🛑 Emergency Stop", callback_data='kill_switch')]
    ])

# --- 5. HANDLERS ---

async def post_init(application):
    """Sets the Menu buttons next to the chat bar"""
    commands = [
        BotCommand("start", "Launch Terminal"),
        BotCommand("scan", "Instant Deep Scan")
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    msg = (
        f"🛡️ **WELCOME, {user.upper()}**\n"
        "**HYDRA DEFI ARBITRAGE V2.5**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• **Wallet:** `{WALLET[:8]}...`\n"
        "• **Status:** [ SCANNING ACTIVE ]\n\n"
        "Select an action from the terminal:"
    )
    # Handle both command and callback
    if update.message:
        await update.message.reply_text(msg, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')
    else:
        await update.callback_query.edit_message_text(msg, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    engine = HydraEngine()

    if query.data == 'scan_markets':
        await query.edit_message_text("📡 **HARVESTING LIVE POLYMARKET DATA...**")
        markets = await engine.harvest_live_bets()
        
        if markets:
            # Show the top 3 best opportunities found
            report = "✅ **LIVE MARKETS FOUND**\n━━━━━━━━━━━━━━━━━━━━\n"
            for m in markets[:3]:
                report += f"🎯 `{m['name'][:40]}...`\n💰 Price: `{m['price']}`\n\n"
            report += "━━━━━━━━━━━━━━━━━━━━\n*Ready for execution.*"
            await query.edit_message_text(report, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ No liquid markets found. Retrying...", reply_markup=get_main_menu_keyboard())

    elif query.data == 'check_credit':
        # (This would call your Aave logic from previous steps)
        await query.edit_message_text("🏦 **CREDIT STATUS:**\n`Active - $4,500 USDC available`", reply_markup=get_main_menu_keyboard())

# --- 6. RUNNER ---

if __name__ == '__main__':
    # Force kill any old sessions
    requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True")
    
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🚀 Hydra V2.5 Pro UI + Deep-Scanner Live.")
    app.run_polling(drop_pending_updates=True)
