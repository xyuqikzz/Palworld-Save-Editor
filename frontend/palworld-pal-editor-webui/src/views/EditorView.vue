<script setup>
import PalList from '@/components/PalList.vue';
import PlayerList from '@/components/PlayerList.vue';
import PalEditor from '@/components/PalEditor.vue';
import PlayerEditor from '@/components/PlayerEditor.vue';
import { usePalEditorStore } from '@/stores/paleditor'
import { computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

const palStore = usePalEditorStore()
const route = useRoute();
const router = useRouter();
let applyingRoute = false;
let routeApplyPending = false;
let stateSyncedRoutePath = null;
const editorMode = computed(() => route.meta.editorMode === 'player' ? 'player' : 'pal');
const editorHomeRoute = computed(() => editorMode.value === 'player' ? 'Players' : 'Editor');

function routeParam(value) {
    return Array.isArray(value) ? value[0] : value;
}

function findBase(baseKey) {
    for (const guild of palStore.GUILD_TREE) {
        const base = guild.bases?.find(item => item.node_id === baseKey);
        if (base) return { guild, base };
    }
    return null;
}

function consumeStateSyncedRoute(path) {
    const expectedPath = stateSyncedRoutePath;
    stateSyncedRoutePath = null;
    return expectedPath === path;
}

async function replaceWithEditor() {
    palStore.clearEditorSelection();
    if (route.name !== editorHomeRoute.value) {
        await router.replace({ name: editorHomeRoute.value });
    }
}

async function applyCurrentRoute() {
    if (!palStore.SAVE_LOADED_FLAG) return;
    if (consumeStateSyncedRoute(route.fullPath)) return;
    if (applyingRoute) {
        routeApplyPending = true;
        return;
    }

    applyingRoute = true;
    try {
        const playerId = routeParam(route.params.playerId);
        const palId = routeParam(route.params.palId);
        const baseKey = routeParam(route.params.baseKey);

        if (route.name === 'Editor' || route.name === 'Players') {
            palStore.clearEditorSelection();
            return;
        }

        if (route.name === 'PlayerEditor') {
            if (!playerId || !palStore.PLAYER_MAP.has(playerId)) {
                await replaceWithEditor();
                return;
            }
            await palStore.selectPlayer(playerId, false, false);
            return;
        }

        if (route.name === 'PlayerPalEditor') {
            if (!playerId || !palStore.PLAYER_MAP.has(playerId)) {
                await replaceWithEditor();
                return;
            }
            await palStore.selectPlayer(playerId, false, false);
            if (!palId || !palStore.PAL_MAP.has(palId)) {
                await replaceWithEditor();
                return;
            }
            await palStore.selectPal(palId);
            return;
        }

        if (route.name === 'BaseEditor') {
            const target = findBase(baseKey);
            if (!target) {
                await replaceWithEditor();
                return;
            }
            await palStore.selectBase(target.guild, target.base);
            return;
        }

        if (route.name === 'BasePalEditor') {
            const target = findBase(baseKey);
            if (!target) {
                await replaceWithEditor();
                return;
            }
            await palStore.selectBase(target.guild, target.base, false);
            if (!palId || !palStore.PAL_MAP.has(palId)) {
                await replaceWithEditor();
                return;
            }
            await palStore.selectPal(palId);
        }
    } finally {
        applyingRoute = false;
        if (routeApplyPending) {
            routeApplyPending = false;
            await applyCurrentRoute();
        }
    }
}

async function syncRouteFromEditorState() {
    if (applyingRoute || palStore.LOADING_FLAG || !palStore.SAVE_LOADED_FLAG) return;

    let location = { name: editorHomeRoute.value };
    if (editorMode.value === 'pal') {
        if (palStore.SELECTED_PAL_ID && palStore.SELECTED_BASE_KEY) {
            location = {
                name: 'BasePalEditor',
                params: {
                    baseKey: palStore.SELECTED_BASE_KEY,
                    palId: palStore.SELECTED_PAL_ID,
                },
            };
        } else if (palStore.SELECTED_PAL_ID && palStore.SELECTED_PLAYER_ID) {
            location = {
                name: 'PlayerPalEditor',
                params: {
                    playerId: palStore.SELECTED_PLAYER_ID,
                    palId: palStore.SELECTED_PAL_ID,
                },
            };
        }
    } else if (palStore.SHOW_PLAYER_EDIT_FLAG && palStore.SELECTED_PLAYER_ID) {
        const tab = route.name === 'PlayerEditor' ? route.query.tab : undefined;
        location = {
            name: 'PlayerEditor',
            params: { playerId: palStore.SELECTED_PLAYER_ID },
            query: tab ? { tab } : {},
        };
    }

    const targetPath = router.resolve(location).fullPath;
    if (targetPath !== route.fullPath) {
        stateSyncedRoutePath = targetPath;
        try {
            await router.replace(location);
        } catch (error) {
            if (stateSyncedRoutePath === targetPath) stateSyncedRoutePath = null;
            throw error;
        }
    }
}

watch(
    () => [route.name, route.params.playerId, route.params.palId, route.params.baseKey].join('|'),
    applyCurrentRoute,
    { immediate: true },
);

watch(
    () => [
        palStore.LOADING_FLAG,
        palStore.SELECTED_PLAYER_ID,
        palStore.SELECTED_BASE_KEY,
        palStore.SELECTED_PAL_ID,
        palStore.SHOW_PLAYER_EDIT_FLAG,
    ],
    syncRouteFromEditorState,
    { flush: 'post' },
);
</script>

<template>
    <div id="EditorDiv">
        <aside v-if="palStore.LAST_ERROR" class="error-banner" role="alert">
            <div>
                <strong>{{ palStore.LAST_ERROR.code }}</strong>
                <span>{{ palStore.LAST_ERROR.message }}</span>
                <small v-if="palStore.LAST_ERROR.action">
                    {{ palStore.LAST_ERROR.action }}
                </small>
                <small v-if="palStore.LAST_ERROR.details?.recovery_status">
                    {{ palStore.getTranslatedText('Xgp_Recovery_Status') }}: {{ palStore.LAST_ERROR.details.recovery_status }}
                </small>
                <small v-if="palStore.LAST_ERROR.details?.backup_path">
                    {{ palStore.getTranslatedText('Save_Backup_Path') }}: {{ palStore.LAST_ERROR.details.backup_path }}
                </small>
                <small v-if="palStore.LAST_ERROR.details?.phase">
                    {{ palStore.getTranslatedText('Save_Backup_Phase') }}: {{ palStore.LAST_ERROR.details.phase }}
                </small>
                <small v-if="palStore.LAST_ERROR.details?.failed_file">
                    {{ palStore.getTranslatedText('Save_Backup_File') }}: {{ palStore.LAST_ERROR.details.failed_file }}
                </small>
                <small v-if="palStore.LAST_ERROR.details?.os_error_category">
                    {{ palStore.getTranslatedText('Save_Backup_Os_Error') }}:
                    {{ palStore.LAST_ERROR.details.os_error_category }}
                    <template v-if="palStore.LAST_ERROR.details?.os_error_code !== null && palStore.LAST_ERROR.details?.os_error_code !== undefined">
                        ({{ palStore.LAST_ERROR.details.os_error_code }})
                    </template>
                </small>
                <small v-if="palStore.LAST_ERROR.details?.manifest_path">{{ palStore.LAST_ERROR.details.manifest_path }}</small>
                <small v-if="palStore.LAST_ERROR.details?.journal_path">{{ palStore.LAST_ERROR.details.journal_path }}</small>
            </div>
            <button @click="palStore.LAST_ERROR = null" :aria-label="palStore.getTranslatedText('Common_DismissError')">×</button>
        </aside>
        <section v-if="palStore.RAW_JSON_PENDING" class="raw-json-lock">
            <strong>{{ palStore.getTranslatedText('JsonEditor_RawLockTitle') }}</strong>
            <p>{{ palStore.getTranslatedText('JsonEditor_RawLockText') }}</p>
            <button type="button" @click="router.push({ name: 'JsonEditor' })">
                {{ palStore.getTranslatedText('TopBar_Btn_JsonEditor') }}
            </button>
        </section>
        <div v-else id="EditorMain">
            <aside :class="['selection-column', `selection-column--${editorMode}`]">
                <PlayerList :mode="editorMode"></PlayerList>
                <PalList
                    v-if="editorMode === 'pal' && (palStore.SELECTED_PLAYER_ID || palStore.BASE_PAL_BTN_CLK_FLAG)"
                ></PalList>
            </aside>
            <PlayerEditor
                v-if="editorMode === 'player' && palStore.SHOW_PLAYER_EDIT_FLAG"
            ></PlayerEditor>
            <PalEditor
                v-else-if="editorMode === 'pal' && palStore.SELECTED_PAL_ID && palStore.SELECTED_PAL_DATA"
            ></PalEditor>
            <section v-else class="editor-empty">
                <p>
                    {{ palStore.getTranslatedText(
                        editorMode === 'player'
                            ? 'Editor_Select_Player_Target'
                            : 'Editor_Select_Pal_Target'
                    ) }}
                </p>
            </section>
        </div>
    </div>
</template>
<style scoped>
div#EditorDiv {
    display: flow-root;
    min-height: 100dvh;
    width: 100%;
    overflow-x: clip;
    background: var(--ui-canvas);
}

div#EditorMain {
    display: grid;
    grid-template-columns: minmax(364px, 416px) minmax(0, 1fr);
    align-items: stretch;
    gap: 14px;
    width: 100%;
    margin-top: var(--editor-top-offset);
    margin-inline: 0;
    padding: 0 10px 16px;
    background: var(--ui-canvas);
}

.selection-column {
    display: grid;
    grid-template-rows: minmax(220px, 34vh) minmax(0, 1fr);
    gap: 12px;
    height: var(--sub-height);
    min-width: 0;
    min-height: 0;
    background: var(--ui-canvas);
}

.selection-column :deep(.list-panel) {
    height: 100%;
    min-height: 0;
}

.selection-column--player {
    grid-template-rows: minmax(0, 1fr);
}

.error-banner {
    position: fixed;
    z-index: 20;
    top: calc(var(--editor-top-offset) + 4px);
    right: 14px;
    display: flex;
    max-width: min(520px, calc(100vw - 28px));
    align-items: center;
    gap: 14px;
    padding: 10px 12px;
    border: 1px solid var(--ui-danger);
    border-radius: var(--ui-radius-sm);
    background: var(--ui-danger-soft);
    box-shadow: var(--ui-shadow-md);
}
.error-banner div { display: grid; gap: 2px; }
.error-banner strong { color: var(--ui-danger); font-size: 11px; }
.error-banner span { color: var(--ui-text); }
.error-banner small { color: var(--ui-text-muted); overflow-wrap: anywhere; }
.error-banner button { border: 0; color: var(--ui-text); background: transparent; font-size: 20px; }

.editor-empty {
    min-height: var(--sub-height);
    display: grid;
    place-content: center;
    justify-items: center;
    gap: 10px;
    margin: 0;
    background: var(--ui-surface);
    border: 1px dashed var(--ui-border-strong);
    border-radius: var(--ui-radius-md);
    color: var(--ui-text-muted);
}

.editor-empty p { margin: 0; }

.raw-json-lock {
    display: grid;
    min-height: var(--sub-height);
    max-width: 720px;
    place-content: center;
    justify-items: center;
    gap: 10px;
    margin: var(--editor-top-offset) auto 0;
    padding: 28px;
    color: var(--ui-text-secondary);
    text-align: center;
    background: var(--ui-surface);
    border: 1px solid oklch(0.48 0.1 72);
    border-radius: var(--ui-radius-lg);
}

.raw-json-lock strong { color: oklch(0.82 0.12 78); font-size: 18px; }
.raw-json-lock p { max-width: 56ch; margin: 0; color: var(--ui-text-muted); line-height: 1.6; }
.raw-json-lock button {
    min-height: 36px;
    margin-top: 6px;
    padding: 0 13px;
    color: oklch(0.16 0.025 252);
    background: var(--ui-accent);
    border: 1px solid var(--ui-accent);
    border-radius: var(--ui-radius-sm);
    font: inherit;
    font-size: 12px;
    font-weight: 650;
}

@media (max-width: 1120px) {
    div#EditorMain {
        grid-template-columns: minmax(0, 1fr);
        width: 100%;
        min-width: 0;
        margin-inline: 0;
        padding-inline: 10px;
    }

    .selection-column {
        grid-template-columns: repeat(2, minmax(0, 1fr));
        grid-template-rows: clamp(240px, 34vh, 340px);
        height: auto;
    }

    .selection-column > :only-child { grid-column: 1 / -1; }
    div#EditorDiv { overflow-x: clip; }
}

@media (max-width: 680px) {
    div#EditorMain { gap: 10px; padding-inline: 8px; }
    .selection-column {
        grid-template-columns: minmax(0, 1fr);
        grid-template-rows: none;
        grid-auto-rows: clamp(240px, 34vh, 320px);
        gap: 10px;
    }
}
</style>
