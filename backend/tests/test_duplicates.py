from app.services.duplicates import haversine_m, score_pair


def test_nearby_same_pothole_is_possible_duplicate():
    reasons = score_pair(
        lon1=91.099,
        lat1=22.869,
        lon2=91.0991,
        lat2=22.86905,
        category1="pothole",
        category2="pothole",
        text1="Large pothole on Station Road near the court.",
        text2="Big pothole on Station Road by the court.",
        hours_apart=48,
    )
    assert reasons.distance_m < 30
    assert reasons.suggested_label() == "possible_duplicate"
    assert reasons.total >= 70


def test_far_away_is_not_a_strong_match():
    reasons = score_pair(
        lon1=91.099,
        lat1=22.869,
        lon2=91.12,
        lat2=22.89,
        category1="pothole",
        category2="garbage",
        text1="Pothole on Station Road",
        text2="Garbage pile near the market",
        hours_apart=24,
    )
    assert reasons.distance_m > 120
    assert reasons.distance_points == 0
    assert reasons.suggested_label() == "weak"


def test_haversine_zero_for_same_point():
    assert haversine_m(91.1, 22.8, 91.1, 22.8) == 0
