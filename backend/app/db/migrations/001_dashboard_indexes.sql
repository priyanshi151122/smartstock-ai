-- Migration 001: add supplier_lead_time override + index used by dashboard risk queries.
-- Additive only; applied once and tracked in schema_migrations.

CREATE INDEX IF NOT EXISTS idx_products_category ON products (category);

CREATE INDEX IF NOT EXISTS idx_inventory_risk ON inventory (current_stock, reorder_threshold);
