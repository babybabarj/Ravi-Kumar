from btceth_os.orderbook import OrderBookSync, BookState
from btceth_os.live_orderbook import _candidate_is_bridge, _drop_stale


def test_spot_first_event_may_start_at_snapshot_plus_one():
    book = OrderBookSync()
    book.begin_buffering()
    book.load_snapshot(100, [["10", "2"]], [["11", "3"]])
    book.bridge_first_delta(101, 103, [["10", "1"]], [], bridge_id=101)
    assert book.state == BookState.VALID
    assert book.last_update_id == 103


def test_spot_overlapping_event_also_bridges_next_expected_id():
    assert _candidate_is_bridge("spot", {"U": 98, "u": 104}, 100)


def test_spot_discards_all_events_at_or_before_snapshot_but_keeps_next():
    events = [
        {"U": 90, "u": 99},
        {"U": 100, "u": 100},
        {"U": 101, "u": 102},
    ]
    _drop_stale("spot", events, 100)
    assert events == [{"U": 101, "u": 102}]
    assert _candidate_is_bridge("spot", events[0], 100)


def test_usdm_first_event_bridges_snapshot_id_itself():
    book = OrderBookSync()
    book.begin_buffering()
    book.load_snapshot(100, [["10", "2"]], [["11", "3"]])
    book.bridge_first_delta(98, 102, [], [], bridge_id=100)
    assert book.state == BookState.VALID
    assert book.last_update_id == 102


def test_usdm_keeps_event_ending_at_snapshot_id():
    events = [{"U": 98, "u": 100}, {"U": 101, "u": 102}]
    _drop_stale("usdm", events, 100)
    assert events[0] == {"U": 98, "u": 100}
    assert _candidate_is_bridge("usdm", events[0], 100)
