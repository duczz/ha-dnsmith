<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Eigener HTTP-Provider

Frei konfigurierbarer HTTP-Aufruf für Anbieter, die noch nicht unterstützt werden. Methode, Authentifizierung, Parameternamen und Erfolgskriterium sind frei wählbar.

Einordnung: generisch

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| Wildcard-Einträge | nein |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |
| mehrere Einträge je Domain | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `url` | Update-URL | URL | erforderlich | Muss HTTPS sein. Interne und private Adressen werden abgelehnt — DNSmith ruft diese URL selbst auf und darf dabei nicht als Sprungbrett ins Heimnetz dienen. Beispiel: `https://example.com/update`. |
| `method` | HTTP-Methode | Auswahl | optional | Vorgabe: `GET`. |
| `auth_mode` | Authentifizierung | Auswahl | optional | Vorgabe: `none`. |
| `auth_username` | Benutzername | Text | optional (nur bei auth_mode = basic) | — |
| `auth_password` | Passwort | Zugangsdaten | optional (nur bei auth_mode = basic) | Das Passwort für HTTP-Basic-Auth, wie es die Doku deines Anbieters für den Update-Aufruf nennt. Bei vielen Diensten ist das ein eigenes Update-Passwort und nicht das Konto-Passwort. |
| `auth_token` | Token | Zugangsdaten | optional (nur bei auth_mode = bearer) | Wird als "Authorization: Bearer <Wert>" gesendet. Nur den Token selbst eintragen, ohne das Wort Bearer davor. |
| `auth_query_name` | Name des Query-Parameters | Text | optional (nur bei auth_mode = query) | Beispiel: `apikey`. |
| `auth_query_value` | Wert des Query-Parameters | Zugangsdaten | optional (nur bei auth_mode = query) | Der Wert, der als Query-Parameter angehängt wird. Achtung: Query-Parameter landen bei manchen Anbietern im Server-Protokoll — wenn der Anbieter auch Basic-Auth oder Bearer anbietet, ist das der sicherere Weg. |
| `ipv4_parameter` | Parametername für IPv4 | Text | optional | Leer lassen, wenn der Anbieter die IP aus der Verbindung selbst ermittelt. Vorgabe: `myip`. |
| `ipv6_parameter` | Parametername für IPv6 | Text | optional | Vorgabe: `myipv6`. |
| `hostname_parameter` | Parametername für den Hostnamen | Text | optional | Vorgabe: `hostname`. |
| `success_mode` | Erfolg erkennen an | Auswahl | optional | Vorgabe: `status`. |
| `success_regex` | Erfolgsmuster | Text | optional (nur bei success_mode = regex) | Regulärer Ausdruck. "good|nochg" passt auf die meisten DynDNS-artigen Antworten. Beispiel: `good|nochg`. |

## Hinweise

> Der eigene HTTP-Provider ist die letzte Option. Wenn er für einen Anbieter funktioniert, lohnt sich ein Hinweis im Projekt — daraus wird ein richtiger Provider mit eigenem Formular.

---

Stand: 16.09.2026.
