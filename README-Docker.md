# Docker Setup for Telegram Time Tracker

## Prerequisites

1. **Docker & Docker Compose** installed on your system
2. **Telegram Bot Token** from BotFather
3. **Google Sheets API credentials** (JSON file)

## Setup Instructions

### 1. Prepare Environment

```bash
# Copy the environment template
cp .env.example .env

# Edit the .env file with your actual values
nano .env
```

### 2. Set up Google Credentials

```bash
# Create credentials directory
mkdir -p creds

# Copy your Google Service Account JSON file
cp /path/to/your/google_creds.json creds/google_creds.json
```

### 3. Configure Environment Variables

Edit `.env` file:
```bash
TELEGRAM_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
GSHEET_KEY_PATH=/app/creds/google_creds.json
LOG_LEVEL=INFO
```

## Running the Application

### Option 1: Using Docker Compose (Recommended)

```bash
# Build and start the application
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the application
docker-compose down
```

### Option 2: Using Docker directly

```bash
# Build the image
docker build -t telegram-tracker .

# Run the container
docker run -d \
  --name telegram-time-tracker \
  --restart unless-stopped \
  -e TELEGRAM_TOKEN=your_token_here \
  -v $(pwd)/creds:/app/creds:ro \
  -v $(pwd)/logs:/app/logs \
  telegram-tracker
```

## Management Commands

```bash
# Check container status
docker-compose ps

# View logs
docker-compose logs telegram-tracker

# Restart the service
docker-compose restart

# Update the application
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Access container shell (for debugging)
docker-compose exec telegram-tracker bash
```

## File Structure

```
/mnt/c/Users/drpoz/OneDrive/Desktop/Launch_Robotics/Tracker/
├── Dockerfile                 # Docker image definition
├── docker-compose.yml         # Docker Compose configuration
├── .env.example              # Environment template
├── .env                      # Your actual environment variables
├── .dockerignore             # Files to exclude from Docker build
├── README-Docker.md          # This documentation
├── app/                      # Application files
│   ├── requirements.txt      # Python dependencies
│   ├── run.py               # Application runner
│   ├── tracker.py           # Main application
│   ├── class_telegram_bot.py # Bot implementation
│   ├── class_gsheets_handler.py # Google Sheets handler
│   └── CLAUDE.md            # Development documentation
└── creds/
    └── google_creds.json    # Google Service Account credentials
```

## Troubleshooting

### Container won't start
```bash
# Check logs for errors
docker-compose logs telegram-tracker

# Common issues:
# - Invalid TELEGRAM_TOKEN
# - Missing google_creds.json file
# - Incorrect file permissions
```

### Google Sheets access issues
```bash
# Verify credentials file exists and has correct permissions
ls -la creds/google_creds.json

# Check if the service account has access to your Google Sheet
```

### Network connectivity issues
```bash
# Test from inside container
docker-compose exec telegram-tracker python -c "import requests; print(requests.get('https://api.telegram.org').status_code)"
```

## Security Notes

- Never commit `.env` file or `google_creds.json` to version control
- The container runs as a non-root user for security
- Credentials are mounted read-only
- Consider using Docker secrets for production deployments

## Production Deployment

For production, consider:
- Using Docker swarm or Kubernetes
- Setting up proper logging with log rotation
- Implementing monitoring and alerting
- Using Docker secrets for sensitive data
- Setting up automatic updates with Watchtower