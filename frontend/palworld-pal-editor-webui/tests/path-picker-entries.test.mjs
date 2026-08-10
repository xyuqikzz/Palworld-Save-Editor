import assert from 'node:assert/strict'
import test from 'node:test'

import { filterAndSortPathEntries } from '../src/components/modules/path-picker-entries.js'
import { getPathEntryIconKind } from '../src/components/modules/path-entry-icon.js'


test('path picker sorts recent directories first and keeps files after directories', () => {
  const entries = new Map([
    ['/older', { filename: 'WORLD_2', isDir: true, modifiedAt: '2026-01-01T00:00:00Z' }],
    ['/file', { filename: 'Level.sav', isDir: false, modifiedAt: '2026-12-01T00:00:00Z' }],
    ['/newer', { filename: 'WORLD_10', isDir: true, modifiedAt: '2026-08-01T00:00:00Z' }],
  ])

  const sorted = filterAndSortPathEntries(entries.entries(), {
    sortMode: 'modified-desc',
    locale: 'en',
  })

  assert.deepEqual(sorted.map(([path]) => path), ['/newer', '/older', '/file'])
})


test('path picker name sorting is natural and filtering is case insensitive', () => {
  const entries = new Map([
    ['/10', { filename: 'World 10', isDir: true, modifiedAt: null }],
    ['/2', { filename: 'World 2', isDir: true, modifiedAt: null }],
    ['/other', { filename: 'Backup', isDir: true, modifiedAt: null }],
  ])

  const sorted = filterAndSortPathEntries(entries.entries(), {
    query: 'WORLD',
    sortMode: 'name-asc',
    locale: 'en',
  })

  assert.deepEqual(sorted.map(([path]) => path), ['/2', '/10'])
})


test('path picker assigns offline file type icons to save and WGS entries', () => {
  assert.equal(getPathEntryIconKind({ filename: 'C:\\', isDir: true, isRoot: true }), 'drive')
  assert.equal(getPathEntryIconKind({ filename: 'Players', isDir: true }), 'folder')
  assert.equal(getPathEntryIconKind({ filename: 'Level.sav', isDir: false }), 'binary')
  assert.equal(getPathEntryIconKind({ filename: 'containers.index', isDir: false }), 'config')
  assert.equal(getPathEntryIconKind({ filename: 'container.12', isDir: false }), 'binary')
  assert.equal(getPathEntryIconKind({ filename: 'notes.txt', isDir: false }), 'text')
  assert.equal(getPathEntryIconKind({ filename: 'unknown.dat', isDir: false }), 'file')
})
