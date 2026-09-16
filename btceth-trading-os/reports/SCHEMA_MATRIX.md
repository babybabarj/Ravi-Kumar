# Schema Matrix

RAW: append-only gzip JSONL retaining the complete source payload and unknown fields.

SILVER: PyArrow Parquet with int64 nanosecond canonical timestamps, preserved source timestamp/unit/precision, payload hash, record key, and exact numeric values serialized without binary-float truth semantics.

Required clocks: ts_event_ns, ts_recv_ns, ts_ingest_ns.
