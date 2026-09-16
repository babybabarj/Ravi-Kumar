import pytest

from btceth_os.orderbook import OrderBookSync, BookState, SequenceGap


def _bridged_usdm_book() -> OrderBookSync:
    book = OrderBookSync()
    book.begin_buffering()
    book.load_snapshot(100, [["10", "2"]], [["11", "3"]])
    book.bridge_first_delta(95, 105, [], [], bridge_id=100)
    assert book.state == BookState.VALID
    assert book.last_update_id == 105
    return book


def test_usdm_pu_continuity_allows_large_U_jump():
    book = _bridged_usdm_book()
    # Mirrors the live Mac failure shape: U can jump well beyond previous_u + 1.
    # Binance USD-M continuity is proved by pu == previous u.
    book.apply_delta(
        130,
        160,
        [["10", "1"]],
        [],
        previous_final_id=105,
    )
    assert book.state == BookState.VALID
    assert book.last_update_id == 160


def test_usdm_wrong_pu_still_forces_resync():
    book = _bridged_usdm_book()
    with pytest.raises(SequenceGap):
        book.apply_delta(130, 160, [], [], previous_final_id=104)
    assert book.state == BookState.INVALID
