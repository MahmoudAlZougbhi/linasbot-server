# Live Chat FAQ correction

Customer replies use **Customer Reply V2**. When a reply comes from published CM FAQ, Live Chat can add that pair to the owner FAQ.

## Current product path

- **Surface:** Linas AI mobile Live Chat (Like on a bot FAQ reply).
- **API:** `POST /api/cm/faq/from-livechat`
- **Storage:** canonical CM FAQ (`services/cm/faq_integration.py`). Legacy `/api/faq/*` and `/api/local-qa/*` HTTP writers are gone.

The conversation payload may still include FAQ match metadata on the message (`faq_match`, `reply_source`) from `GET /api/live-chat/conversation/{user_id}/{conversation_id}`.

## Not in product anymore

These leftover web-operator paths were removed:

- `GET /api/live-chat/faq-match-context`
- `POST /api/faq/update-answer`
- `POST /api/faq/create-from-livechat`
- `POST /api/live-chat/edit-message`
- Dashboard Live Chat FAQ Correction modal
