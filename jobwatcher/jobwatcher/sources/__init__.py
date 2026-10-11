"""Jobquellen. Jede Quelle liefert eine Liste von Job-Objekten und kann Details nachladen."""
from . import ba, kleinanzeigen, linkedin, stepstone, xing

SOURCES = {
    "ba": ba,
    "stepstone": stepstone,
    "linkedin": linkedin,
    "kleinanzeigen": kleinanzeigen,
    "xing": xing,
}
