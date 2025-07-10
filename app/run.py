#!/usr/bin/env python3
"""
Run script for the Telegram Time Tracker Bot
"""

import os
import sys
import logging
from tracker import main

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=os.getenv('LOG_LEVEL', 'INFO'),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run the main application
    try:
        main()
    except KeyboardInterrupt:
        print("\nBot stopped by user")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        sys.exit(1)