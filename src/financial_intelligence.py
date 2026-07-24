"""Financial Intelligence Module for Orca Agent"""

import asyncio
from typing import Dict, Any, List
from loguru import logger
import pandas as pd

class FinancialIntelligence:
    """Handles financial data analysis, investment research, and budgeting"""

    def __init__(self):
        logger.info("💰 Initializing Financial Intelligence module...")
        logger.info("✅ Financial Intelligence module initialized.")

    async def analyze_bank_statements(self, statement_data: pd.DataFrame) -> Dict:
        """Read and understand bank statements, identifying trends and categories"""
        logger.info("Analyzing bank statement data.")
        
        # Simplified analysis
        summary = {
            "total_income": statement_data[statement_data["amount"] > 0]["amount"].sum(),
            "total_expenses": statement_data[statement_data["amount"] < 0]["amount"].sum(),
            "top_expense_categories": statement_data[statement_data["amount"] < 0].groupby("category")["amount"].sum().sort_values().head(3).to_dict()
        }
        
        return {"status": "success", "summary": summary}

    async def detect_unnecessary_expenses(self, statement_data: pd.DataFrame) -> Dict:
        """Detect unnecessary or recurring expenses that could be optimized"""
        logger.info("Detecting unnecessary expenses.")
        
        # Simplified detection: look for recurring small transactions or specific categories
        recurring = statement_data[statement_data["amount"] < 0].groupby("description").filter(lambda x: len(x) > 1)
        
        return {"status": "success", "potential_savings": recurring["amount"].sum(), "recurring_items": recurring["description"].unique().tolist()}

    async def suggest_monthly_budget(self, income: float, past_expenses: pd.DataFrame) -> Dict:
        """Suggest a monthly budget based on income and past spending habits"""
        logger.info(f"Suggesting budget for income: {income}")
        
        # Simple 50/30/20 rule application
        budget = {
            "needs": income * 0.5,
            "wants": income * 0.3,
            "savings_debt": income * 0.2
        }
        
        return {"status": "success", "suggested_budget": budget}

    async def analyze_investments(self, portfolio: List[Dict]) -> Dict:
        """Analyze investment portfolios and compare risks/returns"""
        logger.info(f"Analyzing investment portfolio with {len(portfolio)} assets.")
        
        # Simplified risk analysis
        analysis = "Portfolio appears balanced. Consider diversifying into international markets for better risk management."
        
        return {"status": "success", "analysis": analysis}

    async def monitor_stocks_alerts(self, symbols: List[str]) -> Dict:
        """Monitor stocks and send alerts based on price movements or news"""
        logger.info(f"Monitoring stocks: {', '.join(symbols)}")
        
        # This would typically use a financial API (e.g., Alpha Vantage, Yahoo Finance)
        alerts = [f"Alert: {symbol} price increased by 5%." for symbol in symbols]
        
        return {"status": "success", "alerts": alerts}

    async def calculate_roi(self, investment: float, return_amount: float, time_period_years: float) -> Dict:
        """Calculate Return on Investment (ROI) for any decision"""
        logger.info(f"Calculating ROI for investment: {investment}")
        
        roi = ((return_amount - investment) / investment) * 100
        annualized_roi = ((return_amount / investment) ** (1 / time_period_years) - 1) * 100
        
        return {"status": "success", "roi_percentage": roi, "annualized_roi_percentage": annualized_roi}


# Example usage (for testing purposes)
async def main():
    finance_engine = FinancialIntelligence()

    print("\n--- Analyzing Bank Statement ---")
    data = pd.DataFrame({
        "date": ["2026-07-01", "2026-07-02", "2026-07-03"],
        "amount": [5000, -50, -100],
        "category": ["Salary", "Food", "Transport"],
        "description": ["Company X", "McDonalds", "Uber"]
    })
    statement_result = await finance_engine.analyze_bank_statements(data)
    print(statement_result)

    print("\n--- Suggesting Monthly Budget ---")
    budget_result = await finance_engine.suggest_monthly_budget(5000, data)
    print(budget_result)

    print("\n--- Calculating ROI ---")
    roi_result = await finance_engine.calculate_roi(1000, 1500, 2)
    print(roi_result)

if __name__ == "__main__":
    asyncio.run(main())
