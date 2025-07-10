# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Telegram bot for employee time tracking with Clock In/Clock Out functionality and location tracking.

## Core Features
- Clock In/Clock Out buttons
- Location tracking for each clock action
- Time storage and management
- Simple user interface with inline keyboards

## Development Setup

### Required Environment Variables
```bash
TELEGRAM_TOKEN=your_telegram_bot_token
```

### Required Dependencies
- `python-telegram-bot` for Telegram API interaction
- Database solution for time storage (SQLite/MongoDB/PostgreSQL)
- `datetime` for timestamp handling

### Setup and Installation

#### Using uv (Recommended)
```bash
# Install dependencies
uv sync

# Run the bot
uv run tracker

# Or run directly
uv run python tracker.py
```

#### Alternative: Using pip
```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python tracker.py
```

## Bot Architecture

### Key Components
- **TelegramBot**: Main bot class handling user interactions
- **Time Tracking**: Clock In/Clock Out functionality with timestamps
- **Location Handling**: Request and store user location data
- **Data Storage**: Persistent storage for time records

### Bot Flow
1. User starts bot → Shows Clock In/Clock Out buttons
2. User clicks Clock In → Requests location → Stores timestamp + location
3. User clicks Clock Out → Requests location → Stores timestamp + location
4. Data is stored reliably for reporting

## Implementation Notes
- Use inline keyboards for Clock In/Clock Out buttons
- Request location permission when user performs clock actions
- Store timestamps in UTC for consistency
- Include user ID, action type, timestamp, and location in records
- Handle edge cases (multiple clock-ins, clock-out without clock-in, etc.)