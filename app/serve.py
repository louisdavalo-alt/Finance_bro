"""Point d'entrée : `python -m app.serve` lance l'API de consultation.

Par défaut l'API n'écoute que sur 127.0.0.1 (accessible uniquement depuis cette machine). Pour
l'exposer sur le réseau (`HOST=0.0.0.0`, ou une adresse IP précise), une authentification est
OBLIGATOIRE : définir `API_USERNAME` et `API_PASSWORD` dans `.env` — sinon le lancement est
refusé (le tableau de bord donnerait à quiconque sur le réseau accès aux calculs lourds et aux
appels Yahoo en ton nom). `ALLOW_PUBLIC_WITHOUT_AUTH=true` force le lancement malgré tout, en
connaissance de cause (ex. réseau isolé derrière un reverse proxy qui authentifie déjà).
L'API ne gère pas TLS : pour un accès hors de ta machine, place-la derrière un reverse proxy HTTPS
(Caddy, nginx) — l'authentification Basic transmet le mot de passe encodé, pas chiffré.
"""
import os
import sys

import uvicorn

from .config import load_settings

LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def main() -> int:
    settings = load_settings()
    api = settings.api
    if api.host not in LOOPBACK and not api.auth_enabled and os.environ.get("ALLOW_PUBLIC_WITHOUT_AUTH", "").lower() != "true":
        print(
            f"Refus de démarrer : HOST={api.host} expose l'API au réseau sans authentification.\n"
            "Définis API_USERNAME et API_PASSWORD dans .env (et API_ALLOWED_HOSTS avec le nom/l'IP\n"
            "utilisé(e) dans le navigateur), ou repasse HOST=127.0.0.1.",
            file=sys.stderr,
        )
        return 2
    if api.auth_enabled and len(api.password) < 12:
        print("API_PASSWORD trop court : 12 caractères minimum.", file=sys.stderr)
        return 2
    if api.auth_enabled and api.password.lower() in {api.username.lower(), "password", "motdepasse", "changeme"}:
        print("API_PASSWORD trop faible (égal à l'identifiant ou mot de passe trivial).", file=sys.stderr)
        return 2
    uvicorn.run(
        "app.api:app", host=api.host, port=api.port,
        server_header=False, date_header=False, proxy_headers=False,
        # Bornes contre l'épuisement de ressources (connexions lentes / rafales) : au-delà de
        # `limit_concurrency` connexions simultanées, uvicorn répond 503 au lieu de s'écrouler.
        limit_concurrency=int(os.environ.get("API_LIMIT_CONCURRENCY", 64)),
        timeout_keep_alive=5,
        h11_max_incomplete_event_size=16 * 1024,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
