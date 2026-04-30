@echo off
echo ============================================================
echo   STRATEGY LEARNER — 24/7 Auto Discovery Engine
echo ============================================================
echo.
echo This bot will:
echo   1. Scrape Reddit, YouTube, Financial News 24/7
echo   2. Extract trading strategies using GPT-4o
echo   3. Auto-backtest each strategy
echo   4. Score and rank them
echo   5. Save the best ones to data/best_strategies.json
echo.
echo Make sure your .env file has your API keys set!
echo.
pip install -r requirements.txt -q
echo.
python strategy_learner.py
pause
