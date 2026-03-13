import os
import logging
import requests
from web3 import Web3
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Official Polymarket SDK
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

# --- CONFIGURATION ---
# Use Railway Environment Variables
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
POLYGON_RPC = os.getenv("POLYGON_RPC", "https://polygon-rpc.com")

AAVE_V3_POOL_ADDRESS = "0x7937d4799803FbF533473445d88fD65d629412e2"
AAVE_ABI = [
    {"inputs":[{"internalType":"address","name":"user","type":"address"}],"name":"getUserAccountData","outputs":[
        {"internalType":"uint256","name":"totalCollateralBase","type":"uint256"},
        {"internalType":"uint256","name":"totalDebtBase","type":"uint256"},
        {"internalType":"uint256","name":"availableBorrowsBase","type":"uint256"},
        {"internalType":"uint256","name":"currentLiquidationThreshold","type":"uint256"},
        {"internalType":"uint256","name":"ltv","type":"uint256"},
        {"internalType":"uint256","name":"healthFactor","type":"uint256"}
    ],"stateMutability":"view","type":"function"}
]

w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))

# Initialize Polymarket Trading Client
# host=137 is Polygon Mainnet
trading_client = ClobClient(
    host="https://clob.polymarket.com", 
    key=PRIVATE_KEY, 
    chain_id=137
)
# Authenticate (Railway will store these in memory)
trading_client.set_api_creds(trading_client.create_or_derive_api_creds())

# --- ARBITRAGE SCANNER ---

def get_market_gaps():
    url = "https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=100"
    try:
        response = requests.get(url).json()
        valid_arbs = []
        for m in response:
            # We need clobTokenIds to actually place the trade later
            if 'outcomePrices' not in m or 'clobTokenIds' not in m:
                continue
            
            p_yes = float(m['outcomePrices'][0])
            p_no = float(m['outcomePrices'][1])
            total_prob = p_yes + p_no

            if 0.1 < total_prob < 0.995: 
                valid_arbs.append({
                    "title": m['question'],
                    "yes_price": p_yes,
                    "no_price": p_no,
                    "yes_token": m['clobTokenIds'][0],
                    "no_token": m['clobTokenIds'][1],
                    "prob": total_prob,
                    "roi": (1 / total_prob) - 1
                })
        return sorted(valid_arbs, key=lambda x: x['roi'], reverse=True)
    except Exception as e:
        return []

# --- BOT COMMANDS ---

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallet = trading_client.address # Uses the address from your private key
    arbs = get_market_gaps()
    
    # Check Aave Borrowing Power
    contract = w3.eth.contract(address=AAVE_V3_POOL_ADDRESS, abi=AAVE_ABI)
    data = contract.functions.getUserAccountData(wallet).call()
    borrow_usd = data[2] / 1e8
    
    if not arbs:
        await update.message.reply_text("🔎 No P/L < 1 opportunities found.")
        return

    report = f"💰 **Credit Line:** ${borrow_usd:.2f} USDC\n\n"
    for i, arb in enumerate(arbs[:3]):
        report += (
            f"ID: {i} | **ROI: {arb['roi']:.2%}**\n"
            f"📍 {arb['title']}\n"
            f"Commands: `/execute {i}`\n\n"
        )
    
    context.user_data['latest_arbs'] = arbs
    await update.message.reply_text(report, parse_mode='Markdown')

async def execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executes both sides of the arbitrage trade using your Private Key"""
    try:
        index = int(context.args[0])
        arb = context.user_data['latest_arbs'][index]
        
        # Calculate amount to spend (Example: $10 total for testing)
        # In production, you would pull from borrow_usd
        total_spend = 10.0 
        amt_yes = (arb['yes_price'] / arb['prob']) * total_spend
        amt_no = (arb['no_price'] / arb['prob']) * total_spend

        await update.message.reply_text(f"🚀 Executing Trade on: {arb['title']}...")

        # 1. Place YES Trade
        order_yes = trading_client.create_order(OrderArgs(
            price=arb['yes_price'] + 0.01, # 1 cent slippage buffer
            size=amt_yes / arb['yes_price'],
            side=BUY,
            token_id=arb['yes_token']
        ))
        trading_client.post_order(order_yes, OrderType.GTC)

        # 2. Place NO Trade
        order_no = trading_client.create_order(OrderArgs(
            price=arb['no_price'] + 0.01,
            size=amt_no / arb['no_price'],
            side=BUY,
            token_id=arb['no_token']
        ))
        trading_client.post_order(order_no, OrderType.GTC)

        await update.message.reply_text("✅ Success! Both sides of the arbitrage have been placed.")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Execution Failed: {str(e)}")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("execute", execute))
    app.run_polling()
