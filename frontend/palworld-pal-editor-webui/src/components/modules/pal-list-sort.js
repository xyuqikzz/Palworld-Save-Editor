export const PAL_LIST_SORT_MODES = Object.freeze({
  CONTAINER: 'container',
  PALDECK: 'paldeck',
  LEVEL: 'level',
})

function palSlotIndex(pal) {
  if (pal?.SlotIndex === null || pal?.SlotIndex === undefined || pal?.SlotIndex === '') {
    return Number.POSITIVE_INFINITY
  }
  const slotIndex = Number(pal.SlotIndex)
  return Number.isFinite(slotIndex) ? slotIndex : Number.POSITIVE_INFINITY
}

function palLevel(pal) {
  const level = Number(pal?.Level)
  return Number.isFinite(level) ? level : 1
}

export function sortPalList(pals, mode = PAL_LIST_SORT_MODES.CONTAINER) {
  const paldeckOrder = Array.from(pals)
  if (mode === PAL_LIST_SORT_MODES.PALDECK) return paldeckOrder

  return paldeckOrder
    .map((pal, index) => ({ pal, index }))
    .sort((left, right) => {
      const difference = mode === PAL_LIST_SORT_MODES.LEVEL
        ? palLevel(right.pal) - palLevel(left.pal)
        : palSlotIndex(left.pal) - palSlotIndex(right.pal)
      return difference || left.index - right.index
    })
    .map(({ pal }) => pal)
}
