#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import xml.etree.ElementTree as ET
import gender_guesser.detector as gender
import os

# Ordner mit XML-Dateien
ordner = "Register/Personen"

# Gender-Detector initialisieren
detector = gender.Detector()

# TEI-Namespace
NS = {"tei": "http://www.tei-c.org/ns/1.0"}
TEI_NS = NS["tei"]
XML_NS = "http://www.w3.org/XML/1998/namespace"

# Namespaces registrieren, damit sie im Output sauber bleiben
ET.register_namespace("", TEI_NS)
ET.register_namespace("xml", XML_NS)

anzahl = 0

def mappe_geschlecht(gg_wert):
    """gender-guesser -> TEI value"""
    if gg_wert in ("male", "mostly_male"):
        return "man"
    elif gg_wert in ("female", "mostly_female"):
        return "woman"
    else:
        return "unknown"

for datei_name in os.listdir(ordner):
    if not datei_name.endswith(".xml"):
        continue

    pfad = os.path.join(ordner, datei_name)
    try:
        tree = ET.parse(pfad)
        wurzel = tree.getroot()
    except ET.ParseError as e:
        print(f"⚠️ Fehler beim Parsen von {datei_name}: {e}")
        continue

    geaendert = False

    # Alle <person>-Elemente im TEI-Namespace finden
    for person in wurzel.findall(".//tei:listPerson/tei:person", NS):
        xml_id = person.get(f"{{{XML_NS}}}id")

        persName = person.find("tei:persName", NS)
        if persName is None:
            continue

        vorname_el = persName.find("tei:forename", NS)
        nachname_el = persName.find("tei:surname", NS)

        vorname = (vorname_el.text or "").strip() if vorname_el is not None else ""
        nachname = (nachname_el.text or "").strip() if nachname_el is not None else ""

        # Nur den ersten Namensteil verwenden
        if vorname:
            vorname = vorname.split()[0]

        # Wenn kein Vorname da, Nachname nutzen
        name_fuer_gender = vorname if vorname else nachname

        if not name_fuer_gender:
            gg = "unknown"
        else:
            gg = detector.get_gender(name_fuer_gender)

        tei_value = mappe_geschlecht(gg)

        # Prüfen, ob bereits ein gender-Element vorhanden ist
        vorhandenes_gender = person.find("tei:gender", NS)

        if vorhandenes_gender is not None:
            # Falls es bereits da ist, aktualisieren wir die Attribute
            vorhandenes_gender.set("value", tei_value)
            vorhandenes_gender.set("evidence", "assigned")
        else:
            # Neues <gender>-Element nach <persName> einfügen
            gender_tag = f"{{{TEI_NS}}}gender"
            new_gender = ET.Element(gender_tag)
            new_gender.set("value", tei_value)
            new_gender.set("evidence", "assigned")

            # Position: direkt nach persName
            persName_index = list(person).index(persName)
            person.insert(persName_index + 1, new_gender)

        geaendert = True
        anzahl += 1

    # Datei nur speichern, wenn geändert
    if geaendert:
        try:
            tree.write(pfad, encoding="utf-8", xml_declaration=True)
            print(f"✓ '{datei_name}' aktualisiert.")
        except Exception as e:
            print(f"⚠️ Fehler beim Schreiben von {datei_name}: {e}")

print(f"✅ Fertig. {anzahl} Personen verarbeitet.")
