const EXTENSION_ICON_KINDS = new Map([
  ['sav', 'binary'],
  ['bak', 'backup'],
  ['json', 'json'],
  ['md', 'markdown'],
  ['markdown', 'markdown'],
  ['txt', 'text'],
  ['log', 'text'],
  ['csv', 'text'],
  ['ini', 'config'],
  ['cfg', 'config'],
  ['conf', 'config'],
  ['config', 'config'],
  ['index', 'config'],
  ['toml', 'config'],
  ['xml', 'config'],
  ['yaml', 'config'],
  ['yml', 'config'],
  ['zip', 'archive'],
  ['7z', 'archive'],
  ['rar', 'archive'],
  ['tar', 'archive'],
  ['gz', 'archive'],
  ['png', 'image'],
  ['jpg', 'image'],
  ['jpeg', 'image'],
  ['gif', 'image'],
  ['webp', 'image'],
  ['bmp', 'image'],
  ['svg', 'image'],
  ['ico', 'image'],
  ['mp3', 'audio'],
  ['wav', 'audio'],
  ['ogg', 'audio'],
  ['flac', 'audio'],
  ['m4a', 'audio'],
  ['mp4', 'video'],
  ['mkv', 'video'],
  ['avi', 'video'],
  ['mov', 'video'],
  ['webm', 'video'],
])

export function getPathEntryIconKind(entry) {
  if (entry?.isRoot) return 'drive'
  if (entry?.isDir) return 'folder'

  const filename = String(entry?.filename || '').toLocaleLowerCase()
  if (/^container\.\d+$/.test(filename)) return 'binary'

  const extensionSeparator = filename.lastIndexOf('.')
  if (extensionSeparator < 0 || extensionSeparator === filename.length - 1) {
    return 'file'
  }

  return EXTENSION_ICON_KINDS.get(filename.slice(extensionSeparator + 1)) || 'file'
}
