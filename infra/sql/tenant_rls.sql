-- Apply only with the application role. Superusers bypass RLS.
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY messages_tenant ON messages
    USING (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY conversations_tenant ON conversations
    USING (tenant_id = current_setting('app.tenant_id', true));
