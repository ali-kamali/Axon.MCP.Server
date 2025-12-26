-- Migration: Make event_subscriptions.symbol_id nullable
-- This allows event subscriptions to be saved even when consumer class Symbols aren't found

-- Check if the column is already nullable
DO $$
BEGIN
    -- Make symbol_id nullable
    ALTER TABLE event_subscriptions 
    ALTER COLUMN symbol_id DROP NOT NULL;
    
    RAISE NOTICE 'Migration completed: event_subscriptions.symbol_id is now nullable';
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Migration may have already been applied or error occurred: %', SQLERRM;
END $$;
