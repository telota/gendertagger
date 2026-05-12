import xml.etree.ElementTree as ET
import gender_guesser.detector as gender
import os
import csv

# Ordner mit XML-Dateien
ordner = "Register/Personen"

# Gender-Detector initialisieren
detector = gender.Detector()

# Ergebnisse speichern
ergebnisse = []

# TEI-Namespace
NS = {"tei": "http://www.tei-c.org/ns/1.0"}

for datei_name in os.listdir(ordner):
    if datei_name.endswith(".xml"):
        pfad = os.path.join(ordner, datei_name)
        baum = ET.parse(pfad)
        wurzel = baum.getroot()
        
        # Alle <person> Elemente unter <listPerson> finden
        for person in wurzel.findall(".//tei:listPerson/tei:person", NS):
            xml_id = person.get("{http://www.w3.org/XML/1998/namespace}id")
            persName = person.find("tei:persName", NS)
            
            if persName is not None:
                vorname_el = persName.find("tei:forename", NS)
                nachname_el = persName.find("tei:surname", NS)
                
                vorname = vorname_el.text.strip() if vorname_el is not None and vorname_el.text else ""
                nachname = nachname_el.text.strip() if nachname_el is not None and nachname_el.text else ""
                
                # Nur den ersten Namensteil verwenden
                if vorname:
                    vorname = vorname.split()[0]
                
                # Wenn Vorname leer ist, nehmen wir Nachname
                name_fuer_gender = vorname if vorname else nachname
                
                geschlecht = detector.get_gender(name_fuer_gender)
                
                ergebnisse.append({
                    "xml_id": xml_id,
                    "name": f"{vorname} {nachname}".strip(),
                    "geschlecht": geschlecht,
                    "datei": datei_name
                })

# Ergebnisse in CSV speichern
csv_datei = "ergebnisse.csv"
feldnamen = ["xml_id", "name", "geschlecht", "datei"]

with open(csv_datei, mode="w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=feldnamen)
    writer.writeheader()
    for eintrag in ergebnisse:
        writer.writerow(eintrag)

print(f"Fertig! {len(ergebnisse)} Einträge wurden in '{csv_datei}' gespeichert.")
