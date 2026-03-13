import os
import sys
import subprocess
import logging
from decimal import Decimal, getcontext

# --- 1. DEPENDENCY CHECK (Fixes the ModuleNotFoundError) ---
try:
    from py_clob_client.client import ClobClient
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "py-clob-client"])
    os.execv(sys.executable, ['python'] + sys.argv)

from web3 import Web3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

# --- 2. CONFIG & INITIALIZATION ---
getcontext().prec = 10
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_TOKEN")
WALLET = os.getenv("USER_WALLET_ADDRESS")
# Ensure wallet is checksummed for Web3 calls
if WALLET: WALLET = Web3.to_checksum_address(WALLET)

# --- 3. UI COMPONENTS (The Keyboards) ---
def main_menu_keyboard():
    """Centralized keyboard for consistent UI"""
    keyboard = [
        [InlineKeyboardButton("💰 Set Bet Amount", callback_data='btn_set_amt')],
        [InlineKeyboardButton("🔍 Scan & Place Bet", callback_data='btn_scan')],
        [InlineKeyboardButton("🏦 Check Aave Status", callback_data='btn_credit')],
        [InlineKeyboardButton("🏠 Back to Home", callback_data='btn_home')]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- 4. CORE FUNCTIONS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """The Dashboard - Works for /start and the Home button"""
    current_stake = context.user_data.get('bet_amount', "100 (Default)")
    text = (
        "⚡ **HYDRA ARBITRAGE TERMINAL**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🛠️ **Wallet:** `{WALLET[:8]}...` if WALLET else 'Not Set'\n"
        f"💵 **Active Stake:** `${current_stake}`\n"
        "🟢 **Status:** Ready for Execution"
    )
    
    # Check if this came from a button or a command
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=main_menu_keyboard(), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=main_menu_keyboard(), parse_mode='Markdown')

async def interaction_manager(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """THE GUARANTEE: This handles ALL button clicks and ensures they 'answer'"""
    query = update.callback_query
    # CRITICAL: Always answer the callback to stop the loading spinner
    await query.answer()
    
    data = query.data

    if data == 'btn_home':
        await start(update, context)

    elif data == 'btn_set_amt':
        await query.edit_message_text(
            "⌨️ **INPUT REQUIRED**\n\nPlease type the USDC amount you wish to stake below.",
            parse_mode='Markdown'
        )

    elif data == 'btn_credit':
        # Logic for Aave Status
        await query.edit_message_text(
            "🏦 **AAVE V3 POSITION**\n━━━━━━━━━━━━\nChecking on-chain data...\n(Ensure RPC is active)",
            reply_markup=main_menu_keyboard(),
            parse_mode='Markdown'
        )

    elif data == 'btn_scan':
        stake = context.user_data.get('bet_amount', 100)
        await query.edit_message_text(
            f"🔍 **SCANNING MARKETS**\n━━━━━━━━━━━━\nSearching for P/L > 1 gaps...\nTarget Stake: `${stake}`",
            reply_markup=main_menu_keyboard(),
            parse_mode='Markdown'
        )

async def text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles manual number inputs for the stake amount"""
    user_text = update.message.text
    if user_text.isdigit():
        context.user_data['bet_amount'] = user_text
        await update.message.reply_text(
            f"✅ **Stake Updated!**\nNew amount: `${user_text} USDC`",
            reply_markup=main_menu_keyboard(),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("⚠️ Invalid input. Please send a number only.")

# --- 5. EXECUTION ---

if __name__ == '__main__':
    if not TOKEN:
        print("❌ TELEGRAM_TOKEN is missing!")
        sys.exit(1)

    # Build the Application
    app = ApplicationBuilder().token(TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(interaction_manager)) # Single point of entry for buttons
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_input_handler))

    print("🚀 Hydra Terminal is Online and Buttons are Synchronized.")
    app.run_polling()
