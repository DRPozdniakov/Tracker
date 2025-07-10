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
        self.config_step = None  # For config command flow
        self.temp_config = {}  # Temporary storage for config being set

    def get_main_keyboard(self):
        """Generate main keyboard with Clock In/Clock Out buttons"""
        if self.is_clocked_in:
            keyboard = [
                [InlineKeyboardButton("🔴 Clock Out", callback_data="clock_out")]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("🟢 Clock In", callback_data="clock_in")],
                [InlineKeyboardButton("⚙️ Config", callback_data="config")]
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
        self.version = "v1.1"
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Set up all command and message handlers"""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("config", self.config_command))
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
        
        # Get user configuration and display project details
        user_config = self.time_tracker.get_user_config(user_id)
        
        if user_config:
            project_info = (
                f"📋 **Project**: {user_config.get('project_name', 'Not set')}\n"
                f"🏭 **Location**: {user_config.get('project_location', 'Not set')}\n"
                f"👷 **Contractor**: {user_config.get('contractor_name', 'Not set')}\n"
                f"🍽️ **Lunch Break**: {user_config.get('lunch_duration', 'Not set')}\n\n"
            )
        else:
            project_info = "⚠️ **No project configuration found**\nPlease set up your project details first.\n\n"
        
        welcome_message = (
            f"🕐 **Time Tracker {self.version}**\n\n"
            f"Hello {user.first_name}! 👋\n\n"
            f"{project_info}"
            "Choose an option below:"
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
            "/status - Check your current clock status\n"
            "/config - Configure project details\n\n"
            "**How to use:**\n"
            "🟢 Clock In - Start your work session\n"
            "🔴 Clock Out - End your work session\n"
            "📊 View Records - See your recent time records\n"
            "⚙️ Config - Set project name, location, and contractor\n\n"
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
    
    async def config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /config command"""
        user_id = update.effective_user.id
        
        if user_id not in self.registered_users:
            self.registered_users[user_id] = BotUser(update)
        
        user = self.registered_users[user_id]
        
        # Get current config
        current_config = self.time_tracker.get_user_config(user_id)
        
        config_message = "⚙️ **Project Configuration**\n\n"
        
        if current_config:
            config_message += "**Current Settings:**\n"
            config_message += f"📋 Project Name: {current_config.get('project_name', 'Not set')}\n"
            config_message += f"🏭 Project Location: {current_config.get('project_location', 'Not set')}\n"
            config_message += f"👷 Contractor Name: {current_config.get('contractor_name', 'Not set')}\n"
            config_message += f"🍽️ Lunch Break: {current_config.get('lunch_duration', 'Not set')}\n\n"
        else:
            config_message += "**No configuration found**\n\n"
        
        config_message += "To update your configuration, please provide the following details:\n\n"
        config_message += "1️⃣ Project Name\n2️⃣ Project Location (Factory)\n3️⃣ Contractor Name\n4️⃣ Lunch Break Duration (e.g., 30 minutes)\n\n"
        config_message += "Please send the **Project Name** first:"
        
        user.config_step = "project_name"
        user.temp_config = {}
        
        await update.message.reply_html(config_message)
    
    def _calculate_duration(self, start_time):
        """Calculate duration from start time to now"""        
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
                    "⚠️ You are already clocked in!",
                    reply_markup=user.get_main_keyboard()
                )
            else:
                user.awaiting_location = True
                user.pending_action = "clock_in"
                
                location_keyboard = ReplyKeyboardMarkup(
                    [[KeyboardButton("📍 Clock In with Location", request_location=True)]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                )
                
                await query.edit_message_text("🟢 **Clock In**\n\nTap the button below:")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="📍 Clock In with Location",
                    reply_markup=location_keyboard
                )
        
        elif action == "clock_out":
            if not user.is_clocked_in:
                await query.edit_message_text(
                    "⚠️ You are not clocked in!",
                    reply_markup=user.get_main_keyboard()
                )
            else:
                user.awaiting_location = True
                user.pending_action = "clock_out"
                
                location_keyboard = ReplyKeyboardMarkup(
                    [[KeyboardButton("📍 Clock Out with Location", request_location=True)]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                )
                
                await query.edit_message_text("🔴 **Clock Out**\n\nTap the button below:")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="📍 Clock Out with Location",
                    reply_markup=location_keyboard
                )
        
        elif action == "config":
            # Handle config button click
            current_config = self.time_tracker.get_user_config(user_id)
            
            config_message = "⚙️ **Project Configuration**\n\n"
            
            if current_config:
                config_message += "**Current Settings:**\n"
                config_message += f"📋 Project Name: {current_config.get('project_name', 'Not set')}\n"
                config_message += f"🏭 Project Location: {current_config.get('project_location', 'Not set')}\n"
                config_message += f"👷 Contractor Name: {current_config.get('contractor_name', 'Not set')}\n\n"
            else:
                config_message += "**No configuration found**\n\n"
            
            config_message += "To update your configuration, please provide the following details:\n\n"
            config_message += "1️⃣ Project Name\n2️⃣ Project Location (Factory)\n3️⃣ Contractor Name\n\n"
            config_message += "Please send the **Project Name** first:"
            
            user.config_step = "project_name"
            user.temp_config = {}
            
            await query.edit_message_text(config_message)
    
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
            
            # Get user configuration for display
            user_config = self.time_tracker.get_user_config(user_id)
            config_info = ""
            if user_config:
                config_info = (
                    f"📋 Project: {user_config.get('project_name', 'Not set')}\n"
                    f"🏭 Location: {user_config.get('project_location', 'Not set')}\n"
                    f"👷 Contractor: {user_config.get('contractor_name', 'Not set')}\n"
                )
            
            success_message = (
                f"{config_info}\n"
                f"🟢 **Clocked In! Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                
            )
            
        elif user.pending_action == "clock_out":
            self.time_tracker.add_record(
                user_id=user_id,
                username=user.username,
                action="clock_out",
                latitude=latitude,
                longitude=longitude
            )
            
            # Calculate work duration before clearing last_clock_in
            duration = ""
            if user.last_clock_in:
                duration = f"\nWork Duration: {self._calculate_duration(user.last_clock_in)}"
            
            # Get user configuration for display
            user_config = self.time_tracker.get_user_config(user_id)
            config_info = ""
            if user_config:
                config_info = (
                    f"📋 Project: {user_config.get('project_name', 'Not set')}\n"
                    f"🏭 Location: {user_config.get('project_location', 'Not set')}\n"
                    f"👷 Contractor: {user_config.get('contractor_name', 'Not set')}\n"
                )
            
            success_message = (
                "🔴 **Successfully Clocked Out!**\n\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Location: {latitude:.4f}, {longitude:.4f}{duration}\n\n"
                f"{config_info}"
                "Great work today! 🎉"
            )
            
            user.is_clocked_in = False
            user.last_clock_in = None
        
        # Reset location awaiting state
        user.awaiting_location = False
        user.pending_action = None
        
        # Hide the location keyboard
        from telegram import ReplyKeyboardRemove
        await update.message.reply_html(
            success_message,
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Send new message with main keyboard
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text="Choose an option:",
            reply_markup=user.get_main_keyboard()
        )
    
    async def text_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages"""
        user_id = update.effective_user.id
        
        if user_id not in self.registered_users:
            await update.message.reply_text("Please start with /start first.")
            return
        
        user = self.registered_users[user_id]
        
        # Handle config step-by-step process
        if user.config_step:
            text = update.message.text.strip()
            
            if user.config_step == "project_name":
                user.temp_config["project_name"] = text
                user.config_step = "project_location"
                await update.message.reply_html(
                    f"✅ Project Name set to: **{text}**\n\n"
                    "Now please send the **Project Location** (Factory name/location):"
                )
            
            elif user.config_step == "project_location":
                user.temp_config["project_location"] = text
                user.config_step = "contractor_name"
                await update.message.reply_html(
                    f"✅ Project Location set to: **{text}**\n\n"
                    "Finally, please send the **Contractor Name**:"
                )
            
            elif user.config_step == "contractor_name":
                user.temp_config["contractor_name"] = text
                user.config_step = "lunch_duration"
                await update.message.reply_html(
                    f"✅ Contractor Name set to: **{text}**\n\n"
                    "Finally, please send the **Lunch Break Duration** (e.g., 30 minutes, 1 hour, or 0 for no lunch break):"
                )
            
            elif user.config_step == "lunch_duration":
                user.temp_config["lunch_duration"] = text
                user.temp_config["username"] = user.username  # Add Telegram username
                
                # Save configuration
                self.time_tracker.save_user_config(user_id, user.temp_config)
                
                config_summary = (
                    "✅ **Configuration Saved Successfully!**\n\n"
                    "**Your Settings:**\n"
                    f"📋 Project Name: {user.temp_config['project_name']}\n"
                    f"🏭 Project Location: {user.temp_config['project_location']}\n"
                    f"👷 Contractor Name: {user.temp_config['contractor_name']}\n"
                    f"🍽️ Lunch Break: {user.temp_config['lunch_duration']}\n\n"
                    "These settings will be used in your time tracking reports."
                )
                
                # Reset config state
                user.config_step = None
                user.temp_config = {}
                
                await update.message.reply_html(
                    config_summary,
                    reply_markup=user.get_main_keyboard()
                )
            
            return
        
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
            try:
                if update.message:
                    await update.message.reply_text(
                        "An unexpected error occurred. Please try again or contact support."
                    )
                elif update.callback_query:
                    await update.callback_query.answer()
                    await update.callback_query.edit_message_text(
                        "An unexpected error occurred. Please try again or contact support."
                    )
            except Exception as e:
                self.logger.error(f"Error in error handler: {e}")
    
    def run(self) -> None:
        """Start the bot"""
        try:
            self.logger.info(f"Starting Time Tracker Bot {self.version}")
            self.application.run_polling(allowed_updates=Update.ALL_TYPES)
        except Exception as e:
            self.logger.error(f"Error starting bot: {e}")

