-- FUNLANDIA birthday booking prototype schema (TEST environment only)
-- A party occupies a zone for 4 hours: 3h event + 1h cleanup.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE IF NOT EXISTS birthday_bookings (
    id BIGSERIAL PRIMARY KEY,
    public_code TEXT NOT NULL UNIQUE,
    telegram_user_id BIGINT NOT NULL,
    telegram_username TEXT,
    customer_name TEXT NOT NULL,
    child_name TEXT NOT NULL,
    child_age SMALLINT,
    phone TEXT NOT NULL,
    children_count SMALLINT NOT NULL CHECK (children_count > 0),
    zone_no SMALLINT NOT NULL CHECK (zone_no BETWEEN 1 AND 3),
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    planned_ends_at TIMESTAMPTZ,
    released_at TIMESTAMPTZ,
    released_by BIGINT,
    payment_method TEXT NOT NULL DEFAULT 'payme' CHECK (payment_method IN ('payme','click')),
    party_minutes SMALLINT NOT NULL DEFAULT 180 CHECK (party_minutes = 180),
    cleanup_minutes SMALLINT NOT NULL DEFAULT 60 CHECK (cleanup_minutes = 60),
    deposit_amount INTEGER NOT NULL DEFAULT 100000 CHECK (deposit_amount = 100000),
    status TEXT NOT NULL DEFAULT 'held'
      CHECK (status IN ('held','awaiting_payment','awaiting_admin','confirmed','rejected','cancelled','expired')),
    hold_expires_at TIMESTAMPTZ,
    extras TEXT,
    language TEXT NOT NULL DEFAULT 'ru',
    admin_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (ends_at > starts_at)
);

ALTER TABLE birthday_bookings ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'ru';
ALTER TABLE birthday_bookings ADD COLUMN IF NOT EXISTS planned_ends_at TIMESTAMPTZ;
ALTER TABLE birthday_bookings ADD COLUMN IF NOT EXISTS released_at TIMESTAMPTZ;
ALTER TABLE birthday_bookings ADD COLUMN IF NOT EXISTS released_by BIGINT;
ALTER TABLE birthday_bookings ADD COLUMN IF NOT EXISTS payment_method TEXT NOT NULL DEFAULT 'payme';
UPDATE birthday_bookings SET planned_ends_at=ends_at WHERE planned_ends_at IS NULL;

-- Existing bookings keep their original planned end; ends_at becomes the actual occupancy end
-- when an administrator releases a zone early.
DO $migration$
DECLARE c RECORD;
BEGIN
  FOR c IN SELECT conname FROM pg_constraint
    WHERE conrelid='birthday_bookings'::regclass
      AND contype='c'
      AND pg_get_constraintdef(oid) ILIKE '%ends_at - starts_at%'
  LOOP
    EXECUTE format('ALTER TABLE birthday_bookings DROP CONSTRAINT %I', c.conname);
  END LOOP;
END $migration$;

ALTER TABLE birthday_bookings DROP CONSTRAINT IF EXISTS birthday_bookings_status_check;
ALTER TABLE birthday_bookings ADD CONSTRAINT birthday_bookings_status_check
  CHECK (status IN ('held','awaiting_payment','awaiting_admin','confirmed','rejected','cancelled','expired','released'));
ALTER TABLE birthday_bookings DROP CONSTRAINT IF EXISTS birthday_bookings_payment_method_check;
ALTER TABLE birthday_bookings ADD CONSTRAINT birthday_bookings_payment_method_check
  CHECK (payment_method IN ('payme','click'));

-- Prevent two active reservations/holds from occupying the same zone at overlapping times.
ALTER TABLE birthday_bookings
  DROP CONSTRAINT IF EXISTS birthday_bookings_no_overlap;
ALTER TABLE birthday_bookings
  ADD CONSTRAINT birthday_bookings_no_overlap
  EXCLUDE USING gist (
    zone_no WITH =,
    tstzrange(starts_at, ends_at, '[)') WITH &&
  )
  WHERE (status IN ('held','awaiting_payment','awaiting_admin','confirmed'));

CREATE INDEX IF NOT EXISTS birthday_bookings_calendar_idx
  ON birthday_bookings (starts_at, zone_no)
  WHERE status IN ('held','awaiting_payment','awaiting_admin','confirmed');

CREATE INDEX IF NOT EXISTS birthday_bookings_user_idx
  ON birthday_bookings (telegram_user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS birthday_payments (
    id BIGSERIAL PRIMARY KEY,
    booking_id BIGINT NOT NULL REFERENCES birthday_bookings(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('payme','click')),
    amount INTEGER NOT NULL CHECK (amount = 100000),
    provider_payment_id TEXT,
    status TEXT NOT NULL DEFAULT 'created'
      CHECK (status IN ('created','pending','paid','failed','refunded')),
    payment_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    paid_at TIMESTAMPTZ,
    UNIQUE (provider, provider_payment_id)
);

CREATE TABLE IF NOT EXISTS birthday_admin_actions (
    id BIGSERIAL PRIMARY KEY,
    booking_id BIGINT NOT NULL REFERENCES birthday_bookings(id) ON DELETE CASCADE,
    admin_telegram_id BIGINT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('confirm','reject','reschedule','note','release')),
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE birthday_admin_actions DROP CONSTRAINT IF EXISTS birthday_admin_actions_action_check;
ALTER TABLE birthday_admin_actions ADD CONSTRAINT birthday_admin_actions_action_check
  CHECK (action IN ('confirm','reject','reschedule','note','release'));

-- Admin calendar reads bookings by month; payment status remains separate from admin approval.
