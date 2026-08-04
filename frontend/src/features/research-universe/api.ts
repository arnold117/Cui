const BASE = "/api/v2"

async function read<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`)
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || `${response.status} ${response.statusText}`)
  }
  return response.json()
}

export interface ActiveUniverse {
  id: string
  created_at?: string
}

export const researchUniverse = {
  active: () => read<ActiveUniverse>("/universes/active"),
}
