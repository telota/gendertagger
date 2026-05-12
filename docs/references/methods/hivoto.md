
Dokumentation zum
Historischen Vornamentool – hivoto.
Datensatz für die Normierung und Geschlechtszuweisung anhand
von historischen, deutschsprachigen Vornamen und abgekürzten
Vornamen (1630-1965)
1. Steckbrief
Name des Tools
Historisches Vornamentool - hivoto
Version
1.0.0
Status
des
zugrundeliegenden
Datensatzes
Transkribierte, automatisiert erkannte, bereinigte Daten
mit erfolgten Anreicherungen: Einordnung als abgekürzte
oder ausgeschriebene Form, Zuweisung wahrscheinliches
Geschlecht, Angabe Sicherheit Geschlechtszuweisung,
Angabe Sicherheit Namenszuordnung, Kategorisierung
von Varianten, Erste Normierungsschritte
Sprache
Deutsch


DOI
10.22000/pwbupf0jc2zj4k7x
Urheberschaft
Katja Liebing [0009-0001-1624-6465]
Bearbeitung
Historisches Datenzentrum Sachsen-Anhalt
Datenkuration
Katja Liebing [0009-0001-1624-6465], Katrin Moeller
[0000-0003-4090-5667], Isabel Groß [0009-0007-6566-
4691]
Technisches Datenmanagement
Olaf Simons [0000-0001-9230-4666]
Zeitraum der Quellen
1630-1965
Jahr der Digitalisierung
2014-2020
Jahr der Transkription
2014-2026
Publikation
2026-02-15
Entstehungsort
Halle (Saale)
Herausgabeort
Halle (Saale)
Datenformat
SPSS, CSV, Dokumentation (PDF)
Herausgeberschaft
Historisches Datenzentrum Sachsen-Anhalt,
Emil-Abderhalden-Straße 26/27
06108 Halle
Tel. 0356/55 24 286
E-Mail: hinfo@geschichte.uni-halle.de
ISIL: [DE-4218]
Kontakt
ta2-nfdi4memory@geschichte.uni-halle.de
Schlagwörter
Vorname,
Personenname,
Geschlecht,
historischer
Vorname,
Geschichtswissenschaft,
Geschichte,
Männername,
Frauenname,
Gender,
Namenkunde,
Personennamenkunde,
Wortschatz,
Terminologie,
Standardisierung, Vokabular
Funktion
Geschlechtszuweisung,
Namensdisambiguierung,
Normierung von Vornamen, LOD


Lizenz
CC BY-NC-SA: Attribution-NonCommercial-ShareAlike 4.0
Entstehungskontext
Service im Rahmen von NFDI4Memory
Projektnummer (DFG)
501609550 (NFD4Memory)
2. Einleitung
Mit der vorliegenden Dokumentation soll das historische Vornamentool hivoto erläutert sowie die
ihm zugrundeliegenden Überlegungen, die angewandte Methode und das Vorgehen bei seiner
Erstellung dargestellt werden.
hivoto wurde als Service im Rahmen der NFDI-4Memory-Arbeitsgruppe Data Connectivity (TA2) am
Historischen
Datenzentrum
Sachsen-Anhalt
entwickelt.
Es
dient
der
Normierung,
Informationsanreicherung, Disambiguierung und Kontextualisierung von personenbezogenen Daten
und unterstützt damit die digitale Aufbereitung, Detektierung und Analyse historischer Daten. Seine
Hauptfunktion ist es, Vornamen ein wahrscheinliches Geschlecht zuzuordnen. Dabei kann auf einen
Datensatz von momentan 201.972 Variantenschreibungen zurückgegriffen werden, der historische
Fehlschreibungen, Schreibvarianten, Sprachvarianten und Abkürzungen enthält. Die Varianten
werden in einer Normschreibung zugewiesen. Der Normierungsprozess befindet sich in Bearbeitung,
bisher können ca. 17.800 Schreibungen Normschreibweisen genutzt werden. In einer weiteren
Version sollen diese Normierungsprozesse noch weitergeführt und weitere Varianten zugesetzt
werden.
3. Vorüberlegungen
Hintergrund
Es existiert eine unüberschaubare Masse serieller historischer Quellen mit einer Fülle
personenbezogener Daten, die für geschichtswissenschaftliche Untersuchungen eine hohe Relevanz
besitzt. Sie ermöglichen durch statistische Analysen etwa mikrogeschichtliche und sozialgeschichtliche

Ansätze, indem sie auch Personen und Personengruppen abbilden, über deren Leben und Wirken
aufgrund zeitgenössischer Machtverhältnisse kaum historische Informationen überliefert sind.
In einem digitalen Workflow können diese Quellen nicht nur als Retrodigitalisat erkannt, sondern mit
Texterkennung automatisiert transkribiert und über Named Entity Recognition spezifischen Entitäten
(Vorname, Nachname, Beruf, Adresse etc.) zugeordnet werden. Ein Nachteil der automatischen
Transkription ist jedoch das Fehlen von Kontextinformationen, da bei der bisherigen manuellen
Transkription Bearbeitende das Geschlecht einer Person während dieses Prozesses ermittelten und
erfassten. Zwar ermöglicht die Named Entity Recognition die Zuordnung von Entitäten wie Berufen,
Orten, Nachnamen und Vornamen, die Geschlechtsinformation bleibt dabei jedoch unbestimmt
(Boros et al. 2020; Ehrmann et al. 2024).
Vornamen sind nicht nur für die Identifikation von Personen relevant, sondern ebenso für die
Informationsanreicherung, Disambiguierung und Kontextualisierung, um Daten digital analysieren zu
können. Sie transportieren explizit und implizit Informationen, von denen das Geschlecht wohl die
prägendste ist.
Der quellenbasierte Ansatz von hivoto bringt es mit sich, dass originalsprachliche Vornamen erfasst
sind, die auch zahlreiche sprachliche Varianten, Abkürzungen und Fehlschreibungen enthalten. Dies
erleichtert den Abgleich mit historischen Quellen deutlich und ermöglicht eine bessere Verknüpfung
von Normnamen. Dabei werden gerade für Abkürzungen die typischen historischen Varianten einer
Hauptverwendung zugeordnet, aber auch Alternativvorschläge unterbreitet.
Problematisierung Vorname und Geschlecht
Vornamen werden in aller Regel durch erwachsene Bezugspersonen an Kinder im Säuglingsalter
vergeben. Im deutschsprachigen Raum erfolgt die Namensvergabe meist durch die Eltern, teilweise
auch durch Pat:innen oder andere Verwandte. Dabei folgen die Namensgebenden gesellschaftlichen
Normen, Konventionen und – in der Gegenwart – auch gesetzlichen Bestimmungen.1 Religiöse,
traditionelle, familiäre und allgemein konventionelle Einflüsse werden berücksichtigt (Alford 1988, 30,
1 Für eine vergleichende Studie zur Gesetzeslage in Deutschland und den USA und der Frage zur Einhaltung
sprachlicher Normen bei gesetzlich freier Namenswahl siehe: Gerhards 2010.


36, 51f.). Die gewählten Vornamen vermitteln implizit wie explizit Informationen, etwa religiöse
Bezüge bei Heiligennamen, erwünschte Eigenschaften oder Bezüge zu Namen von Eltern, Großeltern,
vorbildhaften Personen oder Idolen. Die bei weitem häufigste Information ist dabei die über das
Geschlecht (Alford 1988, 65; Blevins und Mullen 2015, 2).
In historischen Kontexten folgt die Einteilung in zwei Geschlechter in der Regel einem binären System
von männlich und weiblich. Ausschlaggebend bei der Namenswahl ist das bei der Geburt festgestellte
biologische Geschlecht (sex). Anhand dessen wird das soziale Geschlecht (gender) konstruiert und mit
dem Vornamen an das Kind und die Umwelt vermittelt (Oelkers 2004, 133; Gerhards 2010, 168 f.). In
diesem Zusammenhang wurde der Begriff sex-category vorgeschlagen, der jenes Geschlecht
beschreibt, das einer Person anhand angeborener, erkennbarer Merkmale sozial zugeschrieben und
über Marker wie den Vornamen kenntlich gemacht wird (West und Zimmerman, 131–35; Gerhards
2010, 156 ff.; Gildemeister 2019, 413).
Wenn mittels Tools auf Basis von Vornamen das wahrscheinliche Geschlecht bestimmt wird, ist
vordergründig diese sex-category gemeint, die durch den Namen ausgedrückt wird. Diese deckt sich
nicht zwangsläufig mit der Geschlechtsidentität des namentragenden Individuums, da Namen in der
Regel ohne Einfluss der benannten Person vergeben werden und Umbenennungen je nach
gesellschaftlichem und historischem Kontext nur eingeschränkt möglich sind. Dies gilt insbesondere
für historische Massenquellen, in denen über die Lebensumstände der Menschen keine größeren
Kontextinformationen erkennbar werden.
Trotz der damit verbundenen ethischen Problematik ist es für geschichtswissenschaftliche
Fragestellungen relevant, Aussagen über das wahrscheinliche Geschlecht von Personen auf Basis
statistischer Untersuchungen zu integrieren. Dies kann zur Sichtbarmachung von Frauen oder
anderweitig marginalisierten Personengruppen beitragen, auch wenn der Widerspruch einer
potenziellen Fremdzuschreibung für das einzelne Individuum nicht aufgelöst werden kann (Blevins
und Mullen 2015, 7–8).
Zuschreibungen anhand von Wahrscheinlichkeitsabwägungen sind in den Geschichtswissenschaften
gängig, etwa bei der Erstellung biografischer Lexika, der Analyse von Editionen oder Textkorpora sowie
der Auswertung serieller Quellen. Auch unter Einbezug sozialer Rollen oder Berufe verbleibt hierbei
eine Unsicherheit, da das Individuum in vielen Fällen nicht mehr befragt werden kann. Selbst eine


Befragung würde unter gesellschaftlichem Druck oder eingeschränkter individueller Freiheit nicht
zwangsläufig die empfundene Identität widerspiegeln.
Personennamen finden sich in Schriftquellen seit dem Bestehen von Schrift. Sie dienen nicht nur der
Identifikation und Unterscheidung von Personen, sondern transportieren stets weitere
Informationen. Namen können Eigenschaften zuschreiben, Assoziationen hervorrufen, auf
Familienzugehörigkeiten verweisen sowie Herkunft oder Geschlecht einer Person anzeigen. Dabei
handelt es sich um Zuschreibungen, die durch die namensgebenden Personen – zumeist die Eltern –
im Rahmen gesellschaftlicher Regeln, Normen und Erwartungen vorgenommen werden. Diese Regeln
und Normen variieren je nach zeitlichem und kulturellem Kontext.
Insofern bildet der bei Geburt oder Taufe vergebene Vorname in amtlichen Quellen häufig das zu
diesem Zeitpunkt zugeschriebene, anhand biologischer Merkmale bestimmte Geschlecht ab. Stimmt
dieses nicht mit der späteren Geschlechtsidentität überein, bleibt dies in Quellen wie Adressbüchern
oder Kirchenbüchern meist unsichtbar.
Problematisierung von Sprache, kulturellem Hintergrund und
Vornamen
Das Geschlecht eines Namens wie auch andere assoziierte Informationen werden durch verschiedene
Wege erkennbar gemacht. Dies können phonetische Kennzeichnungen sein. So enden im Deutschen
weiblich gelesene Namen häufig auf „a“ oder „e“, während männlich gelesene Namen auf „n“, „s“,
„d“ oder „r“ enden (Gerhards 2010, 167). Einige Vornamen besitzen eine Semantik, die an spezifische
Attribute und/oder soziale Rollenbilder geknüpft ist. So sind manche Frauennamen an Blumennamen
orientiert, einige männliche Vornamen wie etwa Hermann oder Bernhard enthalten Begriffe von
Kampf oder Stärke. Daneben existiert aber auch eine Vielzahl an Vornamen, deren zugehöriges
Geschlecht ausschließlich durch Konvention bestimmt ist. Mitglieder der Gesellschaft lernen diese
Zuordnung ähnlich sprachlichen Ausnahmeregelungen im Laufe ihrer Sozialisation (Alford 1988, 66;
Oelkers 2004, 134 f.; Gerhards 2010, 162).
Daher ist es mitunter schwierig oder führt zu Missverständnissen, wenn Personen mit Vornamen aus
anderen Sprachen und Kulturen konfrontiert sind. Hier können phonetische Regeln anders sein, wie
etwa bei dem Namen Andrea, der im Italienischen unisex verwendet wird, bis hin zu Namen, die im


eigenen Sprachraum noch neu sind. Hinzu kommen andere Anordnungen von Vor- und Nachnamen,
die anders gereiht sein oder ganz anderen Regeln folgen können.
Das historische Vornamentool wurde mit Fokus auf den deutschen Sprachraum erstellt. Der Großteil
der zugrunde liegenden Quellen ist hier verortet. Im hervorgegangenen Datenmaterial sind aufgrund
von Migration – sowohl von Personen als auch von Vornamen – zahlreiche Namen anderer Sprachen
enthalten, wobei die meisten aus dem weiteren europäischen Raum stammen. Die Bearbeitenden von
hivoto sind deutsche Muttersprachler:innen und unterliegen damit einem gewissen Bias. Dieser wurde
zu minimieren versucht, indem insbesondere vor einer Zuordnung als Fehlschreibung eine
Überprüfung des Vornamens als Sprachvariante erfolgte, auch wenn eine Fehlschreibung nahe lag.
4. Vorgehen und Methodik
Das Tool wurde auf der Grundlage von 10,5 Mio. historischen Namensnennungen aus den mehr als
9.000 digitalisierten Adressbüchern des Vereins für Computergenealogie erstellt. Diese reichen
vereinzelt bis in das 17. Jahrhundert zurück, stammen aber überwiegend aus dem 19. und frühen 20.
Jahrhundert. Jeweils eine Schreibvariante dieser Vornamen wurde in hivoto integriert, wobei der
Mehrwert vor allem in der Fülle von Abkürzungen und bereits normierten Namensschreibweisen liegt,
die sich zudem räumlich auf das gesamte Deutsche Reich dieser Zeit verteilen (Verein für
Computergenealogie 2023; Moeller und Fertig 2023).
Hinzu kommen ca. 80.000 Einträge aus Sterbe-, Geburts- und Heiratsregistern der Mariengemeinde
zu Halle an der Saale aus den Jahren 1670–1820 sowie umfangreicher weiterer Datensammlungen des
Historischen Datenzentrums Sachsen-Anhalt (Datensammlung des Historischen Datenzentrums
Sachsen-Anhalt). Sie repräsentieren zwar lokal eingeschränkte Varianten, bieten jedoch den Vorteil
von Quellentranskripten, die als echte Schreib- und Sprachvarianten betrachtet werden können
(Moeller und Kühne 2014, 2015a, 2015b). Zudem ergänzen diese Schreibvarianten den Zeitraum des
18. Jahrhunderts.
Weiterhin wurden 11.497 Vornamen aus der Wikibase-Instanz FactGrid ergänzt, die hier von
Nutzenden als Objekt der entsprechenden Property angelegt und mit einer Geschlechtszuweisung
versehen wurden (FactGrid-Community und Olaf Simons (Hg.): FactGrid, a database for historians.
Property:P248 (Vorname(n)), Gotha 2024 (). Der Datensatz wurde schließlich noch durch die in


Wikipedia erhältliche “Liste von Vornamen” ergänzt, die per Skript verarbeitet und zugeordnet
wurden (Wikipedia 2025). Der Nachteil dieser Listen war neben der Normierung der Schreibweisen
auch die Integration zahlreicher Vornamen anderer Sprachen. Aufgenommen wurden jeweils
einmalige Varianten oder Schreibweisen, während Dubletten ausgeschlossen wurden. Insgesamt
verteilt sich die Herkunft der Quellen im dublettenbereinigten Datensatz wie folgt:
Quelle
Anzahl
Prozent
Adressbücher des Vereins für Computergenealogie,
1630-1965
175.158
86,7 %
Datensammlung des Historischen Datenzentrums
Sachsen-Anhalt
8.828
4,4 %
FactGrid
7.773
3,8 %
Wikipedia Vornamenslisten
10.213
5,1 %
Gesamt
201.972
100,0 %
Tab. 1: Übersicht zu den Quellen
Nach einer Separierung der Einträge in ihre entitätsgebundenen Bestandteile wurden die Vornamen
nach Vornamenstelle getrennt in einer CSV erfasst, wobei vorzugsweise Namen an erster Stelle
aufgenommen wurden. Weitere Vornamenstellen sind v. a. für die Klärung uneindeutiger Vornamen
von Relevanz und sorgen für ein sichereres Ergebnis. Die Einträge verfügen über eine Quellenangabe,
die bei jedem Objekt nachvollziehbar bleibt, sowie über eine ID und eine Ortskennung.
Die Bereinigung und die weitere Bearbeitung der Daten erfolgte mit OpenRefine und SPSS. Hier
wurden die Namen mit einer Normschreibung versehen und Varianten als Schreibvarianten oder
Fehlschreibungen gekennzeichnet. Eine erste Zuordnung des Geschlechts war bereits während der
händischen Erfassung im Zuge der Transkription erfolgt. Diese Zuordnungen wurden im nächsten
Schritt überprüft und erweitert. Dabei wurden Abstufungen auf zwei Ebenen vorgenommen: zum


einen bei der Benennung des Geschlechts in männlich, weiblich, vorwiegend männlich, vorwiegend
weiblich, vorwiegend männlich/weiblich nur bei deutschsprachigen Varianten, unsicher (worunter
auch Unisex-Vornamen gefasst werden) und nicht bestimmbar. Zudem wurde ein aus
Einzelfallabwägungen heraus selbst entwickelter dreistufiger Sicherheitsgrad dieser Einteilung
angegeben. Das genaue Vorgehen dabei wurde dokumentiert und in einen methodisch-sprachlichen
Prozess überführt. Die Festlegung einer Normbezeichnung sowie die Zuordnung des wahrscheinlichen
Geschlechts erfolgten anhand von Fachliteratur, Wikipedia, Vornamen-Lexika und freien,
webbasierten Namenssammlungen.
Hier wurde mit 202.000 Varianten ein breites wie umfangreiches Sample zugrunde gelegt, das
dennoch keinen Anspruch auf Vollständigkeit erhebt und nie die Gesamtheit existierender Vornamen
im deutschsprachigen Raum abbilden kann. Das Tool ist in der Folge für weiteres Wachstum offen.
Beschreibung des Normierungsstands
Die in der Tabelle dokumentierte Normierung stellt keinen abgeschlossenen Endzustand dar. Es
handelt sich um einen vorläufigen Arbeits- und Zwischenstand der Normierungsarbeit.
Insgesamt umfasst das Vokabular 201.972 Namensformen. Von diesen wurden bislang 179.750
Einträge einer vorläufigen Normschreibung zugeordnet. Die verbleibenden Namensformen verfügen
derzeit noch über keine Normschreibungszuweisung und befinden sich in Bearbeitung.
Der aktuelle Bearbeitungsstand umfasst etwa 17.800 vorläufige Normschreibungen, auf die sich die
bereits zugeordneten Namensformen verteilen. Diese Normschreibungen sind als Arbeitsformen zu
verstehen und werden in einer geplanten zweiten Version des Vokabulars weiter konsolidiert und
noch stärker verallgemeinert. Ziel dieser Folgeversion ist insbesondere eine stärkere Regelbindung,
eine
verbesserte Konsistenz
der
Normierungsentscheidungen
sowie gegebenenfalls
die
Zusammenführung oder Trennung einzelner Normgruppen.
Auch die Zuordnung von Namensformen zu der Kategorie „kein Vorname“ ist im vorliegenden
Datenstand nicht abschließend geprüft. Diese Klassifikation wurde vorgenommen, um den Umfang
des Materials zunächst strukturierbar zu machen. In der geplanten Folgeverson ist eine präzise
Überprüfung und Korrektur dieser Einordnungen vorgesehen.


Die Spalte Normschreibung_alternativ_01 wird in Fällen genutzt, in denen eine Namensform
mehrdeutig ist und sich nicht eindeutig einer einzelnen Normschreibung zuordnen lässt. Dies betrifft
insbesondere Abkürzungen, bei denen mehrere vollständige Namensformen plausibel sind (z. B.
Herm. → Hermann / Hermine).
Der vorliegende Normierungsstand stellt somit eine Arbeitsgrundlage dar, die sowohl die aktuelle
Geschlechtszuweisung historischer Namensformen ermöglicht als auch die Weiterentwicklung des
Vokabulars in zukünftigen Versionen vorbereitet.
Zugänglichkeit in Radar und FactGrid
Das Historische Datenzentrum Sachsen-Anhalt nutzt FactGrid zur Publikation von Vokabularen und
Daten. Daher wurden alle Normschreibungen von Vornamen mit ihren Vorzugs- und
Alternativschreibungen in die Wikibase-Instanz integriert worden. Dort können Sie über persistente
Q-Nummern für Linked Open Data genutzt werden bzw. wird ein kompletter Download der Daten und
ihre Visualisierung möglich. Die Normschreibungen der Vornamen werden laufend in FactGrid ergänzt.
Nicht enthalten sind in FactGrid die Abkürzungen und Fehlschreibungen zu diesen normierten
Vornamen. Diese können als Arbeitsmittel und Matchingwerkzeug in Form eines
vollständigen
Datensatzes
unter
der
DOI
10.22000/pwbupf0jc2zj4k7x
in
der
Langzeitarchivierung des NFDI Konsortiums Radar4Memory als SPSS-Datensatz und CSV
heruntergeladen werden.
5. Aufbau des Tools
Das Tool beinhaltet ein kontrolliertes Vokabular, zur Erfassung und Analyse historischer Formen von
Vornamen. Unter Namensformen werden alle in den Quellen belegten Originalschreibungen
verstanden, einschließlich Schreib- und Sprachvarianten, Abkürzungen sowie Begriffe, die sich
im Zuge der Bearbeitung als keine Vornamen erweisen.


Übersicht und Beschreibung der Variablen des Datensatzes
Variable
Positio
n
Beschriftung
ID
1
ID des Gesamtsystems, HistData2026
Originalquelle_Eintrag_
ID_extern
2
Kennung des entsprechenden Eintrags in der externen
Ursprungsquelle.
Jahr
3
Jahr des ausgewählten Quellenbelegs (nicht Zeitspanne
aller Nennungen)
Quelle
4
Bezeichnung der Quelle, aus der die Namensform
stammt.
Ortskennung
5
GOV-Kennung des mit dem ausgewählten Namensbeleg
verbundenen Ortes (nicht alle Ortsbelege des Namens)
Originalschreibung
6
Originalbezeichnung des Vornamens in der Quelle
(Rohdaten)
Namensstelle
7
Position oder Kontextstelle des Namens innerhalb der
Quelle numerisch.
Klassifizierte_Original-
schreibung
8
Technisch bereinigte Fassung des ausgewählten
Einzelnamens in Originalschreibung
Sicherheit_Namens-
zuordnung
9
Bewertung der Sicherheit, mit der die Originalschreibung
einer vorläufigen Normschreibung zugeordnet wurde
Namensgeschlecht
10
Zugewiesenes wahrscheinliches Geschlecht der
Namensform; bezieht sich primär auf die
Originalschreibung
Sicherheit_Geschlechts-
zuordnung
11
Bewertung der Verlässlichkeit der Geschlechtszuweisung
in drei Graden
Normschreibung_bevor-
zugt_01
12
Interne Kennung der bevorzugten vorläufigen
Normschreibung (hohe Granularität)
Normschreibung_bevor-
zugt_01_ID
13
Interne Kennung der bevorzugten vorläufigen
Normschreibung.
Normschreibung_alter-
nativ_01
14
Interne Kennung der alternativen vorläufigen
Normschreibung.
Normschreibung_alter-
nativ_01_ID
15
Alternative vorläufige Normschreibung bei mehrdeutigen
Namensformen (Abkürzungen) (hohe Granularität)
Abkürzungsstatus
16
Kennzeichnet, ob es sich um eine ausgeschriebene Form
oder eine Abkürzung handelt

Variantentyp
17
Klassifikation der Abweichung von einer Sprachvariante
wie Fehlschreibungen, gebeugte Formen, latinisierte
Formen etc.
Herkunftssprache
18
Sprachliche Herkunft der Namensform
Abweichende_Namens-
kategorie
19
Kategorie, wenn die Namensform vorläufig nicht als
Vorname eingeordnet wurde (z. B. Nachname, Beruf,
Ort).
Originalschreibung_ID_
2023
20
ID aus der Fassung 2023
FactGrid
21
Q-Nummern der bevorzugten Normschreibung (ID) in
FactGrid
Tab. 2: Übersicht und Beschreibung der Variablen des Datensatzes
Codebuch zu den Merkmalsausprägungen der Variablen
(SPSS, in der CSV wurden nur die Variablenlabel ausgespielt)
Variablenwerte
Wert
Beschriftung
Quelle
1
Adressbücher Compgen
3
Datensammlungen Historisches Datenzentrum
4
Factgrid
5
Wikipedia Vornamenslisten
Sicherheit_Namenszu-
ordnung
1
sicher
2
mittlere Sicherheit
3
unsicher
8
kein Vorname
9
noch klären
Namensgeschlecht
1
männlich (Q18)
2
weiblich (Q17)
3
uneindeutig (Q369534)
4
mehrere, gemischt
5
männlich, vorwiegend (Q1381598)
6
weiblich, vorwiegend (Q1381599)
7
männlich, vorwiegend (nur deutsche Vornamen)
(Q1381599)
8
weiblich, vorwiegend (nur deutsche Vornamen)
(Q1381598)


9
unsicher
Sicherheit_Geschlechts-
zuordnung
1
sicher
2
mittlere Sicherheit
3
unsicher
Abkürzungsstatus
1
ausgeschrieben
2
abgekürzt
Variantentyp
1
Schreibvariante
2
Fehlschreibung
3
Sprachvariante
4
Kurzform
5
Koseform
6
Beugung
7
Verkleinerung
8
Latinisierung
9
Nebenform
10
Unikat
11
Weiterbildung
12
Romanisierung
21
Schreibvariante mit Fehlschreibung
61
gebeugte Schreibvariante
62
gebeugte Fehlschreibung
Abweichende_Namens-
kategorie
1
Titel/Namenszusatz
10
Geografikum
11
sonstiges
2
Anrede
3
Nachname
4
Firma
5
Beschreibung
6
Beruf
7
Sonstiges
8
Gebäude
9
Familiäre Beziehung/Familienstand
Tab. 3: Codebuch zu den Merkmalsausprägungen der Variablen
