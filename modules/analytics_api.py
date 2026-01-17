# -*- coding: utf-8 -*-
"""
Analytics API Module
Uses event-based analytics with append-only JSONL file
"""

from modules.core import app
from services.analytics_events import analytics
from services.openai_usage_service import openai_usage_service


@app.get("/api/analytics/summary")
async def get_analytics_summary(time_range: int = 7, use_real_costs: bool = True):
    """
    Get comprehensive analytics summary
    
    Args:
        time_range: Number of days to include (default: 7)
        use_real_costs: Whether to fetch real costs from OpenAI API (default: True)
        
    Returns:
        JSON with all analytics data aggregated from events
    """
    try:
        print(f"📊 Analytics API: Aggregating events for last {time_range} days")
        
        # Aggregate events from JSONL file
        result = analytics.aggregate_analytics(days=time_range)
        
        # Fetch real costs from OpenAI if requested
        if use_real_costs:
            print(f"💰 Fetching real costs from OpenAI API...")
            try:
                openai_usage = await openai_usage_service.get_usage_for_last_n_days(time_range)
                
                if openai_usage.get('success'):
                    # Replace estimated costs with real costs
                    result['token_usage']['total_cost_usd'] = openai_usage['total_cost_usd']
                    result['token_usage']['total_tokens'] = openai_usage['total_tokens']
                    result['token_usage']['source'] = 'openai_api'
                    result['token_usage']['model_breakdown'] = openai_usage.get('model_breakdown', {})
                    result['token_usage']['daily_costs'] = openai_usage.get('daily_costs', [])
                    
                    print(f"✅ Using real OpenAI costs: ${openai_usage['total_cost_usd']:.4f}")
                else:
                    print(f"⚠️ Failed to fetch real costs, using estimates")
                    result['token_usage']['source'] = 'estimated'
                    
            except Exception as e:
                print(f"⚠️ Error fetching real costs: {e}")
                result['token_usage']['source'] = 'estimated'
        else:
            result['token_usage']['source'] = 'estimated'
        
        if result.get("success"):
            print(f"✅ Analytics API: Successfully aggregated analytics")
            return {
                "success": True,
                "data": result
            }
        else:
            print(f"⚠️ Analytics API: Error aggregating data")
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "data": result
            }
            
    except Exception as e:
        print(f"❌ Analytics API Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }
