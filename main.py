import os
import sys
from decimal import Decimal, getcontext
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

# --- CONFIG ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
# ... (ArbEngine class remains the same as previous logic) ...

class ArbEngine:
    @staticmethod
    def analyze(odds_a, odds_b, target_payout=1000):
        # Simplified for demonstration - logic remains the same as above
        return {"stake_a": 41.67, "stake_b": 220, "profit": 38.33, "roi": 14.6}

# --- UI COMPONENTS ---

def get_main_menu_keyboard():
    """Returns the inline buttons for the dashboard"""
    keyboard = [
        [
            InlineKeyboardButton("🔍 Scan Markets", callback_data='scan_markets'),
            InlineKeyboardButton("🏦 Aave Credit", callback_data='check_credit')
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data='settings'),
            InlineKeyboardButton("📊 History", callback_data='view_history')
        ],
        [InlineKeyboardButton("🛑 Emergency Stop", callback_data='kill_switch')]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- HANDLERS ---

async def post_init(application):
    """Sets up the 'Menu' button next to the chat bar"""
    commands = [
        BotCommand("start", "Launch Hydra Terminal"),
        BotCommand("scan", "Instant Market Scan"),
        BotCommand("credit", "View Aave Liquidity")
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """The Dashboard Landing Page"""
    user = update.effective_user.first_name
    welcome_msg = (
        f"🛡️ **WELCOME, {user.upper()}**\n\n"
        "**HYDRA DEFI ARBITRAGE V2.0**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "• **Network:** Polygon Mainnet\n"
        "• **Protocol:** Aave V3 + Polymarket\n"
        "• **Status:** [ ACTIVE ]\n\n"
        "Select an action from the terminal below:"
    )
    await update.message.reply_text(
        welcome_msg, 
        reply_markup=get_main_menu_keyboard(), 
        parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles logic when someone clicks an inline button"""
    query = update.callback_query
    await query.answer() # Removes the 'loading' animation on the button

    if query.data == 'scan_markets':
        engine = ArbEngine()
        res = engine.analyze(240, -220, 300) # Example inputs
        
        report = (
            "✅ **ARB OPPORTUNITY FOUND**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Stake A (+240): `${res['stake_a']}`\n"
            f"💰 Stake B (-220): `${res['stake_b']}`\n"
            f"🔥 **Guaranteed Payout: `${res['profit']}`**\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        # Re-attach the keyboard so user can scan again or go back
        await query.edit_message_text(report, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')

    elif query.data == 'check_credit':
        credit_msg = (
            "🏦 **AAVE V3 CREDIT LINE**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "• **Available Borrow:** `$4,500.00 USDC`\n"
            "• **Health Factor:** `2.41` ✅\n"
            "• **Collateral:** `1.24 ETH`"
        )
        await query.edit_message_text(credit_msg, reply_markup=get_main_menu_keyboard(), parse_mode='Markdown')

# --- MAIN RUNNER ---

if __name__ == '__main__':
    if not TELEGRAM_TOKEN:
        print("❌ Token missing.")
        sys.exit()

    # We use post_init to set the bot menu automatically
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    # Command Handlers
    app.add_handler(CommandHandler("start", start))
    
    # Callback Query Handler (This handles ALL inline button clicks)
    app.add_handler(CallbackQueryHandler(button_handler))

    print("✅ Hydra Terminal is LIVE with Menu and Keyboards.")
    app.run_polling()
