# services/openai_usage_service.py
"""
OpenAI Usage API Integration
Fetches real cost data from OpenAI's billing API for accurate cost tracking.
"""

import httpx
import datetime
from typing import Dict, Optional
import config


class OpenAIUsageService:
    """Service to fetch actual usage and costs from OpenAI API"""
    
    def __init__(self):
        self.api_key = config.OPENAI_API_KEY
        self.base_url = "https://api.openai.com/v1"
        
    async def get_usage_for_date(self, date: str) -> Optional[Dict]:
        """
        Fetch usage data for a specific date from OpenAI.
        
        Args:
            date: Date in YYYY-MM-DD format
            
        Returns:
            Dict with usage data or None if failed
        """
        try:
            url = f"{self.base_url}/usage?date={date}"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ Fetched OpenAI usage for {date}: ${data.get('total_cost', 0):.4f}")
                    return data
                elif response.status_code == 404:
                    print(f"⚠️ No usage data found for {date}")
                    return None
                else:
                    print(f"❌ OpenAI Usage API error: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            print(f"❌ Error fetching OpenAI usage: {e}")
            return None
    
    async def get_usage_for_date_range(self, start_date: str, end_date: str) -> Dict:
        """
        Fetch usage data for a date range.
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            Dict with aggregated usage data
        """
        try:
            # Convert strings to datetime objects
            start = datetime.datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.datetime.strptime(end_date, "%Y-%m-%d")
            
            total_cost = 0.0
            total_tokens = 0
            model_breakdown = {}
            daily_costs = []
            
            # Iterate through each day in the range
            current_date = start
            while current_date <= end:
                date_str = current_date.strftime("%Y-%m-%d")
                usage_data = await self.get_usage_for_date(date_str)
                
                if usage_data:
                    # Aggregate costs
                    day_cost = usage_data.get('total_cost', 0)
                    total_cost += day_cost
                    
                    # Aggregate tokens
                    day_tokens = usage_data.get('total_tokens', 0)
                    total_tokens += day_tokens
                    
                    # Store daily cost
                    daily_costs.append({
                        'date': date_str,
                        'cost': day_cost,
                        'tokens': day_tokens
                    })
                    
                    # Aggregate by model
                    for model_data in usage_data.get('data', []):
                        model_name = model_data.get('snapshot_id', 'unknown')
                        model_cost = model_data.get('cost', 0)
                        model_tokens = model_data.get('n_context_tokens_total', 0) + model_data.get('n_generated_tokens_total', 0)
                        
                        if model_name not in model_breakdown:
                            model_breakdown[model_name] = {
                                'cost': 0,
                                'tokens': 0,
                                'requests': 0
                            }
                        
                        model_breakdown[model_name]['cost'] += model_cost
                        model_breakdown[model_name]['tokens'] += model_tokens
                        model_breakdown[model_name]['requests'] += model_data.get('n_requests', 0)
                
                # Move to next day
                current_date += datetime.timedelta(days=1)
            
            return {
                'success': True,
                'start_date': start_date,
                'end_date': end_date,
                'total_cost_usd': total_cost,
                'total_tokens': total_tokens,
                'daily_costs': daily_costs,
                'model_breakdown': model_breakdown,
                'days_fetched': len(daily_costs)
            }
            
        except Exception as e:
            print(f"❌ Error fetching usage for date range: {e}")
            return {
                'success': False,
                'error': str(e),
                'total_cost_usd': 0,
                'total_tokens': 0
            }
    
    async def get_usage_for_last_n_days(self, days: int = 7) -> Dict:
        """
        Fetch usage data for the last N days.
        
        Args:
            days: Number of days to fetch (default 7)
            
        Returns:
            Dict with aggregated usage data
        """
        end_date = datetime.datetime.now()
        start_date = end_date - datetime.timedelta(days=days - 1)
        
        return await self.get_usage_for_date_range(
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d")
        )
    
    async def sync_costs_to_analytics(self, days: int = 7) -> bool:
        """
        Sync real OpenAI costs to analytics events file.
        This updates the analytics with actual costs from OpenAI.
        
        Args:
            days: Number of days to sync
            
        Returns:
            True if successful, False otherwise
        """
        try:
            from services.analytics_events import analytics
            
            print(f"🔄 Syncing OpenAI costs for last {days} days...")
            
            # Get real usage data from OpenAI
            usage_data = await self.get_usage_for_last_n_days(days)
            
            if not usage_data.get('success'):
                print(f"❌ Failed to fetch OpenAI usage data")
                return False
            
            # Log the real cost data
            print(f"✅ OpenAI Real Costs:")
            print(f"   Total Cost: ${usage_data['total_cost_usd']:.4f}")
            print(f"   Total Tokens: {usage_data['total_tokens']:,}")
            print(f"   Days Fetched: {usage_data['days_fetched']}")
            
            # Log model breakdown
            if usage_data.get('model_breakdown'):
                print(f"\n📊 Cost Breakdown by Model:")
                for model, data in usage_data['model_breakdown'].items():
                    print(f"   {model}: ${data['cost']:.4f} ({data['tokens']:,} tokens, {data['requests']} requests)")
            
            # Store in analytics metadata (for dashboard display)
            # This will be used by the analytics API to show real costs
            analytics.openai_real_costs = usage_data
            
            return True
            
        except Exception as e:
            print(f"❌ Error syncing costs to analytics: {e}")
            import traceback
            traceback.print_exc()
            return False


# Global instance
openai_usage_service = OpenAIUsageService()
