# Body Part + Pricing + Discount Sync Checklist

## Core Pricing Flow
- [ ] Ask for a price without service (`"How much?"`) -> bot asks for service type first.
- [ ] Ask for hair removal price with no body part (`"Price for laser hair removal?"`) -> bot asks for body area first.
- [ ] Provide body area after prompt (`"underarms"`) -> bot returns system price from API (not static Q&A text).
- [ ] Repeat same request in Arabic/English/French -> returned amounts stay identical to system values.

## Body Part Persistence
- [ ] Select a body part once, then ask `"and on Quadro?"` -> bot reuses saved body part and fetches updated system price.
- [ ] Change body part (`"no, cheeks instead"`) -> next pricing result reflects new body part values.
- [ ] Move from pricing to booking in same thread -> `create_appointment` includes saved `body_part_ids` for services 1/12/13.

## Discount Handling
- [ ] When API returns `discount_*` fields -> reply includes discounted final amount and original amount.
- [ ] When API returns only base + discount percent/amount -> bot computes final amount and displays it.
- [ ] When API returns no discount fields -> bot displays base/final price only (no fake discount text).

## Safety/Regression
- [ ] Price intent should bypass local Q&A direct replies (no static `"Prices vary by area"` short-circuit).
- [ ] If pricing API is unavailable -> bot asks for retry/details and does not invent numbers.
- [ ] Reschedule intents still bypass clinic-hours drift behavior.
