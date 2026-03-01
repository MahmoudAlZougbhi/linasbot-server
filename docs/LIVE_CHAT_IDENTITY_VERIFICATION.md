# Live Chat Identity – Verification Steps

After deploying phone normalization and external CRM resolve:

## 1. Confirm from logs

- **Raw vs normalized**: Look for `identity raw_phone=... normalized_phone=... canonical_user_id=...` in backend logs. Same real number in different formats (e.g. `03956607`, `+9613956607`, `9613956607`, `03 956 607`) must all log the same `normalized_phone` and `canonical_user_id` (e.g. `+9613956607`).
- **External lookup**: Look for `external_lookup normalized_phone=... exists=... name=...`. If the number exists in the external system, `exists=True` and `name` should be the CRM name. If not, `exists=False` and no name is set (phone-only in Live Chat).
- **User/conversation**: Look for `identity created new user doc` vs `identity updated existing user doc`. For a given number, the first message should create; later messages with the same number (any format) should update and append to the same conversation.

## 2. UI checks

- **Same number, one thread**: Send messages from the same WhatsApp number in different formats (e.g. as stored by provider: `03956607` vs `+9613956607`). In Live Chat there should be **one** conversation per number, not two.
- **Name from CRM**: If the number exists in the external system, the Live Chat list and conversation header should show the **exact** name from the CRM.
- **Phone only when unknown**: If the number does **not** exist in the external system, the Live Chat should show the phone number only (no arbitrary name like "jonny122").

## 3. Run unit tests

```bash
python tests/test_phone_identity.py
```

All listed formats (e.g. `03956607`, `+9613956607`, `9613956607`, `03 956 607`) must normalize to the same E.164 value.

## 4. Migration (one-off)

To backfill existing data and merge duplicate users:

```bash
# Report only
python scripts/migrate_phone_identity.py --dry-run

# Apply migration
python scripts/migrate_phone_identity.py
```

Then confirm again from logs and UI that duplicates are gone and names match the external system.
