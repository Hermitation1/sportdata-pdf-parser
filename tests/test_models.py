from datetime import datetime

from app.models import ContestFront, PlaceFront, _norm_rank


def test_clean_ekp_extracts_16_digits():
    contest = ContestFront.model_validate({"ekp": "ЕКП 1234567890123456 текст"})
    assert contest.ekp == "1234567890123456"


def test_clean_ekp_without_digits_keeps_value():
    contest = ContestFront.model_validate({"ekp": "нет номера"})
    assert contest.ekp == "нет номера"


def test_clean_ekp_none_returns_empty():
    contest = ContestFront.model_validate({"ekp": None})
    assert contest.ekp == ""


def test_fix_date_full_iso():
    contest = ContestFront.model_validate({"beginning": "28.01.2026", "ending": "02.02.2026"})
    assert contest.beginning == "2026-01-28"
    assert contest.ending == "2026-02-02"


def test_fix_date_short_year_uses_current_year():
    contest = ContestFront.model_validate({"beginning": "28.01"})
    assert contest.beginning == f"{datetime.now().year}-01-28"


def test_fix_date_empty_stays_empty():
    contest = ContestFront.model_validate({"beginning": ""})
    assert contest.beginning == ""


def test_coerce_place_numeric_string():
    place = PlaceFront.model_validate({"place": "1"})
    assert place.place == 1


def test_coerce_place_invalid_to_none():
    place = PlaceFront.model_validate({"place": "DNS"})
    assert place.place is None


def test_norm_qual_maps_russian_ranks():
    place = PlaceFront.model_validate({"qualificationCategory": "кмс"})
    assert place.qualification_category == "KMS"


def test_alias_qualification_category():
    place = PlaceFront.model_validate({"qualificationCategory": "1"})
    assert place.qualification_category == "R1"


def test_norm_rank_mapping():
    assert _norm_rank("мс") == "MS"
    assert _norm_rank("кмс") == "KMS"
    assert _norm_rank("1") == "R1"
    assert _norm_rank("б/р") == "BR"


def test_contest_defaults():
    contest = ContestFront.model_validate({})
    assert contest.title == ""
    assert contest.participant_total == 0
    assert contest.sports == []
    assert contest.total_subjects == []
