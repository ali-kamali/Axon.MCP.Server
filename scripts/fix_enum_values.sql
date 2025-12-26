-- Script to check and add missing enum values to relationtypeenum
-- Run this in your PostgreSQL database

-- 1. Check current enum values
SELECT 'Current relationtypeenum values:' as info;
SELECT e.enumlabel 
FROM pg_enum e
JOIN pg_type t ON e.enumtypid = t.oid
WHERE t.typname = 'relationtypeenum'
ORDER BY e.enumsortorder;

-- 2. Add missing OVERRIDES value (if not exists)
-- Note: PostgreSQL doesn't support IF NOT EXISTS before version 9.5 in some cases
-- This will error if the value already exists, which is fine
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum e
        JOIN pg_type t ON e.enumtypid = t.oid
        WHERE t.typname = 'relationtypeenum' 
        AND e.enumlabel = 'OVERRIDES'
    ) THEN
        ALTER TYPE relationtypeenum ADD VALUE 'OVERRIDES';
        RAISE NOTICE 'Added OVERRIDES to relationtypeenum';
    ELSE
        RAISE NOTICE 'OVERRIDES already exists in relationtypeenum';
    END IF;
END $$;

-- 3. Add missing REFERENCES value (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum e
        JOIN pg_type t ON e.enumtypid = t.oid
        WHERE t.typname = 'relationtypeenum' 
        AND e.enumlabel = 'REFERENCES'
    ) THEN
        ALTER TYPE relationtypeenum ADD VALUE 'REFERENCES';
        RAISE NOTICE 'Added REFERENCES to relationtypeenum';
    ELSE
        RAISE NOTICE 'REFERENCES already exists in relationtypeenum';
    END IF;
END $$;

-- 4. Verify all values are present
SELECT 'Final relationtypeenum values:' as info;
SELECT e.enumlabel 
FROM pg_enum e
JOIN pg_type t ON e.enumtypid = t.oid
WHERE t.typname = 'relationtypeenum'
ORDER BY e.enumsortorder;
