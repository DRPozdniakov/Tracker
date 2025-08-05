import os
import logging
import pytz
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
        self.version = "v1.108"
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Set up all command and message handlers"""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("config", self.config_command))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        self.application.add_handler(MessageHandler(filters.LOCATION, self.location_handler))
        self.application.add_handler(MessageHandler(filters.VOICE, self.voice_handler))
        self.application.add_handler(MessageHandler(filters.PHOTO, self.image_handler))
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
                # Parse the time string and create a datetime for today
                try:
                    from datetime import datetime, time
                    time_parts = timestamp.split(':')
                    if len(time_parts) == 3:
                        hour, minute, second = map(int, time_parts)
                        today = datetime.now().date()
                        start_datetime = datetime.combine(today, time(hour, minute, second))
                        duration_str = self._calculate_duration(start_datetime)
                    else:
                        duration_str = "Unknown"
                except:
                    duration_str = "Unknown"
                    
                status_message = (
                    f"🟢 **Status: CLOCKED IN**\n\n"
                    f"Started: {timestamp}\n"
                    f"Duration: {duration_str}"
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
        try:
            if start_time is None:
                return "0h 0m"
                
            if isinstance(start_time, str):
                try:
                    start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                except:
                    return "0h 0m"
            
            german_tz = pytz.timezone('Europe/Berlin')
            
            # Make sure start_time is timezone-aware
            if start_time.tzinfo is None:
                start_time = german_tz.localize(start_time)
            
            current_time = datetime.now(german_tz)
            duration = current_time - start_time
            
            # Handle negative duration (clock skew or date issues)
            if duration.total_seconds() < 0:
                return "0h 0m"
            
            total_seconds = int(duration.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours}h {minutes}m"
        except Exception as e:
            self.logger.error(f"Duration calculation error: {e}")
            return "0h 0m"
    
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
                f"{config_info}\n"
                f"🔴 **Clocked Out.\n" 
                f"Date: {user.last_clock_in.strftime('%Y-%m-%d')}\n"
                f"Working Time: {user.last_clock_in.strftime('%H:%M')} - {datetime.now().strftime('%H:%M')}\n"
                f"Work Duration: {self._calculate_duration(user.last_clock_in)}\n"
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
    
    async def voice_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle voice messages and transcribe them"""
        user_id = update.effective_user.id
        
        if user_id not in self.registered_users:
            await update.message.reply_text("Please start with /start first.")
            return
        
        try:
            # Download the voice file
            voice_file = await update.message.voice.get_file()
            voice_data = await voice_file.download_as_bytearray()
            
            # Transcribe using OpenAI Whisper
            transcription = await self._transcribe_audio(voice_data)
            
            if transcription:
                # Save transcription as description for today
                success = self.time_tracker.update_description(user_id, transcription)
                
                if success:
                    user = self.registered_users[user_id]
                    await update.message.reply_html(
                        f"✅ **Sprachnotiz zur heutigen Arbeitszeit hinzugefügt:**\n\n"
                        f"📝 \"{transcription}\"",
                        reply_markup=user.get_main_keyboard()
                    )
                else:
                    user = self.registered_users[user_id]
                    await update.message.reply_html(
                        "⚠️ Keine Arbeitszeit für heute gefunden. Bitte zuerst einstempeln.",
                        reply_markup=user.get_main_keyboard()
                    )
            else:
                user = self.registered_users[user_id]
                await update.message.reply_html(
                    "❌ Audio konnte nicht transkribiert werden. Bitte versuchen Sie es erneut.",
                    reply_markup=user.get_main_keyboard()
                )
                
        except Exception as e:
            self.logger.error(f"Error processing voice message: {e}")
            user = self.registered_users[user_id]
            await update.message.reply_html(
                "❌ Fehler beim Verarbeiten der Sprachnachricht. Bitte versuchen Sie es erneut.",
                reply_markup=user.get_main_keyboard()
            )
    
    async def image_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle image messages and process table with crosses/ticks"""
        user_id = update.effective_user.id
        
        if user_id not in self.registered_users:
            await update.message.reply_text("Bitte starten Sie mit /start zuerst.")
            return
        
        user = self.registered_users[user_id]
        
        try:
            # Show processing message
            await update.message.reply_html("📷 **Bild wird verarbeitet...**\n\nTabelle wird erkannt und Daten werden extrahiert.")
            
            # Download the image file
            photo = update.message.photo[-1]  # Get highest resolution
            image_file = await photo.get_file()
            image_data = await image_file.download_as_bytearray()
            
            # Process table using OCR
            extracted_data = await self._process_table_image(image_data)
            
            if extracted_data:
                # Check if this is a BMW Station Status table
                is_bmw_station = any(
                    'BMW' in str(data.get('raw_text', '')) or 
                    'Dingolfing' in str(data.get('raw_text', '')) or
                    'Hardware installed' in str(data.get('raw_text', '')) or
                    'Robot programs status' in str(data.get('raw_text', '')) or
                    'PLC status' in str(data.get('raw_text', ''))
                    for data in extracted_data
                )
                
                if is_bmw_station:
                    # Create BMW Station Status sheet
                    station_sheet = self.time_tracker.gsheets_handler.create_bmw_station_status_sheet(user_id, extracted_data)
                    
                    # Also save raw OCR data
                    ocr_success = await self._save_table_data(user_id, extracted_data)
                    
                    if station_sheet:
                        await update.message.reply_html(
                            f"✅ **BMW Station Status Tabelle erstellt!**\n\n"
                            f"📋 Neue Tabelle: {station_sheet}\n"
                            f"📊 {len(extracted_data)} Einträge verarbeitet\n\n"
                            f"Die Tabelle wurde im BMW Dingolfing G50 Format erstellt.",
                            reply_markup=user.get_main_keyboard()
                        )
                    else:
                        await update.message.reply_html(
                            "❌ Fehler beim Erstellen der BMW Station Status Tabelle.",
                            reply_markup=user.get_main_keyboard()
                        )
                else:
                    # Regular table processing
                    success = await self._save_table_data(user_id, extracted_data)
                    
                    if success:
                        await update.message.reply_html(
                            f"✅ **Tabelle erfolgreich verarbeitet!**\n\n"
                            f"📊 {len(extracted_data)} Datensätze zur Tabelle hinzugefügt.",
                            reply_markup=user.get_main_keyboard()
                        )
                    else:
                        await update.message.reply_html(
                            "❌ Fehler beim Speichern der Tabellendaten. Bitte versuchen Sie es erneut.",
                            reply_markup=user.get_main_keyboard()
                        )
            else:
                await update.message.reply_html(
                    "❌ Keine Tabelle oder Kreuze/Häkchen im Bild gefunden. Bitte versuchen Sie es mit einem klareren Bild.",
                    reply_markup=user.get_main_keyboard()
                )
                
        except Exception as e:
            self.logger.error(f"Error processing image: {e}")
            await update.message.reply_html(
                "❌ Fehler beim Verarbeiten des Bildes. Bitte versuchen Sie es erneut.",
                reply_markup=user.get_main_keyboard()
            )
    
    async def _process_table_image(self, image_data):
        """Process image to extract table data with crosses/ticks using LlamaParse"""
        try:
            import tempfile
            import os
            from PIL import Image
            from llama_parse import LlamaParse
            
            # Save image data to temporary file
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                temp_file.write(image_data)
                temp_file_path = temp_file.name
            
            try:
                # Initialize LlamaParse with API key
                parser = LlamaParse(
                    api_key=os.getenv("LLAMA_PARSE_API_KEY"),
                    result_type="markdown",  # Get structured markdown output
                    verbose=True,
                    language="de"  # German language support
                )
                
                # Parse the image to extract table data
                documents = parser.load_data(temp_file_path)
                
                # Extract text content from documents
                parsed_text = ""
                for doc in documents:
                    parsed_text += doc.text + "\n"
                
                # Extract table structure and crosses/ticks from parsed content
                extracted_data = await self._parse_llamaparse_output(parsed_text)
                
                return extracted_data
                
            finally:
                # Clean up temporary file
                os.unlink(temp_file_path)
                
        except Exception as e:
            self.logger.error(f"LlamaParse processing error: {e}")
            return None
    
    async def _parse_llamaparse_output(self, parsed_text):
        """Parse LlamaParse markdown output to extract table data with crosses/ticks"""
        try:
            import re
            
            # Split text into lines
            lines = parsed_text.split('\n')
            
            # Remove empty lines
            lines = [line.strip() for line in lines if line.strip()]
            
            # Extract station ID from top-left area (first few lines)
            station_id = self._extract_station_id(lines[:5])
            
            # Look for markdown table patterns
            table_data = []
            in_table = False
            headers = []
            
            # Enhanced symbols for crosses/ticks (LlamaParse might preserve more symbols)
            cross_symbols = ['x', 'X', '×', '✓', '✔', '☑', '☐', '■', '▪', '□', '+', '*', '◯', '●', '○']
            
            for line in lines:
                # Detect markdown table headers
                if '|' in line and not in_table:
                    # This looks like a table header
                    headers = [cell.strip() for cell in line.split('|') if cell.strip()]
                    in_table = True
                    continue
                
                # Skip markdown table separator (|---|---|)
                if in_table and re.match(r'^[\|\s\-]+$', line):
                    continue
                
                # Process table rows
                if in_table and '|' in line:
                    cells = [cell.strip() for cell in line.split('|') if cell.strip()]
                    
                    # Check if any cell contains crosses/ticks
                    row_data = {
                        'headers': headers,
                        'cells': cells,
                        'marks': [],
                        'marked_positions': [],
                        'raw_text': line
                    }
                    
                    for i, cell in enumerate(cells):
                        if any(symbol in cell for symbol in cross_symbols):
                            row_data['marks'].append(cell)
                            row_data['marked_positions'].append(i)
                    
                    if row_data['marks']:
                        table_data.append(row_data)
                
                # Also check for non-table format lines with marks
                elif not in_table:
                    has_marks = any(symbol in line for symbol in cross_symbols)
                    if has_marks:
                        parts = line.split()
                        row_data = {
                            'headers': [],
                            'cells': parts,
                            'marks': [],
                            'marked_positions': [],
                            'raw_text': line
                        }
                        
                        for i, part in enumerate(parts):
                            if any(symbol in part for symbol in cross_symbols):
                                row_data['marks'].append(part)
                                row_data['marked_positions'].append(i)
                        
                        if row_data['marks']:
                            table_data.append(row_data)
            
            # Convert to structured data
            if table_data:
                return self._structure_llamaparse_data(table_data, station_id)
            
            return None
            
        except Exception as e:
            self.logger.error(f"LlamaParse output parsing error: {e}")
            return None
    
    def _extract_station_id(self, first_lines):
        """Extract station ID (VB/HB/BG/KG2/KG3) from first few lines"""
        station_patterns = ['VB', 'HB', 'BG', 'KG2', 'KG3']
        
        for line in first_lines:
            line_upper = line.upper()
            for pattern in station_patterns:
                if pattern in line_upper:
                    return pattern
        
        return "HB"  # Default fallback
    
    def _structure_llamaparse_data(self, table_data):
        """Convert LlamaParse table data into structured format for spreadsheet"""
        structured_data = []
        
        for row in table_data:
            # Create structured entry with enhanced information
            entry = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'source': 'llamaparse_ocr',
                'raw_text': row['raw_text'],
                'headers': ', '.join(row['headers']) if row['headers'] else '',
                'all_cells': ', '.join(row['cells']),
                'marks_detected': ', '.join(row['marks']),
                'marked_positions': ', '.join(map(str, row['marked_positions'])),
                'processed': True
            }
            structured_data.append(entry)
        
        return structured_data
    
    async def _fallback_ocr_processing(self, image_data):
        """Fallback OCR processing using Tesseract if LlamaParse fails"""
        try:
            import tempfile
            import os
            from PIL import Image
            import pytesseract
            
            # Save image data to temporary file
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                temp_file.write(image_data)
                temp_file_path = temp_file.name
            
            try:
                # Open and process image
                image = Image.open(temp_file_path)
                
                # Convert to grayscale for better OCR
                image = image.convert('L')
                
                # Perform OCR to extract text
                ocr_text = pytesseract.image_to_string(image, lang='deu+eng')
                
                # Extract table structure and crosses/ticks
                extracted_data = await self._parse_table_text(ocr_text, image_data)
                
                return extracted_data
                
            finally:
                # Clean up temporary file
                os.unlink(temp_file_path)
                
        except Exception as e:
            self.logger.error(f"Fallback OCR processing error: {e}")
            return None
    
    async def _parse_table_text(self, ocr_text, image_data):
        """Parse OCR text to identify table structure and crosses/ticks"""
        try:
            # Split text into lines
            lines = ocr_text.split('\n')
            
            # Remove empty lines
            lines = [line.strip() for line in lines if line.strip()]
            
            # Look for table patterns
            table_data = []
            current_row = {}
            
            # Common symbols that represent crosses/ticks in OCR
            cross_symbols = ['x', 'X', '×', '✓', '✔', '☑', '■', '▪', '+', '*']
            
            # Process each line
            for line in lines:
                # Skip very short lines (likely OCR artifacts)
                if len(line) < 2:
                    continue
                
                # Look for patterns that suggest table rows
                # This is a simplified approach - you may need to adjust based on your specific table format
                
                # Check if line contains crosses/ticks
                has_marks = any(symbol in line for symbol in cross_symbols)
                
                if has_marks:
                    # Extract data from this line
                    # Split by whitespace and look for meaningful content
                    parts = line.split()
                    
                    row_data = {
                        'raw_text': line,
                        'marks': [],
                        'labels': []
                    }
                    
                    # Identify marks and associated labels
                    for i, part in enumerate(parts):
                        if any(symbol in part for symbol in cross_symbols):
                            row_data['marks'].append(part)
                            # Try to find associated label (previous or next part)
                            if i > 0:
                                row_data['labels'].append(parts[i-1])
                            elif i < len(parts) - 1:
                                row_data['labels'].append(parts[i+1])
                    
                    if row_data['marks'] or row_data['labels']:
                        table_data.append(row_data)
            
            # If we found some structured data, return it
            if table_data:
                return self._structure_table_data(table_data)
            
            return None
            
        except Exception as e:
            self.logger.error(f"Table parsing error: {e}")
            return None
    
    def _structure_table_data(self, raw_data):
        """Convert raw table data into structured format for spreadsheet"""
        structured_data = []
        
        for row in raw_data:
            # Create a structured entry
            entry = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'source': 'image_ocr',
                'raw_text': row['raw_text'],
                'marks_detected': ', '.join(row['marks']),
                'labels': ', '.join(row['labels']),
                'processed': True
            }
            structured_data.append(entry)
        
        return structured_data
    
    async def _save_table_data(self, user_id, table_data):
        """Save extracted table data to a new spreadsheet or existing one"""
        try:
            # Get user's sheet handler
            sheet_name = self.time_tracker.gsheets_handler.get_user_sheet_name(user_id)
            
            # Create or get OCR data sheet
            ocr_sheet_name = f"OCR_Data_{self.time_tracker.gsheets_handler.users_config.get(user_id, 'Unknown')}"
            
            try:
                ocr_wks = self.time_tracker.gsheets_handler.sh.worksheet_by_title(ocr_sheet_name)
            except:
                # Create new OCR sheet
                ocr_wks = self.time_tracker.gsheets_handler.sh.add_worksheet(ocr_sheet_name)
                
                # Setup enhanced headers for LlamaParse data
                headers = ["Timestamp", "Source", "Raw Text", "Table Headers", "All Cells", "Marks Detected", "Marked Positions", "Processed"]
                ocr_wks.update_row(1, headers)
            
            # Get existing records
            try:
                all_records = ocr_wks.get_all_records()
            except:
                all_records = []
            
            # Add new data
            next_row = len(all_records) + 2
            
            for data in table_data:
                if data['source'] == 'llamaparse_ocr':
                    # Enhanced data structure from LlamaParse
                    row_data = [
                        data['timestamp'],
                        data['source'],
                        data['raw_text'],
                        data['headers'],
                        data['all_cells'],
                        data['marks_detected'],
                        data['marked_positions'],
                        str(data['processed'])
                    ]
                else:
                    # Fallback structure for basic OCR
                    row_data = [
                        data['timestamp'],
                        data['source'],
                        data['raw_text'],
                        '',  # headers (empty for basic OCR)
                        data.get('labels', ''),  # use labels as all_cells
                        data['marks_detected'],
                        '',  # marked_positions (empty for basic OCR)
                        str(data['processed'])
                    ]
                ocr_wks.update_row(next_row, row_data)
                next_row += 1
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving table data: {e}")
            return False
    
    async def _transcribe_audio(self, audio_data):
        """Transcribe audio using OpenAI Whisper"""
        try:
            import openai
            import os
            import tempfile
            
            # Set OpenAI API key
            openai.api_key = os.getenv("OPENAI_API_KEY")
            
            # Save audio data to temporary file
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name
            
            try:
                # Transcribe using OpenAI Whisper
                with open(temp_file_path, "rb") as audio_file:
                    client = openai.OpenAI()
                    response = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="de"  # German language
                    )
                return response.text
                
            finally:
                # Clean up temporary file
                os.unlink(temp_file_path)
                
        except Exception as e:
            self.logger.error(f"Transcription error: {e}")
            return None
    
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

