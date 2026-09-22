"""Adapters for providers the declarative executor cannot express.

A module belongs here only when the provider needs more than one call — a
zone lookup before the record write — or a signature the manifest cannot
describe. Everything else is a request block in providers/src/<id>.yaml
and no code at all.

A manifest points at a module here through engine.module; manifest_merge.py
refuses a manifest whose module has no file, so the two cannot drift.
"""
