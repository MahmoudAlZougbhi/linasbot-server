# -*- coding: utf-8 -*-
"""
Analytics API module: Analytics endpoints
Provides comprehensive analytics data aggregated from Firebase, Backend API, and logs
"""

from modules.core import app
from services.analytics_service import analytics_service


@app.get("/api/analytics/summary")
async def get_analytics_summary(time_range: int = 7):
    """
    Get comprehensive analytics summary
    
    Aggregates data from:
    - Firebase: Conversations, messages, user demographics
    - Backend API: Customer info, appointments
    - Logs: Events, escalations, services
    - Feedback: Satisfaction metrics
    
    Parameters:
    - time_range: Number of days to include (default: 7)
    
    Returns:
    - daily_summaries: Daily message counts, users, costs
    - hourly_distribution: Messages by hour of day
    - demographics: Language and gender distribution
    - performance: Response time metrics
    - token_usage: AI model usage and costs
    - conversions: Inquiry to appointment conversion
    - satisfaction: User feedback and ratings
    - appointments: Booking status breakdown
    - escalations: Human handover and issues
    - services: Most requested services
    - trending_topics: Popular conversation topics
    """
    try:
        summary = await analytics_service.get_analytics_summary(time_range)
        return {
            "success": True,
            "data": summary
        }
    except Exception as e:
        print(f"❌ Error in get_analytics_summary: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }
