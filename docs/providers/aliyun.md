<!-- Erzeugt von tools/gen_docs.py. Nicht von Hand bearbeiten. -->

# Aliyun

Chinesischer Cloud-Anbieter. DNS-Einträge werden über die Alibaba-Cloud-API geändert.

Website: <https://www.aliyun.com>

Einordnung: Cloud-DNS

## Was der Anbieter kann

| | |
|---|---|
| IP-Versionen | IPv4 und IPv6 |
| IPv6-Suffix | ja |
| TTL einstellbar | nein |
| Proxy-Schalter | nein |

## Felder

| Feld | Beschriftung | Typ | Nötig | Bedeutung |
|---|---|---|---|---|
| `access_key_id` | AccessKey ID | Text | erforderlich | Der öffentliche Teil eines AccessKey-Paares. In der RAM-Konsole unter Identities → Users → Benutzer → Credentials → Create AccessKey anlegen. Nimm einen RAM-Benutzer, nicht das Hauptkonto. |
| `access_secret` | AccessKey Secret | Zugangsdaten | erforderlich | Der geheime Teil desselben Paares, nicht dein Konto-Passwort. Wird nur einmal direkt nach dem Anlegen angezeigt. |
| `region` | Region | Text | optional | Leer lassen verwendet cn-hangzhou. Nur ändern, wenn die Zone woanders liegt. Beispiel: `cn-hangzhou`. |

---

Stand: 16.09.2026.
