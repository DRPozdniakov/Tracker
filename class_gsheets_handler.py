import pygsheets
import sys
import pandas as pd
import sqlite3
from datetime import datetime

class GsheetsHandler:
    def __init__(self, gsheet_key_path: str, sheet_name: str = 'Launch_Time_Tracker'):
        self.gc = pygsheets.authorize(service_file=gsheet_key_path)
        self.sh = self.gc.open(sheet_name)
        self.setup_timesheet()
        self.setup_config_sheet()

    def read_categories(self):
        wks = self.sh[0]
        categories = wks.get_col(2, include_tailing_empty=False)[1:]
        categories_links = wks.get_col(3, include_tailing_empty=False)[1:]
        categories_dict = {category: category_link for category, category_link in zip(categories, categories_links)}
        return categories_dict
    
    def setup_timesheet(self):
        """Setup Timesheet for clock in/out data"""
        try:
            # Try to get existing Timesheet
            timesheet_wks = self.sh.worksheet_by_title("Timesheet")
        except pygsheets.exceptions.WorksheetNotFound:
            # Create new Timesheet
            timesheet_wks = self.sh.add_worksheet("Timesheet")
        
        # Setup headers for Timesheet
        headers = ["Date", "clock_in", "clock_out", "Latitude In", "Longitude In", "Latitude Out", "Longitude Out"]
        first_row = timesheet_wks.get_row(1)
        if not first_row or first_row[0] != "Date":
            timesheet_wks.update_row(1, headers)
    
    
    def setup_config_sheet(self):
        """Setup configuration sheet for user project settings"""
        try:
            # Try to get existing config sheet
            config_wks = self.sh.worksheet_by_title("User_Config")
        except pygsheets.exceptions.WorksheetNotFound:
            # Create new config sheet
            config_wks = self.sh.add_worksheet("User_Config")
        
        # Setup headers for config sheet
        config_headers = ["User ID", "Project Name", "Project Location", "Contractor Name", "Lunch Duration", "Last Updated"]
        first_row = config_wks.get_row(1)
        if not first_row or first_row[0] != "User ID":
            config_wks.update_row(1, config_headers)

    def add_time_record(self, user_id, username, action, timestamp, latitude=None, longitude=None):
        """Add or update a daily time record in the Timesheet"""
        timesheet_wks = self.sh.worksheet_by_title("Timesheet")
        
        # Format timestamp and extract date
        if isinstance(timestamp, str):
            timestamp_obj = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        else:
            timestamp_obj = timestamp
        
        date_str = timestamp_obj.strftime('%d/%m/%Y')
        time_str = timestamp_obj.strftime('%H:%M:%S')
        
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
                    current_record.get('Longitude Out', '')   # Keep existing Longitude Out
                ]
            else:  # clock_out
                row_data = [
                    date_str,
                    current_record.get('clock_in', ''),  # Keep existing clock_in
                    time_str,  # clock_out
                    current_record.get('Latitude In', ''),   # Keep existing Latitude In
                    current_record.get('Longitude In', ''),  # Keep existing Longitude In
                    latitude or "",  # Latitude Out
                    longitude or ""  # Longitude Out
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
                    ""   # Longitude Out (empty)
                ]
            else:  # clock_out (shouldn't happen without clock_in, but handle it)
                row_data = [
                    date_str,
                    "",  # clock_in (empty)
                    time_str,  # clock_out
                    "",  # Latitude In (empty)
                    "",  # Longitude In (empty)
                    latitude or "",  # Latitude Out
                    longitude or ""  # Longitude Out
                ]
            
            next_row = len(all_records) + 2
            timesheet_wks.update_row(next_row, row_data)
            return next_row
    

    def get_user_records(self, user_id, limit=10):
        """Get recent time records for a user"""
        timesheet_wks = self.sh.worksheet_by_title("Timesheet")
        all_records = timesheet_wks.get_all_records()
        
        # Filter records for the user and sort by timestamp (newest first)
        user_records = [record for record in all_records if str(record.get('User ID')) == str(user_id)]
        user_records.sort(key=lambda x: x.get('Timestamp', ''), reverse=True)
        
        # Return limited records
        limited_records = user_records[:limit]
        formatted_records = []
        
        for record in limited_records:
            formatted_record = (
                record.get('Action', ''),
                record.get('Timestamp', ''),
                record.get('Latitude', ''),
                record.get('Longitude', '')
            )
            formatted_records.append(formatted_record)
        
        return formatted_records

    def get_last_action(self, user_id):
        """Get the last action for a user"""
        timesheet_wks = self.sh.worksheet_by_title("Timesheet")
        all_records = timesheet_wks.get_all_records()
        
        # Filter records for the user and sort by date (newest first)
        user_records = [record for record in all_records if str(record.get('User ID')) == str(user_id)]
        
        if not user_records:
            return None
        
        # Sort by date and get the latest
        user_records.sort(key=lambda x: x.get('Date', ''), reverse=True)
        latest_record = user_records[0]
        
        # Check if there's a clock out time - if yes, last action was clock_out
        # If no clock out time but clock in time exists, last action was clock_in
        clock_in = latest_record.get('Clock In', '')
        clock_out = latest_record.get('Clock Out', '')
        
        if clock_out:
            return ("clock_out", clock_out)
        elif clock_in:
            return ("clock_in", clock_in)
        else:
            return None

    def get_today_records(self, user_id=None):
        """Get today's records for a user or all users"""
        timesheet_wks = self.sh.worksheet_by_title("Timesheet")
        all_records = timesheet_wks.get_all_records()
        
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        # Filter records for today
        today_records = [record for record in all_records if record.get('Date') == today_str]
        
        if user_id:
            today_records = [record for record in today_records if str(record.get('User ID')) == str(user_id)]
        
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

if __name__ == "__main__":
    gsheet_key="C:/Users/drpoz/OneDrive/Desktop/TelegramShops/Amazon/creds/google_creds.json"
    gsheets_handler = GsheetsHandler(gsheet_key_path=gsheet_key)
    write_data = gsheets_handler.write_products("Lets go!")
    print(write_data)