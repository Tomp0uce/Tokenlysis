from backend.app.services.scoring import (
    _normalize,
    score_liquidite,
    score_opportunite,
    score_global,
)


def test_normalization_clamps_and_scales():
    values = list(range(1, 21))
    scores = _normalize(values)
    assert scores[0] == 0
    assert scores[-1] == 100
    # middle value around index 10 should be roughly 50
    assert abs(scores[10] - 50) <= 10


def test_scoring_categories_and_global():
    volume = [10 * i for i in range(1, 21)]
    market_cap = [100 * i for i in range(1, 21)]
    listings = list(range(1, 21))
    rsi_values = [30 + i for i in range(20)]
    volchg = [i for i in range(20)]

    liq = score_liquidite(volume, market_cap, listings)
    opp = score_opportunite(rsi_values, volchg)
    glob = score_global(liq, opp)

    assert len(liq) == len(opp) == len(glob) == 20
    for liq_score, opp_score, glob_score in zip(liq, opp, glob):
        assert 0 <= liq_score <= 100
        assert 0 <= opp_score <= 100
        assert glob_score == round((liq_score + opp_score) / 2)
