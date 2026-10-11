from jobwatcher.config import load_config
from jobwatcher.models import Job
from jobwatcher.rules import classify, parse_wage, score

CFG = load_config()


def job(title, text="", **kw):
    return score(Job(source="ba", source_id=title, title=title, url="u", snippet=text, **kw), CFG)


def test_ueberfuehrung_minijob_weekend_scores_high():
    j = job("Fahrer für Fahrzeugüberführungen (m/w/d) Minijob",
            "Einsätze am Wochenende, flexible Einteilung, 15 €/Std.", distance_km=12)
    assert j.category == "ueberfuehrung"
    assert not j.excluded
    assert j.rule_score >= 8.5


def test_lkw_excluded():
    assert job("LKW-Fahrer CE (m/w/d) Minijob").excluded


def test_selbststaendig_excluded():
    assert job("Überführungsfahrer (m/w/d)", "als selbstständiger Subunternehmer").excluded


def test_age_requirement_excluded():
    j = job("Transferfahrer Minijob", "Führerschein Klasse B seit mindestens 2 Jahren. Mindestens 25 Jahre alt.")
    assert j.excluded == "Mindestalter 25"


def test_license_years_ok_and_too_many():
    assert not job("Transferfahrer Minijob", "Führerschein Klasse B seit mindestens 3 Jahren").excluded
    assert job("Transferfahrer Minijob", "Führerschein seit mindestens 7 Jahren").excluded


def test_plz_is_not_minijob_hint():
    j = job("Verkäufer (m/w/d)", "60311 Frankfurt, Teilzeit")
    assert "Minijob" not in j.rule_notes


def test_too_far_excluded():
    assert job("Fahrer Minijob", distance_km=80).excluded


def test_other_job_capped_without_ai():
    j = job("Aushilfe Service Minijob", "Wochenende, flexibel, 20 €/h", distance_km=3)
    assert j.category == "sonstiges"
    assert j.rule_score <= 6.5


def test_classify_and_wage():
    assert classify("Mitarbeiter Hol- und Bringservice") == "ueberfuehrung"
    assert classify("Kurierfahrer") == "fahrer"
    assert classify("Kassierer") == "sonstiges"
    assert parse_wage("Wir zahlen 14,50 € pro Stunde") == 14.5
    assert parse_wage("PLZ 63303, 603 € Basis") is None
