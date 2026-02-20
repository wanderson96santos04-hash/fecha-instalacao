BEGIN;

-- =========================================
-- FECHA INSTALAÇÃO - Schema MVP
-- =========================================

CREATE TABLE IF NOT EXISTS users (
  id            BIGSERIAL PRIMARY KEY,
  email         VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  is_pro        BOOLEAN NOT NULL DEFAULT FALSE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS budgets (
  id             BIGSERIAL PRIMARY KEY,
  user_id        BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_name    VARCHAR(120) NOT NULL,
  phone          VARCHAR(40)  NOT NULL,
  service_type   VARCHAR(80)  NOT NULL,
  value          VARCHAR(40)  NOT NULL,
  payment_method VARCHAR(60)  NOT NULL,
  notes          TEXT NOT NULL DEFAULT '',
  status         VARCHAR(20) NOT NULL DEFAULT 'awaiting',
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_budgets_user_id ON budgets(user_id);
CREATE INDEX IF NOT EXISTS idx_budgets_created_at ON budgets(created_at);

-- status permitido (MVP): awaiting | won | lost
ALTER TABLE budgets
  DROP CONSTRAINT IF EXISTS chk_budgets_status;

ALTER TABLE budgets
  ADD CONSTRAINT chk_budgets_status
  CHECK (status IN ('awaiting', 'won', 'lost'));

COMMIT;
