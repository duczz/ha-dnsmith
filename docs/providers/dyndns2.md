<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Generisches DynDNS2

Jeder Dienst, der das klassische DynDNS2-Protokoll spricht — Update-URL mit Basic-Auth und den Antworten good, nochg, badauth, nohost, abuse.

Einordnung: DynDNS2, generisch

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| Wildcard-Einträge | nein |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |
| mehrere Einträge je Domain | ja |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `server` | Update-URL | URL | erforderlich | Die vollständige Update-Adresse des Anbieters, zum Beispiel https://dyndns.example.com/nic/update. Steht in dessen DynDNS-Dokumentation. Beispiel: `https://dyndns.example.com/nic/update`. |
| `username` | Benutzername | Text | erforderlich | — |
| `password` | Passwort oder Update-Token | Zugangsdaten | erforderlich | Was dein Anbieter für den DynDNS2-Aufruf verlangt. Sehr oft ist das nicht das Konto-Passwort, sondern ein eigenes Update-Passwort oder ein Token — steht in der DynDNS-Anleitung des Anbieters. |
| `ipv4_parameter` | Parametername für IPv4 | Text | optional | Fast alle Anbieter verwenden "myip". Nur ändern, wenn die Dokumentation es verlangt. Vorgabe: `myip`. |
| `ipv6_parameter` | Parametername für IPv6 | Text | optional | Häufig "myipv6". Manche Anbieter erwarten stattdessen beide Adressen in "myip". Vorgabe: `myipv6`. |
| `hostname_parameter` | Parametername für den Hostnamen | Text | optional | Vorgabe: `hostname`. |

## Hinweise

> Erst probieren, ob der Anbieter bereits als eigener Provider in der Liste steht — dort sind die Eigenheiten schon berücksichtigt.

---

Stand: 16.09.2026.
