"""Observability module.

Records RunRecord / CostRecord from business events on the event bus.
Aggregates costs by tenant / workspace / cost_type.
QualityScore is read-through from the evaluation module.
"""
