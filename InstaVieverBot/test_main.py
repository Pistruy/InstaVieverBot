import os
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram import Update

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Test bot is running!")

def main():
    print("Starting test bot...")
    TOKEN = os.getenv('BOT_TOKEN')
    print(f"BOT_TOKEN: {TOKEN}")
    if not TOKEN:
        raise ValueError("BOT_TOKEN не встановлено")
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    print("Starting polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
