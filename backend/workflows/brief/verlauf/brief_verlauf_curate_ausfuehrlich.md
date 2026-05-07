---
id: brief-verlauf-curate-ausfuehrlich
version: 2026-05-07
model: gemini-3-flash-preview
role: user
inputs: []
---
== FORMAT: AUSFUEHRLICH ==

Du schreibst einen ausführlichen Verlaufsbericht für einen substanzreichen Aufenthalt mit Komplikationen, mehreren Therapieänderungen oder relevanter klinischer Komplexität. Der Patient lag länger auf der Intensivstation. Die Übernehmenden brauchen ein vollständiges Bild des Verlaufs, um Kontext und offene Punkte zu verstehen.

TEXTLÄNGE: Bis zu ~25 Sätze, je nach Substanz. Kein hartes Minimum. Kürzer als die Substanz es erfordert ist besser als aufgeblasen. Cluster-Brücken und narrative Übergänge sind erlaubt und erwünscht (bei ausführlicher Substanz ist KOHÄSION c) vollständig aktiv).

STRUKTUR: 3 oder mehr Absätze, nach Themenclustern oder grob chronologisch. Erster Absatz: Übernahme-Situation. Letzter Absatz: Schluss-Pattern. Dazwischen: thematische Cluster-Absätze in klinischer Wucht-Reihenfolge.

STIL-ANKER — Ausführlich-Beispiele (mittlerer/ausführlicher Verlauf):

> "Postoperativ entwickelte sich ein vasoplegisches Schockgeschehen, weshalb die Katecholamintherapie um Vasopressin und Hydrocortison erweitert und als Rescue-Maßnahme einmalig Methylenblau verabreicht wurde."

> "Aufgrund rezidivierender Sekretverlegungen und einer prolongierten Aspirationsneigung gestaltete sich das pulmonale Weaning schwierig, sodass am 20.04. nach Aufklärung des Sohnes die chirurgische Tracheotomie erfolgte."

> "Hämodynamisch zeigte sich darunter eine zunehmende Stabilisierung; in den Reduktionsechos vom 24.04. ließ sich die Impella-Unterstützung schrittweise von P5 auf P2 deeskalieren bei stabiler LV-Funktion."

Was diese Sätze ausmacht: kausale Verkettung, hierarchische Verdichtung mehrerer Fakten in einen Satz, Partizipialkonstruktionen, Vermeidung von Aufzählungen.

== OUTPUT ==

Schreibe jetzt den finalen Verlaufs-Fließtext. Markdown erlaubt für Absatzgliederung (Leerzeile zwischen Cluster-Absätzen). Kein [PENDING]-Marker im Output. Keine Überschriften, keine Bullet-Listen, keine Tabellen — reiner Fließtext.
