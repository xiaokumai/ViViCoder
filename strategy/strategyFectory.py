"""Resolve strategies lazily so unrelated baselines do not initialize at startup."""

from importlib import import_module


_STRATEGIES = {
    "vanilla": ("strategy.vanilla", "vanilla"),
    "CoT": ("strategy.CoT", "CoT"),
    "SelfPlanning": ("strategy.SelfPlanning", "SelfPlanning"),
    "Analogical": ("strategy.Analogical", "analogical"),
    "MapCoder": ("strategy.MapCoder", "MapCoder"),
    "CodeSIM": ("strategy.CodeSIM", "CodeSIM"),
    "ViViCoder": ("strategy.ViViCoder", "ViViCoder"),
    "paircoder": ("strategy.paircoder.paircoder", "paircoder"),
    "evomac": ("strategy.evomac", "evomac"),
    "chatdev": ("strategy.chatdev", "chatdev"),
    "ldb": ("strategy.ldb", "ldb"),
    "openhands": ("strategy.openhands", "openhands"),
    "codex": ("strategy.codex", "codex"),
    "TraceCoder": ("strategy.tracecoder", "TraceCoder"),
    "FlowGen": ("strategy.flowgen", "flowgen"),
}


def get_strategy(strategy_name):
    target = _STRATEGIES.get(strategy_name)
    if target is None:
        return None
    module_name, attribute_name = target
    return getattr(import_module(module_name), attribute_name)
