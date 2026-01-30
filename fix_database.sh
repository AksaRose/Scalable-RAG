#!/bin/bash
# Fix the tenant API key hash in the database

echo "Fixing tenant API key hash in database..."

docker-compose exec -T postgres psql -U rag_user -d rag_db <<EOF
-- Update existing tenant with correct hash
UPDATE tenants 
SET api_key_hash = '3738a9db044b02c2849ff7eb06aa66659462b920e2368335229f25b144343fcf'
WHERE name = 'test_tenant';

-- If tenant doesn't exist, create it
INSERT INTO tenants (tenant_id, name, api_key_hash, rate_limit) 
VALUES 
    ('00000000-0000-0000-0000-000000000001', 'test_tenant', '3738a9db044b02c2849ff7eb06aa66659462b920e2368335229f25b144343fcf', 100)
ON CONFLICT (name) DO UPDATE 
SET api_key_hash = EXCLUDED.api_key_hash;

-- Verify the fix
SELECT tenant_id, name, api_key_hash, rate_limit FROM tenants WHERE name = 'test_tenant';
EOF

echo "Done! Try your upload request again."
