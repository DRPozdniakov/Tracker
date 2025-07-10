import os
import logging
from class_telegram_bot import TelegramBot

users_config={
    1794622246:"Shane_Hill"	,
    495992751:"Dmitry_Pozdniakov"	
}


def main():
    """Main entry point for the time tracker bot"""
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    GSHEET_KEY_PATH = os.getenv("GSHEET_KEY_PATH", "C:/Users/drpoz/OneDrive/Desktop/TelegramShops/Amazon/creds/google_creds.json")
    
    if not TOKEN:
        print("Error: TELEGRAM_TOKEN environment variable not set")
        exit(1)
    
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logger = logging.getLogger(__name__)
    
    bot = TelegramBot(token=TOKEN, gsheet_key_path=GSHEET_KEY_PATH, logger=logger)
    bot.run()


if __name__ == "__main__":
    main()