from btceth_os.orderbook import OrderBookSync, BookState


def test_spot_first_event_may_start_at_snapshot_plus_one():
    book = OrderBookSync()
    book.begin_buffering()
    book.load_snapshot(100, [["10", "2"]], [["11", "3"]])
    # Valid Spot case after dropping u <= lastUpdateId: the first applicable
    # diff can begin exactly at the next expected update id.
    book.bridge_first_delta(101, 103, [["10", "1"]], [], bridge_id=101)
    assert book.state == BookState.VALID
    assert book.last_update_id == 103


def test_usdm_first_event_bridges_snapshot_id_itself():
    book = OrderBookSync()
    book.begin_buffering()
    book.load_snapshot(100, [["10", "2"]], [["11", "3"]])
    book.bridge_first_delta(98, 102, [], [], bridge_id=100)
    assert book.state == BookState.VALID
    assert book.last_update_id == 102
