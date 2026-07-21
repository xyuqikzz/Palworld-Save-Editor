<script setup>
import { computed, ref, watch } from 'vue'
import { usePalEditorStore } from '@/stores/paleditor'

const palStore = usePalEditorStore()
const searchText = ref('')
const typeFilter = ref('all')
const statusFilter = ref('all')
const sortKey = ref('title')
const sortDirection = ref('asc')
const page = ref(1)
const pageSize = ref(25)
const selectedMissionIds = ref([])
const selectedOperation = ref('mark_completed')
const detailMissionId = ref(null)
const confirmationPreview = ref(null)
const confirmationOperation = ref(null)
const confirmationMissionIds = ref([])

const missions = computed(() => palStore.PLAYER_MISSIONS?.missions || [])
const summary = computed(() => palStore.PLAYER_MISSIONS?.summary || {
    total: 0,
    by_status: { completed: 0, in_progress: 0, unaccepted: 0, inconsistent: 0 },
})
const detailMission = computed(() =>
    missions.value.find(mission => mission.internal_name === detailMissionId.value) || null
)
const bulkOperations = new Set([
    'complete_tracked',
    'complete_all_in_progress',
    'complete_all',
    'reset_all_completed',
])
const operationOptions = [
    'mark_completed',
    'reset_to_unaccepted',
    'restart_from_beginning',
    'complete_tracked',
    'complete_all_in_progress',
    'complete_all',
    'reset_all_completed',
]
const operationTranslationKeys = {
    mark_completed: 'Mission_OperationMarkCompleted',
    reset_to_unaccepted: 'Mission_OperationResetUnaccepted',
    restart_from_beginning: 'Mission_OperationRestart',
    complete_tracked: 'Mission_OperationCompleteTracked',
    complete_all_in_progress: 'Mission_OperationCompleteInProgress',
    complete_all: 'Mission_OperationCompleteAll',
    reset_all_completed: 'Mission_OperationResetCompleted',
}
const statusTranslationKeys = {
    completed: 'Mission_StatusCompleted',
    in_progress: 'Mission_StatusInProgress',
    unaccepted: 'Mission_StatusUnaccepted',
    inconsistent: 'Mission_StatusInconsistent',
}
const typeTranslationKeys = {
    main: 'Mission_TypeMain',
    sub: 'Mission_TypeSub',
    hidden: 'Mission_TypeHidden',
}

const filteredMissions = computed(() => {
    const needle = searchText.value.trim().toLocaleLowerCase()
    const values = missions.value.filter(mission => {
        if (typeFilter.value !== 'all' && mission.type !== typeFilter.value) return false
        if (statusFilter.value !== 'all' && mission.status !== statusFilter.value) return false
        if (!needle) return true
        return [mission.title, mission.internal_name, mission.description]
            .some(value => String(value || '').toLocaleLowerCase().includes(needle))
    })
    return [...values].sort((left, right) => {
        const leftValue = String(left[sortKey.value] ?? '')
        const rightValue = String(right[sortKey.value] ?? '')
        const result = leftValue.localeCompare(rightValue, palStore.I18n || 'en', {
            numeric: true,
            sensitivity: 'base',
        })
        return sortDirection.value === 'asc' ? result : -result
    })
})
const pageCount = computed(() => Math.max(1, Math.ceil(filteredMissions.value.length / pageSize.value)))
const pagedMissions = computed(() => {
    const start = (page.value - 1) * pageSize.value
    return filteredMissions.value.slice(start, start + pageSize.value)
})
const visibleIds = computed(() => pagedMissions.value
    .filter(mission => mission.capabilities.mark_completed)
    .map(mission => mission.internal_name))
const allVisibleSelected = computed(() =>
    visibleIds.value.length > 0
    && visibleIds.value.every(missionId => selectedMissionIds.value.includes(missionId))
)
const someVisibleSelected = computed(() =>
    visibleIds.value.some(missionId => selectedMissionIds.value.includes(missionId))
)
const selectedCount = computed(() => selectedMissionIds.value.length)
const requiresSelection = computed(() => !bulkOperations.has(selectedOperation.value))
const canPreview = computed(() =>
    palStore.PLAYER_MISSIONS?.writable
    && !palStore.MISSION_LOADING
    && (!requiresSelection.value || selectedCount.value > 0)
)

watch([searchText, typeFilter, statusFilter, pageSize], () => { page.value = 1 })
watch(pageCount, value => { if (page.value > value) page.value = value })
watch(
    () => palStore.SELECTED_PLAYER_ID,
    () => {
        searchText.value = ''
        typeFilter.value = 'all'
        statusFilter.value = 'all'
        page.value = 1
        selectedMissionIds.value = []
        detailMissionId.value = null
        confirmationPreview.value = null
    },
)

function translate(key, args = []) {
    return palStore.getTranslatedText(key, args)
}

function statusLabel(status) {
    return translate(statusTranslationKeys[status] || 'Mission_StatusInconsistent')
}

function typeLabel(type) {
    return translate(typeTranslationKeys[type] || 'Mission_TypeHidden')
}

function operationLabel(operation) {
    return translate(operationTranslationKeys[operation])
}

function openDetails(mission) {
    detailMissionId.value = mission.internal_name
}

function toggleMission(missionId) {
    selectedMissionIds.value = selectedMissionIds.value.includes(missionId)
        ? selectedMissionIds.value.filter(value => value !== missionId)
        : [...selectedMissionIds.value, missionId]
}

function toggleVisibleSelection() {
    if (allVisibleSelected.value) {
        const visibleIdSet = new Set(visibleIds.value)
        selectedMissionIds.value = selectedMissionIds.value.filter(value => !visibleIdSet.has(value))
        return
    }
    selectedMissionIds.value = [...new Set([...selectedMissionIds.value, ...visibleIds.value])]
}

function sortBy(key) {
    if (sortKey.value === key) {
        sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
    } else {
        sortKey.value = key
        sortDirection.value = 'asc'
    }
}

async function requestPreview(operation = selectedOperation.value, missionIds = null) {
    const ids = missionIds ?? (bulkOperations.has(operation) ? [] : selectedMissionIds.value)
    const preview = await palStore.previewMissionCommand(operation, ids)
    if (!preview) return
    confirmationOperation.value = operation
    confirmationMissionIds.value = ids
    confirmationPreview.value = preview
}

async function confirmOperation() {
    const preview = confirmationPreview.value
    if (!preview) return
    const succeeded = await palStore.executeMissionCommand(
        confirmationOperation.value,
        confirmationMissionIds.value,
        preview.preview_token,
    )
    if (succeeded) {
        selectedMissionIds.value = []
        confirmationPreview.value = null
    }
}
</script>

<template>
    <section class="mission-editor" :aria-busy="palStore.MISSION_LOADING">
        <header class="mission-heading">
            <p v-if="palStore.PLAYER_MISSIONS?.source">
                {{ translate('Mission_SourceBuild', [palStore.PLAYER_MISSIONS.source.build_id]) }}
            </p>
            <div class="mission-heading-actions">
                <button
                    type="button"
                    class="complete-all-button"
                    :disabled="!palStore.PLAYER_MISSIONS?.writable || palStore.MISSION_LOADING"
                    @click="requestPreview('complete_all', [])"
                >{{ translate('Mission_OperationCompleteAll') }}</button>
                <button type="button" :disabled="palStore.MISSION_LOADING" @click="palStore.loadPlayerMissions()">
                    {{ translate('Mission_Reload') }}
                </button>
            </div>
        </header>

        <div class="mission-warnings" role="note">
            <p>{{ translate('Mission_WarningRewards') }}</p>
            <p>{{ translate('Mission_WarningStoryEffects') }}</p>
            <p>{{ translate('Mission_WarningFollowUp') }}</p>
        </div>

        <div v-if="palStore.LAST_ERROR?.context?.includes('mission')" class="mission-error" role="alert">
            <strong>{{ translate('Mission_Error') }}</strong>
            <span>{{ palStore.LAST_ERROR.code }} · {{ palStore.LAST_ERROR.message }}</span>
            <button type="button" @click="palStore.loadPlayerMissions()">{{ translate('Mission_Retry') }}</button>
        </div>
        <div v-if="!palStore.PLAYER_MISSIONS?.writable" class="mission-readonly" role="status">
            {{ translate('Mission_ReadOnly') }}
        </div>

        <div class="mission-stats" aria-live="polite">
            <span>{{ translate('Mission_StatsTotal') }} <strong>{{ summary.total }}</strong></span>
            <span>{{ translate('Mission_StatusCompleted') }} <strong>{{ summary.by_status.completed }}</strong></span>
            <span>{{ translate('Mission_StatusInProgress') }} <strong>{{ summary.by_status.in_progress }}</strong></span>
            <span>{{ translate('Mission_StatusUnaccepted') }} <strong>{{ summary.by_status.unaccepted }}</strong></span>
            <span class="danger">{{ translate('Mission_StatusInconsistent') }} <strong>{{ summary.by_status.inconsistent }}</strong></span>
        </div>

        <div class="mission-toolbar">
            <input v-model="searchText" type="search" :placeholder="translate('Mission_SearchPlaceholder')">
            <select v-model="typeFilter" :aria-label="translate('Mission_FilterType')">
                <option value="all">{{ translate('Mission_FilterAllTypes') }}</option>
                <option value="main">{{ translate('Mission_TypeMain') }}</option>
                <option value="sub">{{ translate('Mission_TypeSub') }}</option>
                <option value="hidden">{{ translate('Mission_TypeHidden') }}</option>
            </select>
            <select v-model="statusFilter" :aria-label="translate('Mission_FilterStatus')">
                <option value="all">{{ translate('Mission_FilterAllStatuses') }}</option>
                <option value="completed">{{ translate('Mission_StatusCompleted') }}</option>
                <option value="in_progress">{{ translate('Mission_StatusInProgress') }}</option>
                <option value="unaccepted">{{ translate('Mission_StatusUnaccepted') }}</option>
                <option value="inconsistent">{{ translate('Mission_StatusInconsistent') }}</option>
            </select>
            <button type="button" @click="selectedMissionIds = []">{{ translate('Mission_ClearSelection') }}</button>
        </div>

        <div class="mission-actions">
            <span>{{ translate('Mission_SelectedCount', [selectedCount]) }}</span>
            <select v-model="selectedOperation" :aria-label="translate('Mission_BulkAction')">
                <option v-for="operation in operationOptions" :key="operation" :value="operation">
                    {{ operationLabel(operation) }}
                </option>
            </select>
            <button type="button" :disabled="!canPreview" @click="requestPreview()">
                {{ translate('Mission_Preview') }}
            </button>
        </div>

        <div class="mission-table-wrap">
            <table>
                <thead>
                    <tr>
                        <th class="selection-column">
                            <input
                                type="checkbox"
                                :checked="allVisibleSelected"
                                :indeterminate="someVisibleSelected && !allVisibleSelected"
                                :disabled="!visibleIds.length"
                                :aria-label="translate('Mission_SelectVisible')"
                                @change="toggleVisibleSelection"
                            >
                        </th>
                        <th><button type="button" @click="sortBy('title')">{{ translate('Mission_ColumnTitle') }}</button></th>
                        <th><button type="button" @click="sortBy('internal_name')">{{ translate('Mission_ColumnId') }}</button></th>
                        <th><button type="button" @click="sortBy('type')">{{ translate('Mission_ColumnType') }}</button></th>
                        <th><button type="button" @click="sortBy('status')">{{ translate('Mission_ColumnStatus') }}</button></th>
                        <th>{{ translate('Mission_ColumnProgress') }}</th>
                        <th class="actions-column">{{ translate('Mission_ColumnActions') }}</th>
                    </tr>
                </thead>
                <tbody>
                    <tr
                        v-for="mission in pagedMissions"
                        :key="mission.internal_name"
                        :class="{ inconsistent: mission.status === 'inconsistent' }"
                        @click.stop="openDetails(mission)"
                    >
                        <td>
                            <input
                                type="checkbox"
                                :checked="selectedMissionIds.includes(mission.internal_name)"
                                :disabled="!mission.capabilities.mark_completed"
                                :aria-label="translate('Mission_Select')"
                                @click.stop="toggleMission(mission.internal_name)"
                            >
                        </td>
                        <td>
                            <strong>{{ mission.title }}</strong>
                            <small v-if="mission.localization_fallback">{{ translate('Mission_FallbackTitle') }}</small>
                        </td>
                        <td><code>{{ mission.internal_name }}</code></td>
                        <td>{{ typeLabel(mission.type) }}</td>
                        <td><span class="status-badge" :data-status="mission.status">{{ statusLabel(mission.status) }}</span></td>
                        <td>
                            <span v-if="mission.progress">{{ translate('Mission_BlockIndex', [mission.progress.block_index]) }}</span>
                            <span v-else>—</span>
                        </td>
                        <td class="row-actions">
                            <div class="row-actions-inner">
                                <button type="button" @click.stop="openDetails(mission)">{{ translate('Mission_Details') }}</button>
                                <button
                                    v-if="mission.status !== 'completed' && mission.status !== 'inconsistent'"
                                    type="button"
                                    :disabled="!mission.capabilities.mark_completed || palStore.MISSION_LOADING"
                                    @click.stop="requestPreview('mark_completed', [mission.internal_name])"
                                >{{ translate('Mission_OperationMarkCompleted') }}</button>
                                <button
                                    v-if="mission.status !== 'unaccepted' && mission.status !== 'inconsistent'"
                                    type="button"
                                    :disabled="!mission.capabilities.reset_to_unaccepted || palStore.MISSION_LOADING"
                                    @click.stop="requestPreview('reset_to_unaccepted', [mission.internal_name])"
                                >{{ translate('Mission_OperationResetUnaccepted') }}</button>
                                <button
                                    v-if="mission.status !== 'unaccepted' && mission.status !== 'inconsistent'"
                                    type="button"
                                    :disabled="!mission.capabilities.restart_from_beginning || palStore.MISSION_LOADING"
                                    @click.stop="requestPreview('restart_from_beginning', [mission.internal_name])"
                                >{{ translate('Mission_OperationRestart') }}</button>
                            </div>
                        </td>
                    </tr>
                    <tr v-if="!pagedMissions.length">
                        <td colspan="7" class="empty-state">{{ translate('Mission_NoData') }}</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <footer class="mission-pagination">
            <button type="button" :disabled="page <= 1" @click="page--">{{ translate('Mission_Previous') }}</button>
            <span>{{ translate('Mission_Page', [page, pageCount]) }}</span>
            <button type="button" :disabled="page >= pageCount" @click="page++">{{ translate('Mission_Next') }}</button>
            <select v-model.number="pageSize" :aria-label="translate('Mission_PageSize')">
                <option :value="25">25</option>
                <option :value="50">50</option>
                <option :value="100">100</option>
            </select>
        </footer>

        <aside v-if="detailMission" class="mission-drawer" :aria-label="translate('Mission_Details')">
            <header>
                <div><h3>{{ detailMission.title }}</h3><code>{{ detailMission.internal_name }}</code></div>
                <button type="button" @click="detailMissionId = null">{{ translate('Mission_Close') }}</button>
            </header>
            <dl>
                <dt>{{ translate('Mission_ColumnType') }}</dt><dd>{{ typeLabel(detailMission.type) }}</dd>
                <dt>{{ translate('Mission_ColumnStatus') }}</dt><dd>{{ statusLabel(detailMission.status) }}</dd>
                <dt>{{ translate('Mission_Description') }}</dt><dd>{{ detailMission.description || '—' }}</dd>
                <dt>{{ translate('Mission_Objectives') }}</dt>
                <dd><ol><li v-for="objective in detailMission.objectives" :key="objective">{{ objective }}</li></ol></dd>
                <dt>{{ translate('Mission_Progress') }}</dt>
                <dd><pre v-if="detailMission.progress">{{ JSON.stringify(detailMission.progress, null, 2) }}</pre><span v-else>—</span></dd>
            </dl>
            <div class="drawer-actions">
                <button v-if="detailMission.status !== 'completed' && detailMission.status !== 'inconsistent'" type="button" :disabled="!detailMission.capabilities.mark_completed" @click="requestPreview('mark_completed', [detailMission.internal_name])">{{ translate('Mission_OperationMarkCompleted') }}</button>
                <button v-if="detailMission.status !== 'unaccepted' && detailMission.status !== 'inconsistent'" type="button" :disabled="!detailMission.capabilities.reset_to_unaccepted" @click="requestPreview('reset_to_unaccepted', [detailMission.internal_name])">{{ translate('Mission_OperationResetUnaccepted') }}</button>
                <button v-if="detailMission.status !== 'unaccepted' && detailMission.status !== 'inconsistent'" type="button" :disabled="!detailMission.capabilities.restart_from_beginning" @click="requestPreview('restart_from_beginning', [detailMission.internal_name])">{{ translate('Mission_OperationRestart') }}</button>
            </div>
        </aside>

        <div v-if="confirmationPreview" class="mission-modal-backdrop">
            <section class="mission-modal" role="dialog" aria-modal="true" :aria-label="translate('Mission_ConfirmTitle')">
                <h3>{{ translate('Mission_ConfirmTitle') }}</h3>
                <p>{{ operationLabel(confirmationOperation) }}</p>
                <p>{{ translate('Mission_ConfirmCount', [confirmationPreview.impact_count]) }}</p>
                <ul class="impact-list">
                    <li v-for="impact in confirmationPreview.impacts" :key="impact.internal_name">
                        <strong>{{ impact.title }}</strong>
                        <code>{{ impact.internal_name }}</code>
                        <span>{{ statusLabel(impact.before_status) }} → {{ statusLabel(impact.after_status) }}</span>
                    </li>
                </ul>
                <p v-if="confirmationPreview.conflict_ids.length" class="danger">
                    {{ translate('Mission_Conflicts', [confirmationPreview.conflict_ids.join(', ')]) }}
                </p>
                <div class="modal-actions">
                    <button type="button" :disabled="palStore.MISSION_LOADING" @click="confirmationPreview = null">{{ translate('Mission_Cancel') }}</button>
                    <button type="button" :disabled="palStore.MISSION_LOADING || !confirmationPreview.impact_count" @click="confirmOperation">{{ translate('Mission_ConfirmApply') }}</button>
                </div>
            </section>
        </div>
    </section>
</template>

<style scoped>
.mission-editor { position: relative; display: grid; gap: 12px; min-width: 0; padding: 18px; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); background: var(--ui-surface); color: var(--ui-text); }
.mission-heading, .mission-toolbar, .mission-actions, .mission-pagination, .mission-heading-actions { display: flex; align-items: center; gap: 8px; }
.mission-heading { justify-content: space-between; }
.mission-heading p { margin: 0; color: var(--ui-text-muted); font-size: 11px; }
.mission-heading-actions { margin-left: auto; }
.complete-all-button { border-color: #356e59; background: #214d3c; color: #c4f5df; }
button, input, select { min-height: 34px; box-sizing: border-box; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); background: var(--ui-surface-raised); color: var(--ui-text); }
button { padding: 0 10px; cursor: pointer; }
button:disabled { opacity: .5; cursor: not-allowed; }
input, select { padding: 0 9px; }
.mission-toolbar { flex-wrap: wrap; }
.mission-toolbar input { flex: 1 1 260px; min-width: 180px; }
.mission-actions { padding: 10px; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); background: var(--ui-canvas); }
.mission-actions span { margin-right: auto; }
.mission-warnings, .mission-error, .mission-readonly { padding: 10px 12px; border-radius: var(--ui-radius-sm); background: #342f22; color: #f3d98d; }
.mission-warnings p { margin: 2px 0; }
.mission-error { display: flex; align-items: center; gap: 8px; background: #3d2328; color: #ffc4c9; }
.mission-error button { margin-left: auto; }
.mission-readonly { background: #302b3b; color: #d8c8ff; }
.mission-stats { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; }
.mission-stats span { padding: 9px; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); background: var(--ui-canvas); }
.danger { color: #ff9ba4; }
.mission-table-wrap { width: 100%; min-width: 0; overflow-x: auto; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); }
table { width: 100%; min-width: 1040px; border-collapse: collapse; }
th, td { padding: 9px; border-bottom: 1px solid var(--ui-border); text-align: left; vertical-align: middle; }
th { position: sticky; top: 0; z-index: 1; background: var(--ui-surface-raised); }
th.selection-column { width: 36px; }
.actions-column, .row-actions { min-width: 310px; text-align: left; }
th button { min-height: 28px; padding: 0; border: 0; background: transparent; font-weight: 700; }
tbody tr { background: var(--ui-surface); cursor: pointer; }
tbody tr:hover { background: var(--ui-surface-raised); }
tbody tr.inconsistent { box-shadow: inset 3px 0 #d95966; }
td strong, td small { display: block; }
td small { margin-top: 3px; color: #e1b86b; }
code { color: #aeb8d7; font-size: 11px; }
.status-badge { display: inline-flex; padding: 3px 7px; border-radius: 999px; background: #39404c; font-size: 11px; }
.status-badge[data-status="completed"] { background: #214d3c; color: #a9efd2; }
.status-badge[data-status="in_progress"] { background: #263f67; color: #bcd7ff; }
.status-badge[data-status="inconsistent"] { background: #5b2930; color: #ffc4ca; }
.row-actions-inner { display: flex; align-items: center; justify-content: flex-start; gap: 5px; flex-wrap: wrap; }
.row-actions-inner button { min-height: 28px; white-space: nowrap; }
.empty-state { padding: 30px; text-align: center; color: var(--ui-text-muted); }
.mission-pagination { justify-content: flex-end; }
.mission-drawer { position: fixed; z-index: 25; top: 72px; right: 12px; bottom: 12px; width: min(440px, calc(100vw - 24px)); overflow-y: auto; padding: 18px; box-sizing: border-box; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); background: var(--ui-surface-raised); box-shadow: 0 18px 50px #0009; }
.mission-drawer header { display: flex; justify-content: space-between; gap: 12px; }
.mission-drawer h3 { margin: 0 0 4px; }
.mission-drawer dl { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 10px; }
.mission-drawer dt { color: var(--ui-text-muted); }
.mission-drawer dd { min-width: 0; margin: 0; overflow-wrap: anywhere; }
.mission-drawer pre { max-height: 220px; overflow: auto; white-space: pre-wrap; }
.drawer-actions { display: grid; gap: 7px; }
.mission-modal-backdrop { position: fixed; z-index: 40; inset: 0; display: grid; place-items: center; padding: 16px; background: #000a; }
.mission-modal { width: min(680px, 100%); max-height: 85vh; overflow-y: auto; padding: 20px; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); background: var(--ui-surface-raised); box-shadow: 0 24px 70px #000c; }
.impact-list { display: grid; gap: 6px; max-height: 320px; overflow-y: auto; padding: 0; list-style: none; }
.impact-list li { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 3px 12px; padding: 8px; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); }
.impact-list li span { grid-column: 1 / -1; color: var(--ui-text-muted); }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }
@media (max-width: 900px) {
    .mission-editor { padding: 12px; }
    .mission-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .mission-actions { flex-wrap: wrap; }
    .mission-actions span { flex: 1 0 100%; }
}
</style>
