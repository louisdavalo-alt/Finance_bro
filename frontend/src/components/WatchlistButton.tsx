import { useWatchlist } from '../hooks/useWatchlist'

/** Bouton d'ajout/retrait d'une action dans la liste de suivi personnelle — bascule son état
 * selon que `code` y figure déjà ou non. À placer là où une action est sélectionnée pour
 * consultation (fiche de cotation, prévision, graphiques avancés…). */
export function WatchlistButton({ code, className = '' }: { code: string; className?: string }) {
  const { isWatched, toggle } = useWatchlist()
  const watched = isWatched(code)
  return (
    <button
      type="button"
      onClick={() => toggle(code)}
      title={watched ? 'Retirer de ma liste de suivi' : 'Ajouter à ma liste de suivi'}
      className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition-colors ${
        watched
          ? 'border-amber-500/40 bg-amber-500/15 text-amber-300 hover:bg-amber-500/25'
          : 'border-slate-700 text-slate-300 hover:bg-slate-800'
      } ${className}`}
    >
      <span>{watched ? '★' : '☆'}</span>
      {watched ? 'Dans ma liste de suivi' : 'Ajouter à ma liste de suivi'}
    </button>
  )
}

/** Petite étoile cliquable, sans libellé — pour une cellule de tableau (tableau principal). */
export function WatchlistStar({ code, className = '' }: { code: string; className?: string }) {
  const { isWatched, toggle } = useWatchlist()
  const watched = isWatched(code)
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        toggle(code)
      }}
      title={watched ? 'Retirer de ma liste de suivi' : 'Ajouter à ma liste de suivi'}
      className={`text-base leading-none ${watched ? 'text-amber-400' : 'text-slate-600 hover:text-slate-400'} ${className}`}
    >
      {watched ? '★' : '☆'}
    </button>
  )
}
