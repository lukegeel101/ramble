# Dictation glossary

Names, terms and known mishearings for the dictation cleanup.
Copy this file to `glossary.md` in your install folder and replace the examples with your own.
cleanup.py sends the whole file to the cleanup model after the instructions, and dictate.sh gives the transcriber (whisper) the "Transcriber hint" line below so it hears the names right in the first place.
Add a name to the hint line only when whisper keeps mishearing it: the hint holds about 200 tokens and the first names count most.

## Transcriber hint

Sonny, Priya Raman, Grafana, Kubernetes, Postgres, Acme Robotics, Project Lighthouse.

## People

- Sonny: my teammate on the data team; he/him. Heard as "Sunny" or "Sony".
- Priya Raman: product lead. Heard as "Pria" or "Brea".

## Projects and companies

- Acme Robotics: a client. Heard as "act me robotics".
- Project Lighthouse: the migration project. Heard as "project light house".

## Tools and terms

- Grafana: dashboards. Heard as "graph Anna" or "Griffana".
- Kubernetes, k8s: heard as "Cooper Netties".
- Postgres: heard as "post grass".
