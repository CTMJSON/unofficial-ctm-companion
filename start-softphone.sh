#!/bin/bash

# CTM Softphone Launcher
# Starts the Flask development server for the embedded softphone

SOFTPHONE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/softphone"

echo "🚀 Starting CTM Softphone..."
echo "📍 Directory: $SOFTPHONE_DIR"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3."
    exit 1
fi

# Check if Flask is installed
if ! python3 -c "import flask" 2>/dev/null; then
    echo "📦 Installing Flask and dependencies..."
    pip3 install flask requests python-dotenv
fi

# Navigate to softphone directory
cd "$SOFTPHONE_DIR"

# Create .env if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file (you can add credentials later)"
    cat > .env << 'EOF'
# CTM API credentials (Settings > API Keys in CTM)
# CTM_API_KEY=your_api_key_here
# CTM_API_SECRET=your_api_secret_here
# CTM_ACCOUNT_ID=your_account_id

# Optional: auto-fill the setup form with a specific agent
# CTM_USER_EMAIL=agent@example.com
# CTM_USER_FIRST=Alex
# CTM_USER_LAST=Agent
EOF
fi

# Start the Flask app
PORT=${PORT:-8080}
echo "✅ Starting server on http://localhost:$PORT"
echo "📖 Open your browser and go to: http://localhost:$PORT"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Run Flask
python3 app.py
