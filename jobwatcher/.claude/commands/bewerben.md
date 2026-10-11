---
description: Bewerbung für einen Treffer des Job-Watchers vorbereiten und nach Freigabe absenden
argument-hint: <Job-ID aus dem Push, z. B. ba:10001-1003648922-S>
---

Bereite eine Bewerbung für den Job `$ARGUMENTS` vor. Arbeite auf Deutsch.

1. **Job laden.** Führe `git fetch -q origin jobwatcher-state` aus und lies den Eintrag mit dem Schlüssel
   `$ARGUMENTS` aus `git show origin/jobwatcher-state:jobs.json`. Ist `$ARGUMENTS` leer oder nicht vorhanden,
   zeige die 5 besten aktiven Treffer (höchste `ai_score`, sonst `rule_score`) mit ID und frage, welcher es sein soll.
2. **Profil laden.** Lies `bewerbung/profil.md`. Fehlt die Datei, kopiere `bewerbung/profil.example.md` dorthin,
   bitte mich, sie auszufüllen, und brich ab.
3. **Anzeige prüfen.** Öffne die `url` des Jobs (Claude in Chrome, sonst WebFetch). Finde heraus:
   Bewerbungsweg (E-Mail, Formular, Portal-Schnellbewerbung, Telefon), Ansprechperson, verlangte Unterlagen,
   und ob es wirklich ein Minijob ist. Prüfe Ausschlussgründe aus dem Profil (Mindestalter, Führerscheinjahre,
   Selbstständigkeit, Arbeitszeiten). Passt etwas nicht, sag es mir in einem Satz, bevor du weitermachst.
4. **Entwurf.** Schreibe ein kurzes Anschreiben (max. 120 Wörter, Ton laut Profil): warum ich passe
   (Führerschein B seit 5 Jahren, eigenes Auto, zuverlässig, Erfahrung als Fahrer bei Flaschenpost),
   wann ich kann (Wochenende, Mo–Fr ab 17:30), Start ab sofort. Keine erfundenen Fakten.
   Speichere es als `bewerbung/entwuerfe/<JJJJ-MM-TT>-<firma>.md` mit Job-Link oben.
5. **Ausfüllen.** Bereite die Bewerbung im gefundenen Weg vor:
   - Formular/Portal: mit Claude in Chrome ausfüllen, Lebenslauf aus dem Profilpfad hochladen, **nicht absenden**.
   - E-Mail: Entwurf mit Betreff „Bewerbung als <Titel> (Minijob)“ und Lebenslauf als Anhang anlegen
     (Gmail-Connector, sonst `mailto:`-Link), **nicht senden**.
   - Nur Telefon: gib mir Nummer, Ansprechperson und 3 Stichpunkte für das Gespräch.
6. **Freigabe.** Zeig mir eine Zusammenfassung: Firma, Job, Weg, Empfänger, Anschreiben, Anhänge.
   Frage: „Absenden? (ja/nein/ändern)“. Sende **nur nach einem ausdrücklichen „ja“**.
7. **Protokoll.** Hänge eine Zeile an `bewerbung/log.md` an: Datum, Job-ID, Firma, Titel, Weg, Status
   (gesendet / Entwurf / abgebrochen).
