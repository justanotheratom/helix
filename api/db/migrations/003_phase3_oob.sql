-- Helix Phase 3: out-of-band data blobs per snapshot.
-- Large data declared in [snapshot].out_of_band is excluded from the main
-- snapshot tar and published as separate content-addressed blobs
-- (oob/<digest>.tar.gz), recorded here as {oob_root: digest} and mounted by
-- the worker as extra overlayfs lowerdirs. Idempotent.

ALTER TABLE snapshots
    ADD COLUMN IF NOT EXISTS oob_blobs JSONB NOT NULL DEFAULT '{}'::jsonb;
