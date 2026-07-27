<script setup>
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api'
import { jsonDefaults } from 'monaco-editor/esm/vs/language/json/monaco.contribution'
import 'monaco-editor/min/vs/editor/editor.main.css'
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker.js?worker'
import JsonWorker from 'monaco-editor/esm/vs/language/json/json.worker.js?worker'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  readOnly: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'cursor'])
const host = ref(null)
let editor = null
let model = null
let changeDisposable = null
let cursorDisposable = null
let syncing = false

globalThis.MonacoEnvironment = {
  getWorker(_moduleId, label) {
    return label === 'json' ? new JsonWorker() : new EditorWorker()
  },
}

jsonDefaults.setDiagnosticsOptions({
  validate: true,
  allowComments: false,
  schemas: [],
  enableSchemaRequest: false,
  trailingCommas: 'error',
})

monaco.editor.defineTheme('palworld-json-dark', {
  base: 'vs-dark',
  inherit: true,
  rules: [
    { token: 'string.key.json', foreground: '8CBCFF' },
    { token: 'string.value.json', foreground: '9BD5AD' },
    { token: 'number.json', foreground: 'D7A8FF' },
    { token: 'keyword.json', foreground: 'FFB27A' },
    { token: 'delimiter.json', foreground: '8F9BAD' },
  ],
  colors: {
    'editor.background': '#171D25',
    'editor.foreground': '#E7EBF1',
    'editorLineNumber.foreground': '#697587',
    'editorLineNumber.activeForeground': '#A9B5C5',
    'editorCursor.foreground': '#72AEF7',
    'editor.selectionBackground': '#26476C',
    'editor.lineHighlightBackground': '#202A36',
    'editorGutter.background': '#141A21',
    'editorIndentGuide.background1': '#303B49',
    'editorIndentGuide.activeBackground1': '#536173',
    'editorWidget.background': '#202833',
    'editorWidget.border': '#3B4859',
    'editorSuggestWidget.background': '#202833',
    'editorSuggestWidget.border': '#3B4859',
    'minimap.background': '#141A21',
    'scrollbarSlider.background': '#52617455',
    'scrollbarSlider.hoverBackground': '#65758A77',
  },
})

onMounted(() => {
  model = monaco.editor.createModel(
    props.modelValue,
    'json',
    monaco.Uri.parse(`inmemory://palworld-json/${crypto.randomUUID()}.json`),
  )
  editor = monaco.editor.create(host.value, {
    model,
    theme: 'palworld-json-dark',
    automaticLayout: true,
    readOnly: props.readOnly,
    fontFamily: "'Cascadia Code', 'SFMono-Regular', Consolas, monospace",
    fontSize: 13,
    lineHeight: 22,
    tabSize: 2,
    insertSpaces: true,
    formatOnPaste: false,
    formatOnType: false,
    minimap: { enabled: true, showSlider: 'mouseover', scale: 1 },
    folding: true,
    smoothScrolling: true,
    scrollBeyondLastLine: false,
    renderWhitespace: 'selection',
    bracketPairColorization: { enabled: true },
    guides: { bracketPairs: true, indentation: true },
    padding: { top: 14, bottom: 48 },
  })
  changeDisposable = model.onDidChangeContent(() => {
    if (!syncing) emit('update:modelValue', model.getValue())
  })
  cursorDisposable = editor.onDidChangeCursorPosition(event => {
    emit('cursor', {
      line: event.position.lineNumber,
      column: event.position.column,
    })
  })
  emit('cursor', { line: 1, column: 1 })
})

watch(() => props.modelValue, value => {
  if (!model || value === model.getValue()) return
  syncing = true
  model.setValue(value)
  syncing = false
})

watch(() => props.readOnly, value => editor?.updateOptions({ readOnly: value }))

onBeforeUnmount(() => {
  changeDisposable?.dispose()
  cursorDisposable?.dispose()
  editor?.dispose()
  model?.dispose()
})
</script>

<template>
  <div ref="host" class="monaco-host" />
</template>

<style scoped>
.monaco-host {
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
</style>
