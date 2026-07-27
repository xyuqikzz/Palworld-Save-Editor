self.onmessage = event => {
  const { id, action, text } = event.data
  try {
    const value = JSON.parse(text)
    self.postMessage({
      id,
      action,
      valid: true,
      text: action === 'format' ? `${JSON.stringify(value, null, 2)}\n` : undefined,
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    const positionMatch = message.match(/position\s+(\d+)/i)
    const position = positionMatch ? Number(positionMatch[1]) : null
    let line = null
    let column = null
    if (Number.isInteger(position)) {
      const prefix = text.slice(0, position)
      line = prefix.split('\n').length
      column = position - prefix.lastIndexOf('\n')
    }
    self.postMessage({
      id,
      action,
      valid: false,
      message,
      position,
      line,
      column,
    })
  }
}
