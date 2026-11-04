import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'finance-bro:watchlist'
const EVENT = 'finance-bro:watchlist-changed'

function readList(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as string[]) : []
  } catch {
    return []
  }
}

function writeList(list: string[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
  } catch {
    // stockage indisponible (navigation privée, quota dépassé…) : la mise à jour reste en
    // mémoire pour cette session via l'événement ci-dessous, sans persister — pas bloquant.
  }
  window.dispatchEvent(new Event(EVENT))
}

/** Liste de suivi personnelle des actions à surveiller — stockée dans CE navigateur
 * (localStorage), pas de compte ni de synchronisation entre appareils pour l'instant : c'est un
 * outil personnel. `writeList` émet un événement maison (en plus de `storage`, qui ne se
 * déclenche jamais dans l'onglet qui a fait l'écriture) pour que tous les composants montés —
 * tableau principal compris — restent à jour immédiatement, y compris entre onglets. */
export function useWatchlist() {
  const [list, setList] = useState<string[]>(() => readList())

  useEffect(() => {
    const onChange = () => setList(readList())
    window.addEventListener(EVENT, onChange)
    window.addEventListener('storage', onChange)
    return () => {
      window.removeEventListener(EVENT, onChange)
      window.removeEventListener('storage', onChange)
    }
  }, [])

  const isWatched = useCallback((code: string) => list.includes(code), [list])

  const add = useCallback((code: string) => {
    const current = readList()
    if (!current.includes(code)) writeList([...current, code])
  }, [])

  const remove = useCallback((code: string) => {
    writeList(readList().filter((c) => c !== code))
  }, [])

  const toggle = useCallback((code: string) => {
    const current = readList()
    writeList(current.includes(code) ? current.filter((c) => c !== code) : [...current, code])
  }, [])

  return { list, isWatched, add, remove, toggle }
}
