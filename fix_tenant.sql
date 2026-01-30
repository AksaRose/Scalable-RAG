-- Fix existing tenant API key hash
-- This updates the test tenant to use the correct SHA256 hash
UPDATE tenants 
SET api_key_hash = '3738a9db044b02c2849ff7eb06aa66659462b920e2368335229f25b144343fcf'
WHERE name = 'test_tenant' 
  AND api_key_hash != '3738a9db044b02c2849ff7eb06aa66659462b920e2368335229f25b144343fcf';

-- If tenant doesn't exist, create it
INSERT INTO tenants (tenant_id, name, api_key_hash, rate_limit) 
VALUES 
    ('00000000-0000-0000-0000-000000000001', 'test_tenant', '3738a9db044b02c2849ff7eb06aa66659462b920e2368335229f25b144343fcf', 100)
ON CONFLICT (name) DO UPDATE 
SET api_key_hash = EXCLUDED.api_key_hash;
