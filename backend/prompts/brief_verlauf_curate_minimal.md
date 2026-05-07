---
id: brief-verlauf-curate-minimal
version: 2026-05-07
model: gemini-3-flash-preview
role: user
inputs: []
---
== FORMAT: MINIMAL ==

Du schreibst einen sehr kurzen Verlaufsbericht für einen kurzen, unkomplizierten Aufenthalt. Der Patient lag wenige Tage auf der Intensivstation, der Verlauf war im Wesentlichen routinemäßig. Die Übernehmenden brauchen nur die wichtigsten Eckpunkte und offene Punkte.

TEXTLÄNGE: MAXIMAL 4 Sätze. Kein Minimum. Wenn 3 Sätze das Geschehen vollständig beschreiben, sind 3 Sätze das richtige Ergebnis. Der Schluss-Satz bei LEBEND_VERLEGUNG (2 Sätze) und bei KEINE_DOKUMENTATION (1 Satz) zählt zu den MAXIMAL 4 Sätzen.

REDUKTIONS-MANDAT: Du darfst und SOLLST Cluster-Inhalte aktiv weglassen, kürzen und zusammenfassen. Wenn ein Cluster keinen berichtspflichtigen Inhalt hat (kein [PENDING], keine Komplikation, keine Therapieänderung mit Konsequenz), wird er nicht erwähnt — auch nicht andeutungsweise. Routine-Postop-Cluster wie unkompliziertes Weaning, regelrechte Drainagen, O2-Vorlage ohne Eskalation oder Wiederaufnahme der kardialen Dauermedikation werden vollständig gestrichen.

STRUKTUR: Ein einziger Absatz. Keine Absatz-Trennung zwischen Clustern. Alle relevanten Informationen werden in 2-3 klinisch verdichteten Sätzen integriert, bevor der Schluss folgt.

STIL-ANKER — Minimal-Beispiel (4 Sätze, ~24h ITS, unkomplizierter postoperativer Verlauf mit Therapieauftrag):

> "Frau S. wurde am 25.04. nach elektiver ACVB-OP (LIMA-RIVA, A. radialis-RPLS) bei koronarer 3-Gefäßerkrankung mit Hauptstammbeteiligung postoperativ übernommen. Der Verlauf gestaltete sich komplikationslos; die DAPT nach vorangegangenem STEMI (03/2026) wurde am ersten postoperativen Tag etabliert und ist fortzuführen. Der Drain-Zug steht noch aus. Wir verlegen Frau S. in stabilem Zustand auf die Normalstation und danken für die unkomplizierte Übernahme. Für Rückfragen stehen wir jederzeit zur Verfügung."

Was diesen Verlauf ausmacht: Übernahme-Satz, ein kondensierter Inhaltssatz für alle relevanten Therapie-Aufträge, ein Pending-Item-Satz, Schluss. Keine Extubationszeit, keine Noradrenalin-Dosierung, keine Drainagen-Förderung — nur Konsequenz-relevantes.

== OUTPUT ==

Schreibe jetzt den Verlaufs-Fließtext als einen einzigen Absatz. Maximal 4 Sätze. Der Marker [PENDING] darf nicht im Output erscheinen. Keine Überschriften, keine Listen, keine Absatz-Trennungen.
