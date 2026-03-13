import os
import requests
import logging
from web3 import Web3
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- CONFIGURATION ---
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
POLYGON_RPC = os.getenv("POLYGON_RPC", "https://polygon-rpc.com")

# Aave V3 Pool & USDC on Polygon
AAVE_V3_POOL = "0x7937d4799803FbF533473445d88fD65d629412e2"
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
account = w3.eth.account.from_key(PRIVATE_KEY)

# --- AAVE LOGIC ---
AAVE_ABI = '[{"inputs":[{"internalType":"address","name":"user","type":"address"}],"name":"getUserAccountData","outputs":[{"internalType":"uint256","name":"totalCollateralBase","type":"uint256"},{"internalType":"uint256","name":"totalDebtBase","type":"uint256"},{"internalType":"uint256","name":"availableBorrowsBase","type":"uint256"},{"internalType":"uint256","name":"currentLiquidationThreshold","type":"uint256"},{"internalType":"uint256","name":"ltv","type":"uint256"},{"internalType":"uint256","name":"healthFactor","type":"uint256"}],"stateMutability":"view","type":"function"}]'

def get_credit_line():
    contract = w3.eth.contract(address=AAVE_V3_POOL, abi=AAVE_ABI)
    data = contract.functions.getUserAccountData(account.address).call()
    return {
        "available_usdc": data[2] / 1e8,
        "health": data[5] / 1e18
    }

# --- POLYMARKET SCANNER ---
def scan_markets():
    url = "https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=50"
    resp = requests.get(url).json()
    arbs = []
    for m in resp:
        if 'outcomePrices' not in m or len(m['outcomePrices']) < 2:
            continue
        
        p_yes = float(m['outcomePrices'][0])
        p_no = float(m['outcomePrices'][1])
        total_prob = p_yes + p_no

        # The "P/L NOT Equal 1" Filter (Profit guaranteed if < 1)
        if 0.1 < total_prob < 0.992: # 0.8% margin for slippage
            arbs.append({
                "title": m['question'],
                "yes_price": p_yes,
                "no_price": p_no,
                "roi": (1 / total_prob) - 1,
                "prob": total_prob,
                "ids": m.get('clobTokenIds', [])
            })
    return sorted(arbs, key=lambda x: x['roi'], reverse=True)

# --- TELEGRAM INTERFACE ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Hydra Arb Bot Live.\nUse /scan to check credit and gaps.")

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    credit = get_credit_line()
    arbs = scan_markets()

    if not arbs:
        await update.message.reply_text("🔎 No profitable gaps found right now.")
        return

    msg = f"💳 **Credit:** ${credit['available_usdc']:.2f} | **Health:** {credit['health']:.2f}\n\n"
    for i, arb in enumerate(arbs[:3]):
        # Calculate stake based on 80% of available credit
        total_stake = credit['available_usdc'] * 0.8
        stake_yes = (arb['yes_price'] / arb['prob']) * total_stake
        stake_no = (arb['no_price'] / arb['prob']) * stake_total
        
        msg += (
            f"🎯 *{arb['title']}*\n"
            f"ROI: **{arb['roi']:.2%}**\n"
            f"Action: Buy YES ${stake_yes:.2f} | Buy NO ${stake_no:.2f}\n\n"
        )
    await update.message.reply_text(msg, parse_mode='Markdown')

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))
    app.run_polling()
