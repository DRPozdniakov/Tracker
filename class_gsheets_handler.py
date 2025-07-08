import pygsheets
import sys
import pandas as pd
import sqlite3
from datetime import datetime

class GsheetsHandler:
    def __init__(self, gsheet_key_path: str, sheet_name: str = 'Launch_Time_Tracker'):
        self.gc = pygsheets.authorize(service_file=gsheet_key_path)
        self.sh = self.gc.open(sheet_name)
        self.setup_headers()

    def read_categories(self):
        wks = self.sh[0]
        categories = wks.get_col(2, include_tailing_empty=False)[1:]
        categories_links = wks.get_col(3, include_tailing_empty=False)[1:]
        categories_dict = {category: category_link for category, category_link in zip(categories, categories_links)}
        return categories_dict
    
    def setup_headers(self):
        """Setup headers for time tracking sheet if they don't exist"""
        wks = self.sh[0]
        headers = ["User ID", "Username", "Action", "Timestamp", "Date", "Latitude", "Longitude", "Location Address"]
        
        # Check if headers exist, if not, create them
        first_row = wks.get_row(1)
        if not first_row or first_row[0] != "User ID":
            wks.update_row(1, headers)

    def add_time_record(self, user_id, username, action, timestamp, latitude=None, longitude=None, location_address=None):
        """Add a time record to the Google Sheet"""
        wks = self.sh[0]
        
        # Format timestamp and extract date
        if isinstance(timestamp, str):
            timestamp_obj = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        else:
            timestamp_obj = timestamp
        
        date_str = timestamp_obj.strftime('%Y-%m-%d')
        timestamp_str = timestamp_obj.strftime('%Y-%m-%d %H:%M:%S')
        
        # Prepare row data
        row_data = [
            str(user_id),
            username or "",
            action,
            timestamp_str,
            date_str,
            latitude or "",
            longitude or "",
            location_address or ""
        ]
        
        # Find the next empty row
        all_records = wks.get_all_records()
        next_row = len(all_records) + 2  # +2 because records start from row 2 (after headers)
        
        # Add the record
        wks.update_row(next_row, row_data)
        
        return next_row

    def get_user_records(self, user_id, limit=10):
        """Get recent time records for a user"""
        wks = self.sh[0]
        all_records = wks.get_all_records()
        
        # Filter records for the user and sort by timestamp (newest first)
        user_records = [record for record in all_records if str(record.get('User ID')) == str(user_id)]
        user_records.sort(key=lambda x: x.get('Timestamp', ''), reverse=True)
        
        # Return limited records in the format expected by the bot
        limited_records = user_records[:limit]
        formatted_records = []
        
        for record in limited_records:
            formatted_record = (
                record.get('Action', ''),
                record.get('Timestamp', ''),
                record.get('Latitude', ''),
                record.get('Longitude', ''),
                record.get('Location Address', '')
            )
            formatted_records.append(formatted_record)
        
        return formatted_records

    def get_last_action(self, user_id):
        """Get the last action for a user"""
        wks = self.sh[0]
        all_records = wks.get_all_records()
        
        # Filter records for the user and sort by timestamp (newest first)
        user_records = [record for record in all_records if str(record.get('User ID')) == str(user_id)]
        
        if not user_records:
            return None
        
        # Sort by timestamp and get the latest
        user_records.sort(key=lambda x: x.get('Timestamp', ''), reverse=True)
        latest_record = user_records[0]
        
        return (latest_record.get('Action', ''), latest_record.get('Timestamp', ''))

    def get_today_records(self, user_id=None):
        """Get today's records for a user or all users"""
        wks = self.sh[0]
        all_records = wks.get_all_records()
        
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        # Filter records for today
        today_records = [record for record in all_records if record.get('Date') == today_str]
        
        if user_id:
            today_records = [record for record in today_records if str(record.get('User ID')) == str(user_id)]
        
        return today_records

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

    # def write_gsheets(self):
    #     # authorization
    # gc = pygsheets.authorize(service_file=gsheet_key)
    # headers = ["real_id", "timestamp", "prague_id", "link", "location", "contact_ways", "comment", "lodge_type", "assigned_to", "state", "description", "completed"]
    # report_types = ["В обработке", "Выполненые", "Отклоненные", "Буффер новых"]
    # dbs = ["Realities", "Completed_Realities", "Rejected_Realities", "Buffered_Realities"]
    
    # # open the google spreadsheet
    # sh = gc.open('NobbleHomesDB')

    # for num, db_name in enumerate(dbs):
    #     # select the appropriate sheet
    #     wks = sh[num]
    #     data = list(db[db_name].find())
    #     data = [list(item.values())[:5] + ["'" + str(item["contact_ways"])] + list(item.values())[6:8] + list(item.values())[10:] for item in data]
        
    #     # Create a dataframe
    #     df = pd.DataFrame(data, columns=headers)
        
    #     # update the first sheet with df
    #     wks.clear()
    #     logger.info(f"Written in {db_name}")
    #     wks.set_dataframe(df, (1, 1))
    
    # wks = sh[num + 1]
    # wks.set_dataframe(df, (1, 1))


class TimeTracker:
    """Handles time tracking using Google Sheets"""
    
    def __init__(self, gsheet_key_path: str, sheet_name: str = 'Launch_Time_Tracker'):
        self.gsheets_handler = GsheetsHandler(gsheet_key_path, sheet_name)
    
    def add_record(self, user_id, username, action, latitude=None, longitude=None, location_address=None):
        """Add a time record to Google Sheets"""
        timestamp = datetime.now()
        return self.gsheets_handler.add_time_record(
            user_id=user_id,
            username=username,
            action=action,
            timestamp=timestamp,
            latitude=latitude,
            longitude=longitude,
            location_address=location_address
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

if __name__ == "__main__":
    gsheet_key="C:/Users/drpoz/OneDrive/Desktop/TelegramShops/Amazon/creds/google_creds.json"
    gsheets_handler = GsheetsHandler(gsheet_key_path=gsheet_key)
    write_data = gsheets_handler.write_products("Lets go!")
    print(write_data)