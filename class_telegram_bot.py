import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters
from class_gsheets_handler import TimeTracker

class BotUser:
    """User session management for time tracking"""
    
    def __init__(self, update: Update):
        self.user_id = update.effective_user.id
        self.user = update.effective_user
        self.chat_id = int(update.effective_chat.id)
        self.username = self.user.username or self.user.first_name
        self.is_clocked_in = False
        self.last_clock_in = None
        self.awaiting_location = False
        self.pending_action = None  # 'clock_in' or 'clock_out'

    def get_main_keyboard(self):
        """Generate main keyboard with Clock In/Clock Out buttons"""
        if self.is_clocked_in:
            keyboard = [
                [InlineKeyboardButton("🔴 Clock Out", callback_data="clock_out")],
                [InlineKeyboardButton("📊 View Records", callback_data="view_records")]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("🟢 Clock In", callback_data="clock_in")],
                [InlineKeyboardButton("📊 View Records", callback_data="view_records")]
            ]
        return InlineKeyboardMarkup(keyboard)

class TelegramBot:
    """Main Telegram bot class for time tracking"""
    
    def __init__(self, token: str, gsheet_key_path: str, logger=None):
        self.token = token
        self.logger = logger or logging.getLogger(__name__)
        self.application = Application.builder().token(token).build()
        self.registered_users = {}
        self.time_tracker = TimeTracker(gsheet_key_path)
        self.version = "v1.0"
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Set up all command and message handlers"""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        self.application.add_handler(MessageHandler(filters.LOCATION, self.location_handler))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_handler))
        self.application.add_error_handler(self.error_handler)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command"""
        user = update.effective_user
        user_id = user.id
        
        if user_id not in self.registered_users:
            self.registered_users[user_id] = BotUser(update)
            self.logger.info(f"New user registered: {user.username or user.first_name} (ID: {user_id})")
        
        # Check last action to determine current status
        last_action = self.time_tracker.get_last_action(user_id)
        if last_action:
            action, timestamp = last_action
            self.registered_users[user_id].is_clocked_in = (action == "clock_in")
            if action == "clock_in":
                self.registered_users[user_id].last_clock_in = timestamp
        
        welcome_message = (
            f"🕐 *Welcome to Time Tracker {self.version}!* 🕐\n\n"
            f"Hello {user.first_name}! 👋\n\n"
            "This bot helps you track your work hours with location verification.\n\n"
            "📍 **Important**: You'll need to share your location when clocking in/out.\n\n"
            "Use the buttons below to get started:"
        )
        
        reply_markup = self.registered_users[user_id].get_main_keyboard()
        await update.message.reply_html(welcome_message, reply_markup=reply_markup)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command"""
        help_message = (
            f"🕐 *Time Tracker {self.version} Help* 🕐\n\n"
            "**Commands:**\n"
            "/start - Start the bot and see main menu\n"
            "/help - Show this help message\n"
            "/status - Check your current clock status\n\n"
            "**How to use:**\n"
            "🟢 Clock In - Start your work session\n"
            "🔴 Clock Out - End your work session\n"
            "📊 View Records - See your recent time records\n\n"
            "**Note:** You must share your location when clocking in/out for verification."
        )
        await update.message.reply_html(help_message)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command"""
        user_id = update.effective_user.id
        
        if user_id not in self.registered_users:
            self.registered_users[user_id] = BotUser(update)
        
        # Check current status from database
        last_action = self.time_tracker.get_last_action(user_id)
        if last_action:
            action, timestamp = last_action
            is_clocked_in = (action == "clock_in")
            
            if is_clocked_in:
                status_message = (
                    f"🟢 **Status: CLOCKED IN**\n\n"
                    f"Started: {timestamp}\n"
                    f"Duration: {self._calculate_duration(timestamp)}"
                )
            else:
                status_message = (
                    f"🔴 **Status: CLOCKED OUT**\n\n"
                    f"Last action: {timestamp}"
                )
        else:
            status_message = "❓ **Status: No records found**\n\nUse /start to begin tracking your time."
        
        await update.message.reply_html(status_message)
    
    def _calculate_duration(self, start_time):
        """Calculate duration from start time to now"""
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        
        duration = datetime.now() - start_time
        hours = duration.seconds // 3600
        minutes = (duration.seconds % 3600) // 60
        return f"{hours}h {minutes}m"
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle button callbacks"""
        query = update.callback_query
        user_id = update.effective_user.id
        action = query.data
        
        if user_id not in self.registered_users:
            self.registered_users[user_id] = BotUser(update)
        
        user = self.registered_users[user_id]
        
        await query.answer()
        
        if action == "clock_in":
            if user.is_clocked_in:
                await query.edit_message_text(
                    "⚠️ You are already clocked in!\n\nPlease clock out first before clocking in again.",
                    reply_markup=user.get_main_keyboard()
                )
            else:
                user.awaiting_location = True
                user.pending_action = "clock_in"
                
                location_keyboard = ReplyKeyboardMarkup(
                    [[KeyboardButton("📍 Share Location", request_location=True)]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                )
                
                await query.edit_message_text(
                    "🟢 **Clock In Process**\n\n"
                    "Please share your location to complete the clock in process.\n\n"
                    "Tap the button below to share your location:"
                )
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="📍 Please share your location:",
                    reply_markup=location_keyboard
                )
        
        elif action == "clock_out":
            if not user.is_clocked_in:
                await query.edit_message_text(
                    "⚠️ You are not clocked in!\n\nPlease clock in first before clocking out.",
                    reply_markup=user.get_main_keyboard()
                )
            else:
                user.awaiting_location = True
                user.pending_action = "clock_out"
                
                location_keyboard = ReplyKeyboardMarkup(
                    [[KeyboardButton("📍 Share Location", request_location=True)]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                )
                
                await query.edit_message_text(
                    "🔴 **Clock Out Process**\n\n"
                    "Please share your location to complete the clock out process.\n\n"
                    "Tap the button below to share your location:"
                )
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="📍 Please share your location:",
                    reply_markup=location_keyboard
                )
        
        elif action == "view_records":
            records = self.time_tracker.get_user_records(user_id)
            if records:
                records_text = "📊 **Your Recent Records:**\n\n"
                for record in records:
                    action_emoji = "🟢" if record[0] == "clock_in" else "🔴"
                    records_text += f"{action_emoji} {record[0].title()}: {record[1]}\n"
                    if record[2] and record[3]:
                        records_text += f"📍 Location: {record[2]:.4f}, {record[3]:.4f}\n"
                    records_text += "\n"
            else:
                records_text = "📊 **No Records Found**\n\nStart tracking your time by clocking in!"
            
            await query.edit_message_text(
                records_text,
                reply_markup=user.get_main_keyboard()
            )
    
    async def location_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle location messages"""
        user_id = update.effective_user.id
        
        if user_id not in self.registered_users:
            await update.message.reply_text("Please start with /start first.")
            return
        
        user = self.registered_users[user_id]
        
        if not user.awaiting_location:
            await update.message.reply_text("Location not requested at this time.")
            return
        
        location = update.message.location
        latitude = location.latitude
        longitude = location.longitude
        
        # Process the pending action
        if user.pending_action == "clock_in":
            self.time_tracker.add_record(
                user_id=user_id,
                username=user.username,
                action="clock_in",
                latitude=latitude,
                longitude=longitude
            )
            user.is_clocked_in = True
            user.last_clock_in = datetime.now()
            
            success_message = (
                "🟢 **Successfully Clocked In!**\n\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Location: {latitude:.4f}, {longitude:.4f}\n\n"
                "Have a productive day! 💪"
            )
            
        elif user.pending_action == "clock_out":
            self.time_tracker.add_record(
                user_id=user_id,
                username=user.username,
                action="clock_out",
                latitude=latitude,
                longitude=longitude
            )
            
            # Calculate work duration
            duration = ""
            if user.last_clock_in:
                duration = f"\nWork Duration: {self._calculate_duration(user.last_clock_in)}"
            
            user.is_clocked_in = False
            user.last_clock_in = None
            
            success_message = (
                "🔴 **Successfully Clocked Out!**\n\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Location: {latitude:.4f}, {longitude:.4f}{duration}\n\n"
                "Great work today! 🎉"
            )
        
        # Reset location awaiting state
        user.awaiting_location = False
        user.pending_action = None
        
        await update.message.reply_html(
            success_message,
            reply_markup=user.get_main_keyboard()
        )
    
    async def text_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages"""
        user_id = update.effective_user.id
        
        if user_id not in self.registered_users:
            await update.message.reply_text("Please start with /start first.")
            return
        
        user = self.registered_users[user_id]
        
        if user.awaiting_location:
            await update.message.reply_text(
                "Please share your location using the button provided, or send /start to restart."
            )
        else:
            await update.message.reply_html(
                "Use the buttons below to clock in/out:",
                reply_markup=user.get_main_keyboard()
            )
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors"""
        self.logger.error(f"An error occurred: {context.error}")
        
        if update and isinstance(update, Update):
            await update.message.reply_text(
                "An unexpected error occurred. Please try again or contact support."
            )
    
    def run(self) -> None:
        """Start the bot"""
        try:
            self.logger.info(f"Starting Time Tracker Bot {self.version}")
            self.application.run_polling(allowed_updates=Update.ALL_TYPES)
        except Exception as e:
            self.logger.error(f"Error starting bot: {e}")

