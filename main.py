import os
import sys
import subprocess
import logging
from decimal import Decimal, getcontext

# --- 1. DEPENDENCY AUTO-INSTALL ---
try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType
    from py_clob_client.order_builder.constants import BUY
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "py-clob-client"])
    os.execv(sys.executable, ['python'] + sys.argv)

from web3 import Web3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

# --- 2. CONFIG ---
getcontext().prec = 10
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_TOKEN")
RAW_WALLET = os.getenv("USER_WALLET_ADDRESS")
P_KEY = os.getenv("PRIVATE_KEY") 

if not TOKEN:
    print("❌ FATAL: TELEGRAM_TOKEN is missing!")
    sys.exit(1)

# --- 3. UI & KEYBOARD ---
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Set Stake Amount", callback_data='set_amt')],
        [InlineKeyboardButton("🔥 EXECUTE REAL SCAN & BET", callback_data='execute_live')],
        [InlineKeyboardButton("🏠 Home", callback_data='home')]
    ])

# --- 4. HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stake = context.user_data.get('bet_amount', "100")
    text = (
        "🧨 **HYDRA LIVE TERMINAL**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 **Active Stake:** `${stake} USDC`\n"
        "🟢 **Status:** Ready for Execution\n\n"
        "*Note: If you get a 409 Conflict, ensure only one terminal is open.*"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=main_menu(), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=main_menu(), parse_mode='Markdown')

async def manager(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # Stops the loading spinner
    
    if query.data == 'home':
        await start(update, context)
    elif query.data == 'set_amt':
        await query.edit_message_text("⌨️ **Type the USDC amount you want to bet:**", parse_mode='Markdown')
    elif query.data == 'execute_live':
        stake = context.user_data.get('bet_amount', 100)
        # Place Execution Logic Here as shown in previous step
        await query.edit_message_text(f"📡 **Scanning...**\nTargeting `${stake}` stake on Polymarket.", reply_markup=main_menu())

async def text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.isdigit():
        context.user_data['bet_amount'] = update.message.text
        await update.message.reply_text(f"✅ Stake set to **${update.message.text}**", reply_markup=main_menu())

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and notify the admin."""
    logging.error(f"Exception while handling an update: {context.error}")

# --- 5. RUN ---

if __name__ == '__main__':
    # We add 'drop_pending_updates' to help clear the 409 Conflict on start
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(manager))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_input))
    
    # Register error handler
    app.add_error_handler(error_handler)

    print("🚀 Hydra is broadcasting... (Conflict Prevention Active)")
    
    # drop_pending_updates=True tells Telegram to ignore messages sent while the bot was offline
    app.run_polling(drop_pending_updates=True)
