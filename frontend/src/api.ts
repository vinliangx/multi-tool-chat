import { keycloak } from "./keycloak";

export async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  await keycloak.updateToken(10);
  return fetch(path, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      Authorization: `Bearer ${keycloak.token}`,
    },
  });
}
