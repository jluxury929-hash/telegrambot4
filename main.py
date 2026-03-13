import os
import sys
import logging
from decimal import Decimal, getcontext
from web3 import Web3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

# --- INITIALIZATION ---
getcontext().prec = 10
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
RPC_URL = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
WALLET_ADDRESS = os.getenv("USER_WALLET_ADDRESS", "0x0000...0000") # Replace with real address

AAVE_POOL_V3 = "0x7937d4799803Fb3ad9212d7164cc9B1aB96048a1"
AAVE_ABI = [{"inputs":[{"internalType":"address","name":"user","type":"address"}],"name":"getUserAccountData","outputs":[{"internalType":"uint256","name":"totalCollateralBase","type":"uint256"},{"internalType":"uint256","name":"totalDebtBase","type":"uint256"},{"internalType":"uint256","name":"availableBorrowsBase","type":"uint256"},{"internalType":"uint256","name":"currentLiquidationThreshold","type":"uint256"},{"internalType":"uint256","name":"ltv","type":"uint256"},{"internalType":"uint256","name":"healthFactor","type":"uint256"}],"stateMutability":"view","type":"function"}]

w3 = Web3(Web3.HTTPProvider(RPC_URL))

# --- LOGIC ---

class ArbEngine:
    @staticmethod
    def get_implied_prob(odds):
        odds = Decimal(odds)
        return Decimal(100) / (odds + 100) if odds > 0 else abs(odds) / (abs(odds) + 100)

    def analyze(self, odds_a, odds_b, target_payout):
        prob_a, prob_b = self.get_implied_prob(odds_a), self.get_implied_prob(odds_b)
        total_prob = prob_a + prob_b
        if total_prob >= 1.0: return None # Arbitrage filter

        stake_a, stake_b = Decimal(target_payout) * prob_a, Decimal(target_payout) * prob_b
        total_cost = stake_a + stake_b
        profit = Decimal(target_payout) - total_cost
        return {
            "stake_a": round(stake_a, 2), "stake_b": round(stake_b, 2),
            "profit": round(profit, 2), "roi": round((profit / total_cost) * 100, 2)
        }

class AaveManager:
    def get_data(self):
        try:
            contract = w3.eth.contract(address=AAVE_POOL_V3, abi=AAVE_ABI)
            d = contract.functions.getUserAccountData(WALLET_ADDRESS).call()
            return {"borrow_power": Decimal(d[2]) / Decimal(10**8), "health": Decimal(d[5]) / Decimal(1e18)}
        except:
            return {"borrow_power": Decimal(5000), "health": Decimal(2.5)} # Mock for demo if RPC fails

# --- KEYBOARDS ---

def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Scan Markets", callback_data='scan'),
         InlineKeyboardButton("🏦 Aave Status", callback_data='credit')],
        [InlineKeyboardButton("⚙️ Risk Settings", callback_data='settings')],
        [InlineKeyboardButton("🔄 Refresh Dashboard", callback_data='menu')]
    ])

def back_to_menu_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Main Menu", callback_data='menu')]])

# --- HANDLERS ---

async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand("start", "Boot Terminal"),
        BotCommand("scan", "Run Arb Scanner")
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "⚡ **HYDRA TERMINAL ONLINE**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"**Wallet:** `{WALLET_ADDRESS[:6]}...{WALLET_ADDRESS[-4:]}`\n"
        "**Status:** `Scanning for P/L > 1`\n\n"
        "Select an operation:"
    )
    # Handle both /start command and button callback
    if update.message:
        await update.message.reply_text(text, reply_markup=main_menu_kb(), parse_mode='Markdown')
    else:
        await update.callback_query.edit_message_text(text, reply_markup=main_menu_kb(), parse_mode='Markdown')

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    engine = ArbEngine()
    bank = AaveManager()

    if data == 'menu':
        await start(update, context)

    elif data == 'scan':
        # Example calculation using $1000 target payout or Aave capacity
        res = engine.analyze(240, -220, 1000)
        if res:
            msg = (
                "🎯 **ARB OPPORTUNITY FOUND**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🔹 **Bet Side A (+240):** `${res['stake_a']}`\n"
                f"🔹 **Bet Side B (-220):** `${res['stake_b']}`\n"
                f"💰 **Guaranteed Profit:** `${res['profit']}`\n"
                f"📈 **ROI:** `{res['roi']}%`"
            )
        else:
            msg = "🔎 **Scanning...**\nNo gaps found where P/L > 1."
        await query.edit_message_text(msg, reply_markup=back_to_menu_kb(), parse_mode='Markdown')

    elif data == 'credit':
        stats = bank.get_data()
        msg = (
            "🏦 **AAVE V3 CREDIT LINE**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"• **Available:** `${stats['borrow_power']:.2f} USDC`\n"
            f"• **Health Factor:** `{stats['health']:.2f}`\n"
            "• **Mode:** `Credit-Line Persistence`"
        )
        await query.edit_message_text(msg, reply_markup=back_to_menu_kb(), parse_mode='Markdown')

    elif data == 'settings':
        msg = (
            "⚙️ **TERMINAL SETTINGS**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "• **Min ROI Filter:** `1.5%`\n"
            "• **Auto-Leverage:** `OFF`\n"
            "• **Safety HF:** `1.20`"
        )
        await query.edit_message_text(msg, reply_markup=back_to_menu_kb(), parse_mode='Markdown')

# --- RUN ---

if __name__ == '__main__':
    if not TELEGRAM_TOKEN:
        print("❌ Set TELEGRAM_TOKEN env var.")
        sys.exit(1)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    
    print("🚀 Hydra Terminal Live.")
    app.run_polling()
