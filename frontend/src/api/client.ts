// Client HTTP typé pour l'API FastAPI de finance-bro, à partir des types générés depuis
// `/openapi.json` (voir schema.d.ts, et `npm run gen:api` pour les régénérer).
//
// En dev, Vite proxifie `/api/*` vers le serveur FastAPI (voir vite.config.ts) : pas de CORS à
// gérer, et la même base URL fonctionne en build de prod si le frontend est servi par FastAPI
// lui-même (voir README du frontend).
import createClient from "openapi-fetch";

import type { paths } from "./schema";

export const api = createClient<paths>({ baseUrl: "/api" });

/** Lève une erreur lisible à partir d'une réponse openapi-fetch en échec (son `error` est le
 * corps JSON d'erreur FastAPI, typiquement `{ detail: string }`). */
export function apiErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "detail" in error) {
    const detail = (error as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return "Erreur inattendue de l'API.";
}
