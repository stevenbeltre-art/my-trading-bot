#!/bin/bash
# This script starts the Trading Bot

echo "Setting up the Trading Bot..."
echo ""

# Go to the bot directory
cd "/Users/stevebeltre/Desktop/ANTIGRAVITY/trading_bot"

# Activate the virtual environment
source venv/bin/activate

# Run the app
echo "Launching Dashboard! Please wait..."
streamlit run main.py
