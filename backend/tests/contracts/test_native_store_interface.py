"""Interface signature snapshot: the kernel's NativeEventStore protocol.

Why pin this: NativeEventStore is the persistence seam between kernel
(cui.research_universe.store) and the SDK/service layer. Services type against
this protocol; silently renaming or dropping a method here would break the
contract without any direct caller in the kernel package. Snapshot = the
protocol's public method set (contract minimum, not implementation detail).
"""
import inspect

from cui.research_universe.store.event_store import NativeEventStore

EXPECTED_PUBLIC_METHODS = frozenset({
    "create_active_universe",
    "get_active_universe",
    "list_universes_for_library",
    "lookup_command",
    "command_execution",
    "append",
    "read_events",
})


def test_native_event_store_protocol_public_methods_unchanged():
    actual = frozenset(
        name for name, _ in inspect.getmembers(NativeEventStore)
        if not name.startswith("_")
    )
    # Contract minimum: every expected method must still exist. Extra members
    # are allowed (additive change); removals fail here.
    missing = EXPECTED_PUBLIC_METHODS - actual
    assert not missing, f"NativeEventStore lost public method(s): {sorted(missing)}"
