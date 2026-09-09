"""Verification and deletion helpers for Meta's user-data deletion callback.

Implementation is split under 500 lines; this module re-exports the public API.
"""

from __future__ import annotations

from services.meta_data_deletion_process import (  # noqa: F401
    _DELETION_THREAD_LOCK,
    _LOCK_DIR,
    _delete_meta_social_user_data_locked,
    _deletion_process_lock,
    _redaction_has_remaining,
    _sanitize_local_and_ack,
    delete_meta_social_user_data,
    process_pending_meta_deletion_requests,
    read_deletion_status,
)
from services.meta_data_deletion_store import (  # noqa: F401
    _binding_scopes,
    _finalize_shared_request,
    _get_or_create_shared_request,
    _mark_coordinator_completed,
    _mark_coordinator_failed,
    _merge_request_scope,
    _new_request,
    _parse_ack,
    _parse_binding_scopes,
    _parse_shared_request,
    _read_shared_request,
    _replace_request_if_generation,
    _request_payload,
    _snapshot_payload,
)
from services.meta_data_deletion_types import (  # noqa: F401
    _ACK_SAFE_FIELDS,
    _BINDING_ID_RE,
    _CONFIRMATION_CODE_RE,
    _FIRESTORE_APP_ID,
    _INDEX_SAFE_FIELDS,
    _MAX_FUTURE_SKEW_SECONDS,
    _MAX_SIGNED_REQUEST_AGE_SECONDS,
    _META_USER_ID_RE,
    _NODE_ID_RE,
    _REQUEST_COLLECTION,
    _REQUEST_SAFE_FIELDS,
    _SCHEMA_VERSION,
    _SUBJECT_INDEX_COLLECTION,
    MetaDeletionResult,
    MetaDeletionStateError,
    MetaDeletionStoreUnavailableError,
    MetaSignedRequestError,
    VerifiedMetaDeletionRequest,
    _app_document,
    _decode_base64url,
    _deletion_node_config,
    _DeletionBindingScope,
    _firestore_db,
    _request_ref,
    _safe_int,
    _SharedDeletionRequest,
    _subject_index_key,
    _subject_index_ref,
    deletion_confirmation_code,
    generate_opaque_confirmation_code,
    verify_meta_deletion_signed_request,
)
