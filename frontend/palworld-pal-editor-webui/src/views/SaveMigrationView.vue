<script setup>
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { usePalEditorStore } from '@/stores/paleditor';
import AppIcon from '@/components/modules/AppIcon.vue';

const store = usePalEditorStore();
const router = useRouter();
const mode = ref('full');
const sourcePlatform = ref('steam');
const targetPlatform = ref('steam');
const sourcePath = ref('');
const targetPath = ref('');
const sourceId = ref('');
const targetId = ref('');
const mappings = ref([]);

const plan = computed(() => store.MIGRATION_PLAN);
const result = computed(() => store.MIGRATION_RESULT);
const targetPlayers = computed(() => plan.value?.target_summary?.players || []);
const hasDuplicateTargets = computed(() => {
  const selected = mappings.value
    .filter(item => item.selected && item.target_player_uid)
    .map(item => item.target_player_uid);
  return new Set(selected).size !== selected.length;
});
const mappingsReady = computed(() => {
  const selected = mappings.value.filter(item => item.selected);
  if (hasDuplicateTargets.value) return false;
  if (mode.value !== 'full' && !selected.length) {
    return false;
  }
  return selected.every(item => item.target_player_uid && item.target_instance_id);
});
const canExecute = computed(() => (
  plan.value
  && !plan.value.blockers?.length
  && mappingsReady.value
  && !store.MIGRATION_LOADING
));
const migrationModeLabel = computed(() => (
  result.value?.mode === 'full'
    ? t('Migration_ModeFull')
    : t('Migration_ModeCharacter')
));

watch(
  [
    mode,
    sourcePlatform,
    targetPlatform,
    sourcePath,
    targetPath,
    sourceId,
    targetId,
  ],
  () => {
    if (store.MIGRATION_LOADING || !plan.value) return;
    store.clearMigrationAnalysis();
    mappings.value = [];
  },
);

function t(key) {
  return store.getTranslatedText(key);
}

function migrationMessage(item) {
  const localized = t(item.code);
  return localized === 'I18N_MISSING' ? item.message : localized;
}

function sourceRef(platform, path, selectedId) {
  return platform === 'xgp'
    ? { platform, source_id: selectedId }
    : { platform, path: path.trim() };
}

function setPlatform(side, value) {
  if (side === 'source') sourcePlatform.value = value;
  else targetPlatform.value = value;
}

function setWgsSource(side, value) {
  if (side === 'source') sourceId.value = value;
  else targetId.value = value;
}

function setPath(side, value) {
  if (side === 'source') sourcePath.value = value;
  else targetPath.value = value;
}

async function choosePath(which) {
  const current = which === 'source' ? sourcePath.value : targetPath.value;
  const selected = await store.pickMigrationPath(current);
  if (!selected) return;
  if (which === 'source') sourcePath.value = selected;
  else targetPath.value = selected;
}

async function chooseWgsPath() {
  if (await store.pickMigrationWgsDirectory()) {
    sourceId.value = '';
    targetId.value = '';
  }
}

async function analyze() {
  const analyzed = await store.analyzeMigration({
    mode: mode.value,
    source: sourceRef(sourcePlatform.value, sourcePath.value, sourceId.value),
    target: sourceRef(targetPlatform.value, targetPath.value, targetId.value),
  });
  if (!analyzed) return;
  mappings.value = (analyzed.player_candidates || []).map(candidate => ({
    ...candidate,
    selected: candidate.auto_confirmed,
    target_player_uid: candidate.target_player_uid || '',
    target_instance_id: candidate.target_instance_id || '',
  }));
}

function selectTarget(mapping, uid) {
  const target = targetPlayers.value.find(item => item.player_uid === uid);
  mapping.target_player_uid = target?.player_uid || '';
  mapping.target_instance_id = target?.instance_id || '';
  mapping.evidence = 'manual';
}

async function execute() {
  await store.executeMigration({
    plan_id: plan.value.plan_id,
    mappings: mappings.value
      .filter(item => item.selected)
      .map(item => ({
        source_player_uid: item.source_player_uid,
        source_instance_id: item.source_instance_id,
        target_player_uid: item.target_player_uid,
        target_instance_id: item.target_instance_id,
        evidence: item.evidence || 'manual',
        confirmed: true,
      })),
    operation_id: crypto.randomUUID(),
  });
}
</script>

<template>
  <main :class="['migration-page', { 'migration-page--loaded': store.SAVE_LOADED_FLAG }]">
    <div class="migration-shell">
      <header class="migration-header">
      <button type="button" class="icon-button" :aria-label="t('Migration_Back')" @click="router.push('/')">
        <AppIcon name="back" :size="18" />
      </button>
      <div>
        <p>{{ t('Migration_Eyebrow') }}</p>
        <h1>{{ t('Migration_Title') }}</h1>
        <span>{{ t('Migration_OfflineOnly') }}</span>
      </div>
      </header>

      <section class="migration-card">
      <h2>1. {{ t('Migration_ModeTitle') }}</h2>
      <div class="mode-grid">
        <label :class="{ selected: mode === 'full' }">
          <input v-model="mode" type="radio" value="full" :disabled="store.MIGRATION_LOADING" />
          <strong>{{ t('Migration_ModeFull') }}</strong>
          <span>{{ t('Migration_ModeFullDescription') }}</span>
        </label>
        <label :class="{ selected: mode === 'character_only' }">
          <input v-model="mode" type="radio" value="character_only" :disabled="store.MIGRATION_LOADING" />
          <strong>{{ t('Migration_ModeCharacter') }}</strong>
          <span>{{ t('Migration_ModeCharacterDescription') }}</span>
        </label>
      </div>
      </section>

      <section class="migration-card">
      <h2>2. {{ t('Migration_SavesTitle') }}</h2>
      <div class="save-grid">
        <article v-for="side in ['source', 'target']" :key="side">
          <h3>{{ t(side === 'source' ? 'Migration_Source' : 'Migration_Target') }}</h3>
          <select
            :value="side === 'source' ? sourcePlatform : targetPlatform"
            :disabled="store.MIGRATION_LOADING"
            @change="setPlatform(side, $event.target.value)"
          >
            <option value="steam">{{ t('Migration_PlatformSteam') }}</option>
            <option value="xgp">{{ t('Migration_PlatformXgp') }}</option>
          </select>
          <template v-if="(side === 'source' ? sourcePlatform : targetPlatform) === 'steam'">
            <div class="path-row">
              <input
                :value="side === 'source' ? sourcePath : targetPath"
                :placeholder="t('Migration_PathPlaceholder')"
                :disabled="store.MIGRATION_LOADING"
                @input="setPath(side, $event.target.value)"
              />
              <button type="button" :disabled="store.MIGRATION_LOADING" @click="choosePath(side)">{{ t('Migration_Browse') }}</button>
            </div>
          </template>
          <template v-else>
            <div class="path-row">
              <input
                :value="store.XGP_WGS_PATH"
                :placeholder="t('Entry_Xgp_Path_Example')"
                readonly
              />
              <button type="button" :disabled="store.MIGRATION_LOADING" @click="chooseWgsPath">{{ t('Entry_Xgp_Select_Folder') }}</button>
            </div>
            <select
              :value="side === 'source' ? sourceId : targetId"
              :disabled="store.MIGRATION_LOADING"
              @change="setWgsSource(side, $event.target.value)"
            >
              <option value="">{{ t('Migration_SelectWgs') }}</option>
              <option v-for="item in store.XGP_SOURCES" :key="item.sourceId" :value="item.sourceId">
                {{ item.displayName }}
              </option>
            </select>
            <p v-if="side === 'target'" class="capability-note">{{ t('Migration_WgsTargetBlocked') }}</p>
          </template>
        </article>
      </div>
      <button class="primary" type="button" :disabled="store.MIGRATION_LOADING" @click="analyze">
        {{ store.MIGRATION_LOADING && store.MIGRATION_STAGE === 'analyzing' ? t('Migration_Analyzing') : t('Migration_Analyze') }}
      </button>
      </section>

      <section v-if="plan" class="migration-card">
      <h2>3. {{ t('Migration_AnalysisTitle') }}</h2>
      <div class="summary-grid">
        <article v-for="side in ['source_summary', 'target_summary']" :key="side">
          <h3>{{ t(side === 'source_summary' ? 'Migration_Source' : 'Migration_Target') }}</h3>
          <dl>
            <div><dt>{{ t('Migration_Platform') }}</dt><dd>{{ plan[side].platform }}</dd></div>
            <div><dt>{{ t('Migration_Version') }}</dt><dd>{{ plan[side].save_version }}</dd></div>
            <div><dt>{{ t('Migration_Players') }}</dt><dd>{{ plan[side].counts.players }}</dd></div>
            <div><dt>{{ t('Migration_Guilds') }}</dt><dd>{{ plan[side].counts.groups }}</dd></div>
            <div><dt>{{ t('Migration_Bases') }}</dt><dd>{{ plan[side].counts.bases }}</dd></div>
          </dl>
        </article>
      </div>
      <div v-if="plan.blockers?.length" class="message-list message-list--error" role="alert">
        <strong>{{ t('Migration_Blockers') }}</strong>
        <p v-for="item in plan.blockers" :key="item.code"><code>{{ item.code }}</code> · {{ migrationMessage(item) }}</p>
      </div>
      <div v-if="plan.warnings?.length" class="message-list">
        <strong>{{ t('Migration_Warnings') }}</strong>
        <p v-for="item in plan.warnings" :key="item.code">{{ migrationMessage(item) }}</p>
      </div>
      <div class="scope-grid">
        <article>
          <strong>{{ t('Migration_ScopeTitle') }}</strong>
          <ul>
            <li v-for="item in plan.migration_scope" :key="item">{{ t(`Migration_Scope_${item}`) }}</li>
          </ul>
        </article>
        <article>
          <strong>{{ t('Migration_OverwriteTitle') }}</strong>
          <ul>
            <li v-for="item in plan.overwritten_scope" :key="item">{{ t(`Migration_Scope_${item}`) }}</li>
          </ul>
        </article>
      </div>
      </section>

      <section v-if="plan" class="migration-card">
      <h2>4. {{ t('Migration_MappingTitle') }}</h2>
      <p>{{ t('Migration_MappingHint') }}</p>
      <div class="mapping-list">
        <label v-for="mapping in mappings" :key="mapping.source_player_uid" class="mapping-row">
          <input
            v-model="mapping.selected"
            type="checkbox"
            :disabled="store.MIGRATION_LOADING"
          />
          <span>
            <strong>{{ plan.source_summary.players.find(item => item.player_uid === mapping.source_player_uid)?.name || mapping.source_player_uid }}</strong>
            <small>{{ mapping.source_player_uid }} · {{ t(`Migration_Evidence_${mapping.evidence}`) }}</small>
          </span>
          <AppIcon name="forward" :size="17" />
          <select
            :value="mapping.target_player_uid"
            :disabled="!mapping.selected || store.MIGRATION_LOADING"
            @change="selectTarget(mapping, $event.target.value)"
          >
            <option value="">{{ t('Migration_SelectTarget') }}</option>
            <option v-for="target in targetPlayers" :key="target.player_uid" :value="target.player_uid">
              {{ target.name || target.player_uid }} · {{ target.player_uid }}
            </option>
          </select>
        </label>
      </div>
      <p v-if="hasDuplicateTargets" class="inline-error">{{ t('Migration_DuplicateTarget') }}</p>
      <p v-if="store.MIGRATION_LOADING" class="migration-stage" role="status">
        {{ t('Migration_CurrentStage') }}:
        {{ t(`Migration_Stage_${store.MIGRATION_STAGE}`) }}
      </p>
      <button class="primary danger" type="button" :disabled="!canExecute" @click="execute">
        {{ store.MIGRATION_LOADING ? t('Migration_Running') : t('Migration_Execute') }}
      </button>
      </section>

      <section v-if="store.LAST_ERROR?.context === 'migration'" class="migration-card result-card message-list--error" role="alert">
      <h2>{{ t('Migration_Failed') }}</h2>
      <code>{{ store.LAST_ERROR.code }}</code>
      <p>{{ store.LAST_ERROR.message }}</p>
      <dl v-if="store.LAST_ERROR.details">
        <div v-if="store.LAST_ERROR.details.recovery_status">
          <dt>{{ t('Migration_RecoveryStatus') }}</dt>
          <dd>{{ store.LAST_ERROR.details.recovery_status }}</dd>
        </div>
        <div v-if="store.LAST_ERROR.details.backup_path">
          <dt>{{ t('Migration_BackupPath') }}</dt>
          <dd><code>{{ store.LAST_ERROR.details.backup_path }}</code></dd>
        </div>
        <div v-if="store.LAST_ERROR.details.manifest_path">
          <dt>{{ t('Migration_ManifestPath') }}</dt>
          <dd><code>{{ store.LAST_ERROR.details.manifest_path }}</code></dd>
        </div>
      </dl>
      </section>

      <section v-if="result" class="migration-card result-card">
      <h2>{{ t('Migration_Completed') }}</h2>
      <dl>
        <div><dt>{{ t('Migration_ResultMode') }}</dt><dd>{{ migrationModeLabel }}</dd></div>
        <div><dt>{{ t('Migration_Validation') }}</dt><dd>{{ result.validation.level }}</dd></div>
        <div><dt>{{ t('Migration_RecoveryStatus') }}</dt><dd>{{ result.recovery_status }}</dd></div>
        <div><dt>{{ t('Migration_BackupPath') }}</dt><dd><code>{{ result.backup_path }}</code></dd></div>
        <div><dt>{{ t('Migration_ManifestPath') }}</dt><dd><code>{{ result.manifest_path }}</code></dd></div>
        <div><dt>{{ t('Migration_WrittenFiles') }}</dt><dd>{{ result.written_files.length }}</dd></div>
      </dl>
      <h3>{{ t('Migration_ResultMappings') }}</h3>
      <ul>
        <li v-for="item in result.migrated_players" :key="item.source_player_uid">
          <code>{{ item.source_player_uid }}</code> → <code>{{ item.target_player_uid }}</code>
        </li>
      </ul>
      <h3>{{ t('Migration_WrittenFiles') }}</h3>
      <ul>
        <li v-for="item in result.written_files" :key="item"><code>{{ item }}</code></li>
      </ul>
      <h3>{{ t('Migration_RuntimeChecklist') }}</h3>
      <ul>
        <li v-if="!result.validation.game_load_validated">{{ t('Migration_Runtime_GameLoad') }}</li>
        <li v-if="!result.validation.player_access_validated">{{ t('Migration_Runtime_PlayerAccess') }}</li>
        <li v-if="!result.validation.restart_persistence_validated">{{ t('Migration_Runtime_Restart') }}</li>
        <li v-if="!result.validation.wgs_cloud_sync_validated">{{ t('Migration_Runtime_WgsCloud') }}</li>
      </ul>
      <p>{{ t('Migration_RuntimeStillRequired') }}</p>
      </section>
    </div>
  </main>
</template>

<style scoped>
.migration-page {
  width: 100%;
  min-height: 100dvh;
  padding: 96px clamp(16px, 3vw, 36px) 80px;
  color: var(--ui-text);
  background:
    radial-gradient(circle at 78% 4%, color-mix(in srgb, var(--ui-accent) 9%, transparent), transparent 32rem),
    var(--ui-canvas);
}
.migration-page--loaded { padding-top: calc(var(--editor-top-offset) + 24px); }
.migration-shell { width: min(1120px, 100%); margin-inline: auto; }
.migration-header { display: flex; align-items: flex-start; gap: 18px; margin-bottom: 26px; padding-inline: 4px; }
.migration-header p { margin: 0 0 6px; color: var(--ui-accent); font-size: 12px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
.migration-header h1 { margin: 0; font-size: clamp(30px, 4vw, 42px); font-weight: 760; letter-spacing: -.035em; line-height: 1.1; text-wrap: balance; }
.migration-header span { display: block; max-width: 72ch; margin-top: 10px; color: var(--ui-text-secondary); line-height: 1.6; }
.icon-button { flex: 0 0 auto; width: 42px; height: 42px; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); background: var(--ui-surface); color: inherit; display: grid; place-items: center; box-shadow: var(--ui-shadow-sm); }
.icon-button:hover { color: var(--ui-accent); border-color: var(--ui-border-strong); background: var(--ui-surface-hover); }
.migration-card { margin-top: 16px; padding: clamp(20px, 2.4vw, 28px); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-lg); background: color-mix(in srgb, var(--ui-surface) 94%, transparent); box-shadow: var(--ui-shadow-sm); }
.migration-card h2 { margin: 0 0 20px; font-size: 18px; font-weight: 720; letter-spacing: -.01em; }
.migration-card h3 { margin: 0 0 12px; font-size: 14px; }
.mode-grid, .save-grid, .summary-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.mode-grid label { display: grid; grid-template-columns: auto 1fr; gap: 7px 12px; padding: 18px; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); background: var(--ui-surface-raised); cursor: pointer; transition: background-color 160ms ease, border-color 160ms ease, transform 120ms ease; }
.mode-grid label:hover { border-color: var(--ui-border-strong); background: var(--ui-surface-hover); }
.mode-grid label:active { transform: translateY(1px); }
.mode-grid label.selected { border-color: var(--ui-accent); background: color-mix(in srgb, var(--ui-accent) 10%, var(--ui-surface)); box-shadow: 0 0 0 1px color-mix(in srgb, var(--ui-accent) 22%, transparent) inset; }
.mode-grid input { margin-top: 3px; accent-color: var(--ui-accent); }
.mode-grid label span { grid-column: 2; color: var(--ui-text-secondary); line-height: 1.5; }
.save-grid article, .summary-grid article { padding: 18px; background: var(--ui-surface-raised); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); }
.save-grid article { display: grid; align-content: start; gap: 10px; }
.save-grid article h3 { margin-bottom: 2px; }
select, input[type="text"], .path-row input { width: 100%; min-height: 42px; padding: 9px 11px; color: var(--ui-text); border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); background: var(--ui-surface); }
.path-row { display: grid; grid-template-columns: 1fr auto; gap: 8px; }
.path-row button, .primary { min-height: 42px; padding: 0 18px; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); background: var(--ui-surface-raised); color: var(--ui-text); font-weight: 700; }
.path-row button:hover:not(:disabled) { border-color: var(--ui-border-strong); background: var(--ui-surface-hover); }
.primary { display: block; margin: 20px 0 0 auto; min-width: 190px; background: var(--ui-accent); color: #fff; border-color: var(--ui-accent); box-shadow: 0 8px 20px color-mix(in srgb, var(--ui-accent) 24%, transparent); }
.primary:hover:not(:disabled) { background: var(--ui-accent-strong); border-color: var(--ui-accent-strong); }
.primary.danger { background: #b5413a; border-color: #b5413a; }
button:disabled { opacity: .45; cursor: not-allowed; }
.capability-note, .migration-card > p { color: var(--ui-text-secondary); }
dl { margin: 0; }
dl div { display: flex; justify-content: space-between; gap: 18px; padding: 8px 0; border-bottom: 1px solid var(--ui-border); }
dt { color: var(--ui-text-secondary); }
dd { margin: 0; text-align: right; overflow-wrap: anywhere; }
.message-list { margin-top: 16px; padding: 14px; border-left: 3px solid #c18b32; background: color-mix(in srgb, #c18b32 8%, transparent); }
.message-list p { margin: 7px 0 0; }
.message-list--error { border-left-color: #b5413a; background: color-mix(in srgb, #b5413a 8%, transparent); }
.scope-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-top: 16px; }
.scope-grid article { padding: 14px; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-md); background: var(--ui-surface-raised); }
.scope-grid ul, .result-card ul { margin: 10px 0 0; padding-left: 20px; }
.mapping-list { display: grid; gap: 8px; }
.mapping-row { display: grid; grid-template-columns: auto minmax(0, .9fr) auto minmax(220px, 1fr); align-items: center; gap: 12px; padding: 12px; border: 1px solid var(--ui-border); border-radius: var(--ui-radius-sm); background: var(--ui-surface-raised); }
.mapping-row span { min-width: 0; }
.mapping-row strong, .mapping-row small { display: block; overflow: hidden; text-overflow: ellipsis; }
.mapping-row small { margin-top: 4px; color: var(--ui-text-secondary); }
.migration-stage { font-weight: 700; color: var(--ui-text) !important; }
.inline-error { color: #c75149 !important; }
.result-card code { overflow-wrap: anywhere; }
@media (max-width: 760px) {
  .migration-page { padding: 112px 14px 48px; }
  .migration-page--loaded { padding-top: calc(var(--editor-top-offset) + 18px); }
  .migration-header { gap: 13px; margin-bottom: 20px; padding-inline: 2px; }
  .migration-header h1 { font-size: clamp(28px, 9vw, 36px); }
  .migration-card { padding: 18px; }
  .mode-grid, .save-grid, .summary-grid, .scope-grid { grid-template-columns: 1fr; }
  .mapping-row { grid-template-columns: auto 1fr; }
  .mapping-row :deep(svg) { display: none; }
  .mapping-row select { grid-column: 2; }
}
@media (max-width: 520px) {
  .path-row { grid-template-columns: 1fr; }
  .path-row button, .primary { width: 100%; }
  .primary { min-width: 0; }
}
</style>
