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
    CHECK (ends_at > starts_at),
    CHECK (ends_at - starts_at = interval '4 hours')
);

ALTER TABLE birthday_bookings ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'ru';

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
    action TEXT NOT NULL CHECK (action IN ('confirm','reject','reschedule','note')),
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Admin calendar reads bookings by month; payment status remains separate from admin approval.
