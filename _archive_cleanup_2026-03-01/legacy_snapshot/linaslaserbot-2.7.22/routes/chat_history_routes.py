# -*- coding: utf-8 -*-
"""
Chat History API Routes
"""
from fastapi import APIRouter, Query
from services.live_chat_service import live_chat_service

router = APIRouter()

@router.get("/api/chat-history/customers")
async def get_chat_history_customers(
    search: str = Query(default=""),
    filter_by: str = Query(default="all"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=1000),
):
    return await live_chat_service.get_history_customers(
        search=search,
        filter_by=filter_by,
        page=page,
        page_size=page_size,
    )


@router.post("/api/chat-history/refresh")
async def refresh_chat_history_cache():
    """Force refresh service caches."""
    live_chat_service.invalidate_cache()
    return await get_chat_history_customers()


@router.get("/api/chat-history/conversations/{user_id}")
async def get_customer_conversations(
    user_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=1000),
    status: str = Query(default="all"),
    search: str = Query(default=""),
):
    return await live_chat_service.get_history_conversations(
        user_id=user_id,
        page=page,
        page_size=page_size,
        status=status,
        search=search,
    )


@router.get("/api/chat-history/messages/{user_id}/{conversation_id}")
async def get_conversation_messages(
    user_id: str,
    conversation_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=1000, ge=1, le=1000),
    search: str = Query(default=""),
    sort: str = Query(default="asc"),
):
    return await live_chat_service.get_history_messages(
        user_id=user_id,
        conversation_id=conversation_id,
        page=page,
        page_size=page_size,
        search=search,
        sort=sort,
    )
