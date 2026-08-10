function entryTimestamp(entry) {
  const timestamp = Date.parse(entry.modifiedAt || '')
  return Number.isFinite(timestamp) ? timestamp : Number.NEGATIVE_INFINITY
}

export function filterAndSortPathEntries(entries, {
  query = '',
  sortMode = 'modified-desc',
  locale,
} = {}) {
  const normalizedQuery = query.trim().toLocaleLowerCase()
  const filtered = Array.from(entries).filter(([, entry]) => (
    !normalizedQuery
    || entry.filename.toLocaleLowerCase().includes(normalizedQuery)
  ))

  return filtered.sort((left, right) => {
    const leftEntry = left[1]
    const rightEntry = right[1]

    if (leftEntry.isDir !== rightEntry.isDir) {
      return leftEntry.isDir ? -1 : 1
    }

    if (sortMode === 'modified-desc') {
      const timestampDifference = entryTimestamp(rightEntry) - entryTimestamp(leftEntry)
      if (timestampDifference) return timestampDifference
    }

    return leftEntry.filename.localeCompare(rightEntry.filename, locale, {
      numeric: true,
      sensitivity: 'base',
    })
  })
}
