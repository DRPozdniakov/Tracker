import pygsheets
import sys
import pandas as pd
import sqlite3
from datetime import datetime

# Station Status


class GsheetsHandler:
    def __init__(self, gsheet_key_path: str, sheet_name: str = 'Launch_Time_Tracker'):
        self.gc = pygsheets.authorize(service_file=gsheet_key_path)
        self.sh = self.gc.open(sheet_name)
        
        # User configuration mapping
        self.users_config = {
            1794622246: "Shane_Hill",
            495992751: "Dmitry_Pozdniakov"
        }
        
        self.setup_config_sheet()
        self.setup_user_timesheets()

    def read_categories(self):
        wks = self.sh[0]
        categories = wks.get_col(2, include_tailing_empty=False)[1:]
        categories_links = wks.get_col(3, include_tailing_empty=False)[1:]
        categories_dict = {category: category_link for category, category_link in zip(categories, categories_links)}
        return categories_dict
    
    def setup_user_timesheets(self):
        """Setup individual timesheets for each user"""
        for user_id, username in self.users_config.items():
            sheet_name = f"Timesheet_{username}"
            try:
                # Try to get existing user timesheet
                timesheet_wks = self.sh.worksheet_by_title(sheet_name)
            except pygsheets.exceptions.WorksheetNotFound:
                # Create new user timesheet
                timesheet_wks = self.sh.add_worksheet(sheet_name)
            
            # Setup headers for user timesheet
            headers = ["Date", "clock_in", "clock_out", "Latitude In", "Longitude In", "Latitude Out", "Longitude Out", "Description"]
            first_row = timesheet_wks.get_row(1)
            if not first_row or first_row[0] != "Date":
                timesheet_wks.update_row(1, headers)
    
    def get_user_sheet_name(self, user_id):
        """Get the sheet name for a specific user"""
        if user_id in self.users_config:
            return f"Timesheet_{self.users_config[user_id]}"
        else:
            # Default sheet for unknown users
            self._setup_unknown_user_sheet()
            return "Timesheet_Unknown"
    
    def _setup_unknown_user_sheet(self):
        """Setup default sheet for unknown users"""
        sheet_name = "Timesheet_Unknown"
        try:
            # Try to get existing unknown user timesheet
            timesheet_wks = self.sh.worksheet_by_title(sheet_name)
        except pygsheets.exceptions.WorksheetNotFound:
            # Create new unknown user timesheet
            timesheet_wks = self.sh.add_worksheet(sheet_name)
            
            # Setup headers
            headers = ["Date", "clock_in", "clock_out", "Latitude In", "Longitude In", "Latitude Out", "Longitude Out", "Duration", "Description"]
            timesheet_wks.update_row(1, headers)
    
    def _get_local_time(self, latitude=None, longitude=None):
        """Get local time based on coordinates or default to Europe/Berlin"""
        try:
            if latitude is not None and longitude is not None:
                # Use timezonefinder to get timezone from coordinates
                from timezonefinder import TimezoneFinder
                import pytz
                
                tf = TimezoneFinder()
                timezone_str = tf.timezone_at(lat=float(latitude), lng=float(longitude))
                
                if timezone_str:
                    tz = pytz.timezone(timezone_str)
                    return datetime.now(tz)
        except:
            pass
        
        # Fallback to Europe/Berlin timezone
        import pytz
        default_tz = pytz.timezone('Europe/Berlin')
        return datetime.now(default_tz)
    
    
    
    def setup_config_sheet(self):
        """Setup configuration sheet for user project settings"""
        try:
            # Try to get existing config sheet
            config_wks = self.sh.worksheet_by_title("User_Config")
        except pygsheets.exceptions.WorksheetNotFound:
            # Create new config sheet
            config_wks = self.sh.add_worksheet("User_Config")
        
        # Setup headers for config sheet
        config_headers = ["User ID", "Username", "Project Name", "Project Location", "Contractor Name", "Lunch Duration", "Last Updated"]
        first_row = config_wks.get_row(1)
        if not first_row or first_row[0] != "User ID":
            config_wks.update_row(1, config_headers)

    def add_time_record(self, user_id, username, action, timestamp, latitude=None, longitude=None):
        """Add or update a daily time record in the user's Timesheet"""
        sheet_name = self.get_user_sheet_name(user_id)
        timesheet_wks = self.sh.worksheet_by_title(sheet_name)
        
        # Get timezone from location if available
        local_time = self._get_local_time(latitude, longitude)
        
        date_str = local_time.strftime('%d/%m/%Y')
        time_str = local_time.strftime('%H:%M:%S')
        
        # Get all records to find existing entry for today
        all_records = timesheet_wks.get_all_records()
        
        # Look for existing record for today's date
        existing_row = None
        for i, record in enumerate(all_records):
            if record.get('Date') == date_str:
                existing_row = i + 2  # +2 because records start from row 2
                break
        
        if existing_row:
            # Update existing record
            current_record = all_records[existing_row - 2]
            if action == "clock_in":
                row_data = [
                    date_str,
                    time_str,  # clock_in
                    current_record.get('clock_out', ''),  # Keep existing clock_out
                    latitude or "",  # Latitude In
                    longitude or "",  # Longitude In
                    current_record.get('Latitude Out', ''),  # Keep existing Latitude Out
                    current_record.get('Longitude Out', ''),   # Keep existing Longitude Out
                    current_record.get('Duration', ''),  # Keep existing Duration
                    current_record.get('Description', '')  # Keep existing Description
                ]
            else:  # clock_out                
                row_data = [
                    date_str,
                    current_record.get('clock_in', ''),  # Keep existing clock_in
                    time_str,  # clock_out
                    current_record.get('Latitude In', ''),   # Keep existing Latitude In
                    current_record.get('Longitude In', ''),  # Keep existing Longitude In
                    latitude or "",  # Latitude Out
                    longitude or "",  # Longitude Out
                    f"=TEXT(C{existing_row}-B{existing_row},\"[h]:mm:ss\")",  # Duration formula in hours:minutes:seconds format
                    current_record.get('Description', '')  # Keep existing Description
                ]
            timesheet_wks.update_row(existing_row, row_data)
            return existing_row
        else:
            # Create new record
            if action == "clock_in":
                row_data = [
                    date_str,
                    time_str,  # clock_in
                    "",  # clock_out (empty)
                    latitude or "",  # Latitude In
                    longitude or "",  # Longitude In
                    "",  # Latitude Out (empty)
                    "",   # Longitude Out (empty)
                    "",   # Duration (empty)
                    ""    # Description (empty)
                ]
            else:  # clock_out (shouldn't happen without clock_in, but handle it)
                row_data = [
                    date_str,
                    "",  # clock_in (empty)
                    time_str,  # clock_out
                    "",  # Latitude In (empty)
                    "",  # Longitude In (empty)
                    latitude or "",  # Latitude Out
                    longitude or "",  # Longitude Out
                    "",   # Duration (empty)
                    ""    # Description (empty)
                ]
            
            next_row = len(all_records) + 2
            timesheet_wks.update_row(next_row, row_data)
            return next_row
    
    def update_description(self, user_id, date_str, description):
        """Update description for a specific date"""
        sheet_name = self.get_user_sheet_name(user_id)
        try:
            timesheet_wks = self.sh.worksheet_by_title(sheet_name)
            all_records = timesheet_wks.get_all_records()
            
            # Find the record for this date
            for i, record in enumerate(all_records):
                if record.get('Date') == date_str:
                    # Update description in the existing record
                    row_num = i + 2  # +2 because records start from row 2
                    current_description = record.get('Description', '')
                    
                    # Append new description to existing one
                    if current_description:
                        new_description = f"{current_description}; {description}"
                    else:
                        new_description = description
                    
                    # Update just the description column (column I = 9, since we added Duration)
                    timesheet_wks.update_value((row_num, 9), new_description)
                    return True
            
            return False  # Date not found
            
        except pygsheets.exceptions.WorksheetNotFound:
            return False

    def get_user_records(self, user_id, limit=10):
        """Get recent time records for a user"""
        sheet_name = self.get_user_sheet_name(user_id)
        try:
            timesheet_wks = self.sh.worksheet_by_title(sheet_name)
            all_records = timesheet_wks.get_all_records()
        except pygsheets.exceptions.WorksheetNotFound:
            return []
        
        # Sort records by date (newest first)
        all_records.sort(key=lambda x: x.get('Date', ''), reverse=True)
        
        # Return limited records
        limited_records = all_records[:limit]
        formatted_records = []
        
        for record in limited_records:
            formatted_record = (
                record.get('Date', ''),
                record.get('clock_in', ''),
                record.get('clock_out', ''),
                record.get('Latitude In', ''),
                record.get('Longitude In', ''),
                record.get('Latitude Out', ''),
                record.get('Longitude Out', '')
            )
            formatted_records.append(formatted_record)
        
        return formatted_records

    def get_last_action(self, user_id):
        """Get the last action for a user"""
        sheet_name = self.get_user_sheet_name(user_id)
        try:
            timesheet_wks = self.sh.worksheet_by_title(sheet_name)
            all_records = timesheet_wks.get_all_records()
        except pygsheets.exceptions.WorksheetNotFound:
            return None
        
        if not all_records:
            return None
        
        # Sort by date and get the latest
        all_records.sort(key=lambda x: x.get('Date', ''), reverse=True)
        latest_record = all_records[0]
        
        # Check if there's a clock out time - if yes, last action was clock_out
        # If no clock out time but clock in time exists, last action was clock_in
        clock_in = latest_record.get('clock_in', '')
        clock_out = latest_record.get('clock_out', '')
        
        if clock_out:
            return ("clock_out", clock_out)
        elif clock_in:
            return ("clock_in", clock_in)
        else:
            return None

    def get_today_records(self, user_id=None):
        """Get today's records for a user"""
        if user_id:
            sheet_name = self.get_user_sheet_name(user_id)
            try:
                timesheet_wks = self.sh.worksheet_by_title(sheet_name)
                all_records = timesheet_wks.get_all_records()
            except pygsheets.exceptions.WorksheetNotFound:
                return []
        else:
            # If no user_id provided, return empty list since we now have separate sheets
            return []
        
        today_str = datetime.now().strftime('%d/%m/%Y')
        
        # Filter records for today
        today_records = [record for record in all_records if record.get('Date') == today_str]
        
        return today_records

    def save_user_config(self, user_id, config):
        """Save user configuration to the config sheet"""
        config_wks = self.sh.worksheet_by_title("User_Config")
        all_records = config_wks.get_all_records()
        
        # Check if user config already exists
        user_row = None
        for i, record in enumerate(all_records):
            if str(record.get('User ID')) == str(user_id):
                user_row = i + 2  # +2 because records start from row 2
                break
        
        # Prepare config data
        config_data = [
            str(user_id),
            config.get('username', ''),  # Telegram username
            config.get('project_name', ''),
            config.get('project_location', ''),
            config.get('contractor_name', ''),
            config.get('lunch_duration', ''),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ]
        
        if user_row:
            # Update existing config
            config_wks.update_row(user_row, config_data)
        else:
            # Add new config
            next_row = len(all_records) + 2
            config_wks.update_row(next_row, config_data)
    
    def get_user_config(self, user_id):
        """Get user configuration from the config sheet"""
        try:
            config_wks = self.sh.worksheet_by_title("User_Config")
            all_records = config_wks.get_all_records()
            
            # Find user config
            for record in all_records:
                if str(record.get('User ID')) == str(user_id):
                    return {
                        'username': record.get('Username', ''),
                        'project_name': record.get('Project Name', ''),
                        'project_location': record.get('Project Location', ''),
                        'contractor_name': record.get('Contractor Name', ''),
                        'lunch_duration': record.get('Lunch Duration', ''),
                        'last_updated': record.get('Last Updated', '')
                    }
            return None
        except pygsheets.exceptions.WorksheetNotFound:
            return None

    def write_products(self, data):
        """Legacy method - kept for compatibility"""
        wks = self.sh[0]
        if isinstance(data, str):
            # If data is a string, write it as a simple value
            wks.update_value((1, 1), data)
        elif isinstance(data, pd.DataFrame):
            # If data is a DataFrame, use set_dataframe
            wks.set_dataframe(data, (1, 1))
        else:
            raise ValueError("Data must be either a string or pandas DataFrame")

class TimeTracker:
    """Handles time tracking using Google Sheets"""
    
    def __init__(self, gsheet_key_path: str, sheet_name: str = 'Launch_Time_Tracker'):
        self.gsheets_handler = GsheetsHandler(gsheet_key_path, sheet_name)
    
    def add_record(self, user_id, username, action, latitude=None, longitude=None, location_address=None):
        """Add a time record"""
        timestamp = datetime.now()
        
        # Add record to main sheet
        return self.gsheets_handler.add_time_record(
            user_id=user_id,
            username=username,
            action=action,
            timestamp=timestamp,
            latitude=latitude,
            longitude=longitude
        )
    
    def get_user_records(self, user_id, limit=10):
        """Get recent time records for a user"""
        return self.gsheets_handler.get_user_records(user_id, limit)
    
    def get_last_action(self, user_id):
        """Get the last action for a user"""
        return self.gsheets_handler.get_last_action(user_id)
    
    def get_today_records(self, user_id=None):
        """Get today's records for a user or all users"""
        return self.gsheets_handler.get_today_records(user_id)
    
    def save_user_config(self, user_id, config):
        """Save user configuration"""
        return self.gsheets_handler.save_user_config(user_id, config)
    
    def get_user_config(self, user_id):
        """Get user configuration"""
        return self.gsheets_handler.get_user_config(user_id)
    
    def update_description(self, user_id, description):
        """Update description for today's date"""
        from datetime import datetime
        import pytz
        
        # Get today's date in the format used in sheets
        default_tz = pytz.timezone('Europe/Berlin')
        today = datetime.now(default_tz).strftime('%d/%m/%Y')
        
        return self.gsheets_handler.update_description(user_id, today, description)

if __name__ == "__main__":
    gsheet_key="C:/Users/drpoz/OneDrive/Desktop/TelegramShops/Amazon/creds/google_creds.json"
    gsheets_handler = GsheetsHandler(gsheet_key_path=gsheet_key)
    write_data = gsheets_handler.write_products("Lets go!")
    print(write_data)