---
target: Run-Detailansicht mit unklarer Aggregation angleichen
total_score: 20
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 3
target_identity: "file:/home/westphal/Projekte/BBAW/gendertagger/repo/gendertagger/frontend/src/features/runs/RunDetailView.vue"
target_fingerprint: "sha256:cf8bc4d159ddef621b0a21c7603c76e57391273e8b7cb16cbd7d76ebf1654d2c"
target_path: /home/westphal/Projekte/BBAW/gendertagger/repo/gendertagger/frontend/src/features/runs/RunDetailView.vue
timestamp: 2026-09-26T09-40-41Z
slug: frontend-src-features-runs-rundetailview-vue
---
Method: dual-agent (A: RunDetailDesignReview · B: RunDetailEvidenceScan)

## Design Health Score

| # | Heuristik | Score | Kernproblem |
|---|---|---:|---|
| 1 | Sichtbarkeit des Systemstatus | 3/4 | Lauf und Methoden sind transparent; Entstehung und Bedeutung der Aggregation bleiben unsichtbar. |
| 2 | Übereinstimmung mit der realen Arbeitswelt | 2/4 | `reference_v1`, „9 Methodenausführungen“ und Hashes dominieren gegenüber dem redaktionellen Ergebnis. |
| 3 | Kontrolle und Freiheit | 2/4 | Die Standardaggregation kann beim Seitenaufruf automatisch entstehen, ohne klaren Ursprung oder Abbruchpfad. |
| 4 | Konsistenz und Standards | 2/4 | Die Ansicht weicht von Datenstand-, Auswertungs- und Exportansichten ab: keine beschriftete Faktengruppe, keine klare Aktion/Verlauf-Trennung. |
| 5 | Fehlervermeidung | 2/4 | Zehn beliebige Methoden lassen sich auswählen, obwohl `reference_v1` nur gültige Kombinationen akzeptiert. |
| 6 | Wiedererkennen statt Erinnern | 2/4 | „9 von 10“ zwingt Nutzende, die fehlgeschlagene bzw. ausgeschlossene Methode selbst herzuleiten. |
| 7 | Flexibilität und Effizienz | 1/4 | Kein kompakter Abschlusszustand, Sprung zum Fehler oder zur Aggregation, Filter oder „alle einklappen“. |
| 8 | Ästhetik und Minimalismus | 2/4 | Ruhige Gestaltung, aber zehn abgeschlossene Methodenkarten und volle Fortschrittsbalken verdrängen das eigentliche Arbeitsergebnis. |
| 9 | Fehler erkennen und beheben | 2/4 | Fehler sind benannt, aber „mit Fehlern abgeschlossen“ erklärt weder Folge noch empfohlenen nächsten Schritt. |
| 10 | Hilfe und Dokumentation | 2/4 | Hinweise existieren, erklären aber weder automatische Aggregation noch Auswahlabweichung oder nächsten redaktionellen Schritt. |
| **Gesamt** |  | **20/40** | **Akzeptabel, aber deutliche Workflow- und Hierarchieprobleme** |

**Kognitive Last:** 5 von 8 Kriterien fallen durch — hoher unnötiger Aufwand. Betroffen: eindeutiger Fokus, Chunking, visuelle Hierarchie, minimale Auswahlmenge und Arbeitsgedächtnis.

## Design-Spezifität

**Designurteil:** Inhaltlich gendertagger-spezifisch, strukturell zu nah an einem generischen Job-/CI-Runner.

Die ruhige Archivästhetik, exakte Statusangaben, Unsicherheit und Provenienz passen sehr gut zum Produkt. Die Komposition erzählt aber nicht den entscheidenden fachlichen Übergang: unabhängige Methoden werden zu einem gemeinsamen Arbeitsergebnis für Prüfung, Auswertung und Export. Stattdessen erscheint die Aggregation wie ein weiteres technisches Logelement nach zehn Methodenkarten.

**Deterministischer Scan:** Der CLI-Scan über `RunDetailView.vue`, `AggregationSection.vue`, `ExecutionCard.vue` und `RunProvenance.vue` war sauber: **0 Findings**, Exit 0. Der Browser-Detektor meldete zwölf DOM-Auffälligkeiten:

- 3× lange Textzeilen, davon die sichtbare Aggregationsbeschreibung in `AggregationSection.vue:160` relevant.
- 7× vermeintliche Textüberdeckung in geschlossenen Methoden-Provenienzbereichen; diese sind False Positives.
- 2× Sidebar-Breitenübergang außerhalb des Zielbereichs; für diese Ansicht nicht relevant.

**Browser-/A11y-Evidenz:**

- Desktop: Aggregation beginnt erst bei ca. `y=1819`, also rund 1,8 Viewports unter dem Einstieg.
- Mobile: Aggregation beginnt bei ca. `y=1878`, rund 2,2 Viewports unter dem Einstieg.
- Kein horizontaler Seitenüberlauf bei 1440, 390 oder 320 CSS px.
- Axe: 0 Verstöße, 0 unvollständige Prüfungen, 26 bestandene Checks.
- Die Live-Overlays wurden erfolgreich injiziert und ausgewertet, anschließend für den sauberen Axe-Lauf entfernt; sie sind daher nicht mehr im Browser sichtbar.

## Gesamteindruck

Der Einstieg schafft Vertrauen: „Mit Fehlern abgeschlossen“, `69 von 70`, genaue Methodenstände und reproduzierbare Provenienz. Danach wird die Seite zu einem langen technischen Prüfprotokoll. Das entscheidende Ergebnis kommt zu spät und beantwortet nicht: **Was wurde zusammengeführt, warum nur neun Methoden, ist das Ergebnis prüfbar und was soll ich jetzt tun?**

Die größte Chance: Eine abgeschlossene Ausführung nicht länger wie einen laufenden Monitor behandeln, sondern wie ein **Ergebnisprotokoll mit einer klaren nächsten redaktionellen Handlung**.

## Was funktioniert

1. **Ehrliche Evidenzdarstellung:** Fehler, fehlende Resultate und Teilstände werden nicht beschönigt.
2. **Gute responsive Basis:** Die Ansicht fließt bis 320 px sauber um; Provenienz bleibt progressiv verborgen.
3. **Solide Semantik:** Ein H1, benannte Abschnitte, Listen, Definitionslisten, Fieldset/Legend, beschriftete Fortschrittsanzeigen und textliche Statuswerte.

## Prioritätsprobleme

### [P1] Die Aggregation ist vergraben und fachlich undurchsichtig

**Warum relevant:** Sie ist das kombinierte Arbeitsergebnis, erhält aber weniger Gewicht als zehn abgeschlossene Methodenprotokolle. „Completed · reference_v1 · 9 method executions · Hash“ erklärt weder Nutzen noch nächsten Schritt.

**Fix:** Direkt unter dem Laufstatus einen Bereich **„Kombiniertes Ergebnis“** zeigen: verständlicher Strategiename, Zustand, verwendete Methoden, Abweichungen und eine primäre Aktion **„Kombiniertes Ergebnis prüfen“**. „Aggregationsdetails und Provenienz“ bleibt sekundär.

**Vorgeschlagener Befehl:** `/impeccable shape`

### [P1] „9 von 10 Methoden“ erzwingt eine eigene Rekonstruktion

**Warum relevant:** Eine Methode hat einen Fehler, die Aggregation verwendet neun Methoden, aber die Ansicht nennt weder die neun noch den Ausschluss. Das schwächt die Nachvollziehbarkeit genau an der wichtigsten fachlichen Stelle.

**Fix:** Verwendete Methoden direkt oder in einem klar benannten Disclosure anzeigen. Abweichung explizit formulieren: etwa „9 abgeschlossene Methoden verwendet; `hivoto_xgboost` nicht enthalten“. Nur Gründe behaupten, die das Backend sicher liefert.

**Vorgeschlagener Befehl:** `/impeccable clarify`

### [P1] Aktuelles Ergebnis, automatische Erstellung, Verlauf und Neuerstellung sind vermischt

**Warum relevant:** Die Standardaggregation kann automatisch entstehen, während die Oberfläche wie eine passive Liste wirkt. „Weitere Aggregation anlegen“ erklärt nicht, was sich gegenüber dem aktuellen Ergebnis ändert.

**Fix:** Wie Auswertungs- und Exportansichten strukturieren:

1. **Aktuelles kombiniertes Ergebnis**
2. **Weitere Aggregation erstellen** als erweiterter Operatorpfad
3. **Frühere Aggregationen** nur bei mehreren Einträgen

Automatische Entstehung und laufender Zustand werden explizit benannt.

**Vorgeschlagener Befehl:** `/impeccable shape`

### [P2] Abgeschlossene Methodenkarten dominieren die Seite

**Warum relevant:** Zehn nahezu gleiche Karten mit vollen Fortschrittsbalken erzeugen mehr als 1.400 px Scrollstrecke und verstecken den einzigen Fehler sowie das Ergebnis.

**Fix:** Für terminale Läufe eine kompakte Methodenübersicht verwenden: Methode, Status, Ergebniszahl und Aktion. Nur problematische Methoden erhalten zusätzliche visuelle und textliche Aufmerksamkeit. Laufende Läufe dürfen den ausführlicheren Monitor behalten.

**Vorgeschlagener Befehl:** `/impeccable distill`

### [P2] Kontrollnamen und mobile Trefferflächen sind zu schwach

**Warum relevant:** Zehn Disclosures heißen im Accessibility Tree identisch „Method provenance“. „Open aggregation“ wäre bei mehreren Einträgen ebenfalls mehrdeutig. Mehrere mobile Ziele messen nur ca. 19–20 px Höhe statt der vorgesehenen 44 px bei grobem Pointer.

**Fix:** Kontextuelle Namen wie „Methodenprovenienz für GND“ und „Referenzaggregation vom … öffnen“; Disclosure- und Linkflächen auf die vorhandene mobile Kontrollhöhe bringen.

**Vorgeschlagener Befehl:** `/impeccable audit`

## Persona-Warnsignale

**Alex – Power User:** Muss zehn Karten bzw. zwanzig methodenbezogene Controls passieren, bevor das kombinierte Ergebnis erreichbar ist. Kein Sprung zum Fehler, zur Aggregation oder kompakter Abschlussmodus.

**Sam – Screenreader-/Tastaturnutzer:** Gute Grundsemantik, aber zehn gleich benannte „Method provenance“-Controls. Status und Datum sind unbeschriftete Spans. Die wichtigste Aktion folgt erst nach der gesamten Methodenliste.

**Mara – wissenschaftliche Operatorin/Redakteurin:** Sie sieht einen Methodenfehler und eine fertige 9-Methoden-Aggregation, kann auf dieser Seite aber nicht entscheiden, ob genau die erwartete Evidenz verwendet wurde und ob das Ergebnis jetzt sicher in die Prüfung gehen kann.

## Kleinere Beobachtungen

- „Lauf“ als H1 ist deutlich weniger orientierend als der datierte Titel der Datenstandansicht.
- Der Laufzeitpunkt hat kein sichtbares Label wie „Angelegt“.
- Der volle 64-stellige Hash wird mobil zum größten Fakt innerhalb der Aggregationskarte; gekürzte Anzeige plus vollständige Provenienz wäre klarer.
- „Auswertungen dieses Laufs“ und „Exporte dieses Laufs“ stehen gleichgewichtet vor dem eigentlichen kombinierten Ergebnis.
- Die Seite endet emotional auf Provenienz statt auf einem klaren nächsten Schritt.

## Leitfragen

- Wenn die Aggregation das prüfbare Arbeitsergebnis ist: Warum steht sie hinter jedem Methodenprotokoll?
- Darf „9 Methodenausführungen“ jemals ohne sichtbare Auflösung der neun erscheinen?
- Ist `reference_v1` ein Nutzungsbegriff oder ein Provenienz-Identifier unter einem verständlichen Label „Referenzaggregation“?
- Sollte ein abgeschlossener Lauf eine andere Hierarchie als ein laufender Lauf haben?
