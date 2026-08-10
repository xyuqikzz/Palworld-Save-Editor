<script setup>
import { usePalEditorStore } from '@/stores/paleditor'
import AppIcon from '@/components/modules/AppIcon.vue'
import CustomPassiveDialog from '@/components/modules/CustomPassiveDialog.vue'
import ElementIcon from '@/components/modules/ElementIcon.vue'
import PassivePresetDialog from '@/components/modules/PassivePresetDialog.vue'
import PassiveSkillCard from '@/components/modules/PassiveSkillCard.vue'
import PalSkillPicker from '@/components/modules/PalSkillPicker.vue'
import PalSpeciesPicker from '@/components/modules/PalSpeciesPicker.vue'
import VariantBadge from '@/components/modules/VariantBadge.vue'
import { showMessage } from '@/services/message-dialog'
import { computed, ref } from 'vue'
const palStore = usePalEditorStore()
const cloneContainer = ref('AUTO')
const presetInput = ref(null)
const passivePresetDialog = ref(null)
const customPassiveDialog = ref(null)
const passivePresets = ref([])

function saveJson(preset) {
  const blob = new Blob([JSON.stringify(preset, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${preset.kind}-preset-v${preset.version}.json`
  link.click()
  URL.revokeObjectURL(url)
}

async function exportPreset(kind) {
  const preset = await palStore.exportPreset(kind, palStore.SELECTED_PAL_ID)
  if (preset) saveJson(preset)
}

async function importPreset(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  try {
    const preset = JSON.parse(await file.text())
    if (!['skills', 'pal'].includes(preset.kind)) {
      throw new Error('Choose a skills or Pal preset.')
    }
    const targets = palStore.BULK_PAL_IDS.length
      ? [...palStore.BULK_PAL_IDS]
      : [palStore.SELECTED_PAL_ID]
    await palStore.applyPreset(preset, targets)
  } catch (error) {
    void showMessage({
      tone: 'error',
      message: palStore.getTranslatedText('MessageDialog_PresetImportFailed'),
      details: error.message,
      dismissible: false,
    })
  }
}

function filterInvalid(list) {
  return list.filter(item => {
    if (palStore.HIDE_INVALID_OPTIONS) {
      return !(item.Invalid || item.IsHuman)
    }
    return true
  })
}

const equippableMasteredSkills = computed(() => {
  const masteredSkills = palStore.SELECTED_PAL_DATA?.MasteredWaza || []
  const equippedSkills = new Set(palStore.SELECTED_PAL_DATA?.EquipWaza || [])
  const availableSkills = [...new Set(masteredSkills)]
    .filter(skill => !equippedSkills.has(skill))
    .map(skill => palStore.ACTIVE_SKILLS[skill])
    .filter(Boolean)

  return filterInvalid(availableSkills)
})

const isMaxSuit = key => {
  return palStore.SELECTED_PAL_DATA.Suitabilities[key] >= palStore.MAX_SUITABILITY_LEVEL;
};

const isMinSuit = key => {
  const baseLevel = palStore.PAL_STATIC_DATA[palStore.SELECTED_PAL_DATA.DataAccessKey]?.Suitabilities[key]
  const condensationBonus = palStore.SELECTED_PAL_DATA.Rank >= 5 && baseLevel < 5 ? 1 : 0
  return baseLevel === palStore.SELECTED_PAL_DATA.Suitabilities[key] - condensationBonus
};

const areAllEnhancementsMax = computed(() => (
  palStore.SELECTED_PAL_DATA?.areAllEnhancementsMax?.() ?? true
))

const soulBonusPercent = rank => Number(rank || 0) * 3

const maxableSuitabilityKeys = computed(() => {
  const suitabilities = palStore.SELECTED_PAL_DATA?.Suitabilities || {}
  const baseSuitabilities = palStore.PAL_STATIC_DATA[palStore.SELECTED_PAL_DATA?.DataAccessKey]?.Suitabilities || {}
  return Object.keys(suitabilities).filter(key => (
    !palStore.HIDE_INVALID_OPTIONS || Number(baseSuitabilities[key] || 0) > 0
  ))
})

const areAllSuitabilitiesMax = computed(() => (
  maxableSuitabilityKeys.value.length === 0
  || maxableSuitabilityKeys.value.every(key => isMaxSuit(key))
))

const applyPassivePreset = skills => {
  palStore.SELECTED_PAL_DATA.replacePassiveSkills(skills)
}

const pinnedPassivePresets = computed(() => passivePresets.value.filter(preset => preset.pinned))
const updatePassivePresets = presets => {
  passivePresets.value = presets
}
const passivePresetIsAvailable = preset => preset.skills.every(skill => palStore.PASSIVE_SKILLS[skill])
const passivePresetIsActive = preset => {
  const equipped = palStore.SELECTED_PAL_DATA?.PassiveSkillList || []
  return equipped.length === preset.skills.length
    && equipped.every((skill, index) => skill === preset.skills[index])
}

const addCustomPassive = async internalName => {
  if (await palStore.addCustomPassive(internalName)) {
    customPassiveDialog.value?.close()
  }
}

const isMaxLv = () => {
  return palStore.SELECTED_PAL_DATA.Level >= (palStore.HIDE_INVALID_OPTIONS ? palStore.MAX_LEVEL : palStore.MAX_INVALID_LEVEL);
};

const isMinLv = () => {
  return palStore.SELECTED_PAL_DATA.Level <= 1;
};

const isMaxFriendshipLv = () => {
  return palStore.SELECTED_PAL_DATA.FriendshipLevel >= palStore.MAX_FRIENDSHIP_LEVEL;
};

const isMinFriendshipLv = () => {
  return palStore.SELECTED_PAL_DATA.FriendshipLevel <= palStore.MIN_FRIENDSHIP_LEVEL;
};

const suitabilityIconSrc = key => {
  return key ? `/image/suitabilities/${key.split("::").pop()}` : '';
};

</script>

<template>
  <div :class="['PalEditor', 'pal-editor-layout', { 'unref': palStore.SELECTED_PAL_DATA.Is_Unref_Pal }]">
    <div class="EditorItem item flex-v basicInfo">
      <header class="pal-summary">
        <div class="pal-identity">
          <img class="pal-summary__portrait" :src="`/image/pals/${palStore.SELECTED_PAL_DATA.IconAccessKey}`" alt="">
          <div class="pal-summary__copy">
            <span class="pal-summary__eyebrow">{{ palStore.getTranslatedText("Editor_Basic_Info") }}</span>
            <strong>{{ palStore.SELECTED_PAL_DATA.NickName || palStore.SELECTED_PAL_DATA.I18nName }}</strong>
            <span class="pal-summary__species">
              <ElementIcon v-for="element in palStore.PAL_STATIC_DATA[palStore.SELECTED_PAL_DATA.DataAccessKey]?.Elements || []"
                :key="element" :element="element" :size="15" />
              {{ palStore.PAL_STATIC_DATA[palStore.SELECTED_PAL_DATA.DataAccessKey]?.I18n || palStore.SELECTED_PAL_DATA.DataAccessKey }}
            </span>
          </div>
        </div>
        <div class="editor-card-actions">
          <button type="button" class="max-pal-button" @click="palStore.maxSelectedPal"
            :disabled="palStore.LOADING_FLAG" :title="palStore.getTranslatedText('PalEditor_MaxPal_Tooltip')">
            {{ palStore.getTranslatedText("PalEditor_MaxPal") }}
          </button>
          <button id="dump_btn" @click="palStore.dumpPalData" :disabled="palStore.LOADING_FLAG">
            {{ palStore.getTranslatedText("Editor_Btn_Export_Data") }}
          </button>
          <button @click="exportPreset('skills')" :disabled="palStore.LOADING_FLAG">{{ palStore.getTranslatedText('PalEditor_ExportSkills') }}</button>
          <button @click="exportPreset('pal')" :disabled="palStore.LOADING_FLAG">{{ palStore.getTranslatedText('PalEditor_ExportPreset') }}</button>
          <button @click="presetInput?.click()" :disabled="palStore.LOADING_FLAG">{{ palStore.getTranslatedText('PalEditor_ImportPreset') }}</button>
          <input ref="presetInput" class="preset-file-input" type="file" accept="application/json,.json" @change="importPreset">
          <select v-if="!palStore.BASE_PAL_BTN_CLK_FLAG" v-model="cloneContainer" class="clone-target" :aria-label="palStore.getTranslatedText('PalEditor_CloneDestination')">
            <option value="AUTO">{{ palStore.getTranslatedText('PalEditor_CloneAutomatic') }}</option>
            <option value="PARTY">{{ palStore.getTranslatedText('PalEditor_CloneParty') }}</option>
            <option value="PAL_STORAGE">{{ palStore.getTranslatedText('PalEditor_CloneStorage') }}</option>
          </select>
          <button id="dupe_btn" @click="palStore.dupePal(cloneContainer)" :disabled="palStore.LOADING_FLAG"
            v-if="!palStore.BASE_PAL_BTN_CLK_FLAG">
            {{ palStore.getTranslatedText("Editor_Btn_Dupe_Pal") }}
          </button>
          <span class="action-separator" aria-hidden="true"></span>
          <button v-if="palStore.SELECTED_PAL_DATA.IsExpeditionPal" class="cancel-expedition"
            @click="palStore.cancelSelectedPalExpedition" :disabled="palStore.LOADING_FLAG"
            :title="palStore.getTranslatedText('PalEditor_CancelExpedition_Tooltip')">
            {{ palStore.getTranslatedText("PalEditor_CancelExpedition") }}
          </button>
          <button id="del_btn" @click="palStore.delPal" :disabled="palStore.LOADING_FLAG">
            {{ palStore.getTranslatedText("Editor_Btn_Delete_Pal") }}
          </button>
        </div>
      </header>

      <p v-if="palStore.SELECTED_PAL_DATA.Is_Unref_Pal">
        {{ palStore.getTranslatedText("Editor_Note_Ghost_Pal") }}
      </p>

      <div class="item flex-v left basic-fields">
        <div class="editField identity-field">
          <p class="const" :title="palStore.SELECTED_PAL_DATA.InternalName">
            {{ palStore.getTranslatedText("Editor_Species") }}
          </p>
          <PalSpeciesPicker
            v-model="palStore.SELECTED_PAL_DATA.DataAccessKey"
            :options="filterInvalid(palStore.PAL_STATIC_DATA_LIST)"
            :selected-option="palStore.PAL_STATIC_DATA[palStore.SELECTED_PAL_DATA.DataAccessKey]"
            :disabled="palStore.LOADING_FLAG"
            :show-selected-icon="false"
            :show-internal-name="!palStore.HIDE_INVALID_OPTIONS"
            :title="palStore.getTranslatedText('Editor_Species_Picker_Title')"
            :search-placeholder="palStore.getTranslatedText('Editor_Species_Search_Placeholder')"
            :results-label="palStore.getTranslatedText('Editor_Species_Results_Label')"
            :empty-text="palStore.getTranslatedText('Editor_Species_Empty')"
            :close-label="palStore.getTranslatedText('Common_Close')"
          />
          <button class="edit" @click="palStore.SELECTED_PAL_DATA.changeSpecie" name="CharacterID"
            :disabled="palStore.LOADING_FLAG" :title="palStore.getTranslatedText('TopBar_Btn_Save')"><AppIcon name="check" /></button>

        </div>
        <div class="editField identity-field">
          <p class="const">
            {{ palStore.getTranslatedText("Editor_Nickname") }}
          </p>
          <input class="edit" type="text" name="NickName" v-model="palStore.SELECTED_PAL_DATA.NickName"
            :placeholder="palStore.SELECTED_PAL_DATA.I18nName">
          <button class="edit" @click="palStore.updatePal" name="NickName" :value="palStore.SELECTED_PAL_DATA.NickName"
            :disabled="palStore.LOADING_FLAG" :title="palStore.getTranslatedText('TopBar_Btn_Save')"><AppIcon name="check" /></button>
        </div>
        <div v-if="palStore.SELECTED_PAL_DATA.IsHuman" class="editField identity-field npc-weapon-field">
          <p class="const">
            {{ palStore.getTranslatedText("PalEditor_NpcWeapon") }}
          </p>
          <p class="const npc-weapon-value">
            {{ palStore.getNpcWeaponDisplayName(palStore.SELECTED_PAL_DATA.NpcDefaultWeapon) }}
          </p>
        </div>
        <div class="flex-h attribute-row">
          <div class="editField">
            <p class="const" :title="palStore.getTranslatedText('PalEditor_TrustBonus_Tooltip')">
              {{ palStore.getTranslatedText("Editor_Friendship_Level") }} {{ palStore.SELECTED_PAL_DATA.FriendshipLevel }}
            </p>
            <button class="edit" @click="palStore.SELECTED_PAL_DATA.friendshipLevelDown" name="FriendshipLevel"
              :disabled="palStore.LOADING_FLAG || isMinFriendshipLv()" :title="palStore.getTranslatedText('Common_Decrease')"><AppIcon name="chevron-down" /></button>
            <button class="edit" @click="palStore.SELECTED_PAL_DATA.friendshipLevelUp" name="FriendshipLevel"
              :disabled="palStore.LOADING_FLAG || isMaxFriendshipLv()" :title="palStore.getTranslatedText('Common_Increase')"><AppIcon name="chevron-up" /></button>
            <button class="edit" @click="palStore.SELECTED_PAL_DATA.maxFriendshipLevel" name="FriendshipLevel"
              :disabled="palStore.LOADING_FLAG || isMaxFriendshipLv()" :title="palStore.getTranslatedText('Common_SetMaximum')"><AppIcon name="chevrons-up" /></button>
          </div>
          <div class="editField" v-if="palStore.SELECTED_PAL_DATA.Level">
            <p class="const"> {{ palStore.getTranslatedText('Common_LevelShort') }} {{ palStore.SELECTED_PAL_DATA.Level }}</p>
            <button class="edit" @click="palStore.SELECTED_PAL_DATA.levelDown" name="Level"
              :disabled="palStore.LOADING_FLAG || isMinLv()" :title="palStore.getTranslatedText('Common_Decrease')"><AppIcon name="chevron-down" /></button>
            <button class="edit" @click="palStore.SELECTED_PAL_DATA.levelUp" name="Level"
              :disabled="palStore.LOADING_FLAG || isMaxLv()" :title="palStore.getTranslatedText('Common_Increase')"><AppIcon name="chevron-up" /></button>
            <button class="edit" @click="palStore.SELECTED_PAL_DATA.maxLevel" name="Level"
              :disabled="palStore.LOADING_FLAG || isMaxLv()" :title="palStore.getTranslatedText('Common_SetMaximum')"><AppIcon name="chevrons-up" /></button>
          </div>
        </div>
        <div class="flex-h attribute-row" v-if="!palStore.SELECTED_PAL_DATA.IsHuman">
          <div class="editField" v-if="palStore.SELECTED_PAL_DATA.Gender || !palStore.HIDE_INVALID_OPTIONS">
            <p class="const">
              {{ palStore.getTranslatedText("Editor_Gender") }}
              {{ palStore.SELECTED_PAL_DATA.displayGender() }}
            </p>
            <button class="edit" @click="palStore.SELECTED_PAL_DATA.swapGender" name="Gender"
              :disabled="palStore.LOADING_FLAG" :title="palStore.getTranslatedText('Common_Toggle')"><AppIcon name="refresh" /></button>
          </div>

          <div class="editField">
            <p class="const">
              {{ palStore.getTranslatedText("Editor_Variant") }}
              <VariantBadge v-if="palStore.SELECTED_PAL_DATA.IsTower" kind="tower" />
              <VariantBadge v-if="palStore.SELECTED_PAL_DATA.IsBOSS" kind="boss" />
              <VariantBadge v-if="palStore.SELECTED_PAL_DATA.IsRarePal" kind="rare" />
              {{ palStore.SELECTED_PAL_DATA.displaySpecialType() }}
            </p>
            <button class="edit" @click="palStore.SELECTED_PAL_DATA.swapTower" name="IsTower"
              v-if="palStore.SELECTED_PAL_DATA.HasTowerVariant" :disabled="palStore.LOADING_FLAG" :title="palStore.getTranslatedText('PalEditor_TowerVariant')"><AppIcon name="building" :size="15" /></button>
            <button class="edit variant-toggle" :class="{ 'is-active': palStore.SELECTED_PAL_DATA.IsBOSS }" :aria-pressed="palStore.SELECTED_PAL_DATA.IsBOSS" @click="palStore.SELECTED_PAL_DATA.swapBoss" name="IsBOSS"
              v-if="palStore.SELECTED_PAL_DATA.HasBossVariant" :disabled="palStore.LOADING_FLAG" :title="palStore.getTranslatedText('PalEditor_BossVariant')">{{ palStore.getTranslatedText('Variant_Boss') }}</button>
            <button class="edit variant-toggle" :class="{ 'is-active': palStore.SELECTED_PAL_DATA.IsRarePal }" :aria-pressed="palStore.SELECTED_PAL_DATA.IsRarePal" @click="palStore.SELECTED_PAL_DATA.swapRare" name="IsRarePal"
              v-if="palStore.SELECTED_PAL_DATA.HasBossVariant" :disabled="palStore.LOADING_FLAG" :title="palStore.getTranslatedText('PalEditor_RareVariant')">{{ palStore.getTranslatedText('Variant_Rare') }}</button>
          </div>
        </div>
        <div class="flex-h attribute-row" v-if="!palStore.SELECTED_PAL_DATA.IsHuman">
          <div class="editField awakening-field">
            <p class="const">
              {{ palStore.getTranslatedText("Editor_Awakening") }}:
              {{ palStore.getTranslatedText(palStore.SELECTED_PAL_DATA.IsAwakened
                ? "Editor_Awakening_Awakened"
                : "Editor_Awakening_NotAwakened") }}
            </p>
            <button class="edit awakening-toggle"
            :aria-pressed="palStore.SELECTED_PAL_DATA.IsAwakened"
            @click="palStore.SELECTED_PAL_DATA.swapAwakening" name="IsAwakened"
            :disabled="palStore.LOADING_FLAG"
            :title="palStore.getTranslatedText(palStore.SELECTED_PAL_DATA.IsAwakened
              ? 'Editor_Awakening_Disable'
              : 'Editor_Awakening_Enable')">
              <AppIcon name="refresh" />
            </button>
          </div>
        </div>
        <div class="metadata-grid">
          <p class="const meta-field">
            <span>{{ palStore.getTranslatedText("Editor_Pal_CharacterID") }}</span>
            <strong>{{ palStore.SELECTED_PAL_DATA.CharacterID }}</strong>
          </p>
          <p class="const meta-field">
            <span>{{ palStore.getTranslatedText("Editor_Pal_ID") }}</span>
            <strong>{{ palStore.SELECTED_PAL_ID }}</strong>
          </p>
          <p class="const meta-field">
            <span>{{ palStore.getTranslatedText("Editor_Pal_Guild_ID") }}</span>
            <strong>{{ palStore.SELECTED_PAL_DATA.group_id }}</strong>
          </p>
          <div class="editField metadata-slot">
            <p :class="['const', 'meta-field', { 'out_of_container': !palStore.SELECTED_PAL_DATA.in_owner_palbox }]"
              :title="palStore.SELECTED_PAL_DATA.in_owner_palbox ? '' : palStore.getTranslatedText('PalEditor_OutOfOwnerContainerTitle')">
              <span>{{ palStore.getTranslatedText("Editor_Pal_Slot") }}</span>
              <strong>#{{ palStore.SELECTED_PAL_DATA.SlotIndex ?? "—" }}</strong>
            </p>
            <button class="edit edit_text" @click="palStore.updatePal" name="in_owner_palbox"
              :disabled="palStore.LOADING_FLAG" v-if="!palStore.SELECTED_PAL_DATA.in_owner_palbox">
              {{ palStore.getTranslatedText("Editor_Btn_Retrieve_Pal") }}
            </button>
          </div>
          <p class="const meta-field">
            <span>{{ palStore.getTranslatedText("Editor_Pal_Owner") }}</span>
            <strong>{{ palStore.SELECTED_PAL_DATA.OwnerName || palStore.getTranslatedText("Editor_Pal_No_Owner") }}</strong>
          </p>
        </div>
        <section class="estimated-group">
          <div class="palInfo">
            <div class="metric"><span>{{ palStore.getTranslatedText("Editor_Estimated_HP") }}</span><strong>{{ palStore.SELECTED_PAL_DATA.ComputedMaxHP / 1000 }}</strong></div>
            <div class="metric"><span>{{ palStore.getTranslatedText("Editor_Estimated_ATK") }}</span><strong>{{ palStore.SELECTED_PAL_DATA.ComputedAttack }}</strong></div>
            <div class="metric"><span>{{ palStore.getTranslatedText("Editor_Estimated_DEF") }}</span><strong>{{ palStore.SELECTED_PAL_DATA.ComputedDefense }}</strong></div>
            <div class="metric"><span>{{ palStore.getTranslatedText("Editor_Estimated_WorkSpeed") }}</span><strong>{{ palStore.SELECTED_PAL_DATA.ComputedCraftSpeed }}</strong></div>
          </div>
        </section>
        <div class="editField" v-if="palStore.SELECTED_PAL_DATA.HasWorkerSick">
          <button class="edit text" @click="palStore.updatePal" name="HasWorkerSick" :disabled="palStore.LOADING_FLAG">
            {{ palStore.getTranslatedText("Editor_Btn_Heal_Pal") }}
          </button>
        </div>
        <div class="editField" v-if="palStore.SELECTED_PAL_DATA.IsFaintedPal">
          <button class="edit text" @click="palStore.updatePal" name="IsFaintedPal" :disabled="palStore.LOADING_FLAG">
            {{ palStore.getTranslatedText("Editor_Btn_Revive_Pal") }}
          </button>
        </div>
      </div>
    </div>
    <div class="EditorItem flex-v item left statsPanel">
      <button type="button" class="edit stats-max-all"
        :disabled="palStore.LOADING_FLAG || areAllEnhancementsMax"
        :title="palStore.getTranslatedText('PalEditor_MaxAllEnhancements')"
        @click="palStore.SELECTED_PAL_DATA.maxAllEnhancements">
        {{ palStore.getTranslatedText('Common_Max') }}
      </button>
      <div class="stat-primary-grid">
        <section class="stat-group stat-group--iv">
        <p class="cat">
          {{ palStore.getTranslatedText("Editor_IV") }}
        </p>
      <div class="editField spaceBetween">
        <p class="const">
          {{ palStore.getTranslatedText("Editor_IV_HP") }}
          {{ palStore.SELECTED_PAL_DATA.Talent_HP }}
        </p>
        <input class="slider" type="range" name="Talent_HP" min="0" :max="palStore.HIDE_INVALID_OPTIONS ? 100 : 255"
          :disabled="palStore.LOADING_FLAG" v-model="palStore.SELECTED_PAL_DATA.Talent_HP" @mouseup="palStore.updatePal"
          @touchend="palStore.updatePal">
      </div>
      <div class="editField spaceBetween">
        <p class="const">
          {{ palStore.getTranslatedText("Editor_IV_DEF") }}
          {{ palStore.SELECTED_PAL_DATA.Talent_Defense }}
        </p>
        <input class="slider" type="range" name="Talent_Defense" min="0"
          :max="palStore.HIDE_INVALID_OPTIONS ? 100 : 255" :disabled="palStore.LOADING_FLAG"
          v-model="palStore.SELECTED_PAL_DATA.Talent_Defense" @mouseup="palStore.updatePal"
          @touchend="palStore.updatePal">
      </div>
      <div class="editField spaceBetween">
        <p class="const">
          {{ palStore.getTranslatedText("Editor_IV_ATK") }}
          {{ palStore.SELECTED_PAL_DATA.Talent_Shot }}
        </p>
        <input class="slider" type="range" name="Talent_Shot" min="0" :max="palStore.HIDE_INVALID_OPTIONS ? 100 : 255"
          :disabled="palStore.LOADING_FLAG" v-model="palStore.SELECTED_PAL_DATA.Talent_Shot"
          @mouseup="palStore.updatePal" @touchend="palStore.updatePal">
      </div>
      <div class="editField spaceBetween" v-if="!palStore.HIDE_INVALID_OPTIONS">
        <p class="const">
          {{ palStore.getTranslatedText("Editor_IV_MELEE") }}
          {{ palStore.SELECTED_PAL_DATA.Talent_Melee }}
        </p>
        <input class="slider" type="range" name="Talent_Melee" min="0" :max="palStore.HIDE_INVALID_OPTIONS ? 100 : 255"
          :disabled="palStore.LOADING_FLAG" v-model="palStore.SELECTED_PAL_DATA.Talent_Melee"
          @mouseup="palStore.updatePal" @touchend="palStore.updatePal">
      </div>
        </section>
        <section class="stat-group stat-group--souls">
        <p class="cat">
          {{ palStore.getTranslatedText("Editor_Souls_Upgrade") }}
        </p>
      <div class="editField spaceBetween">
        <p class="const">
          {{ palStore.getTranslatedText("Editor_Souls_HP") }}
          {{ palStore.SELECTED_PAL_DATA.Rank_HP }} ({{ soulBonusPercent(palStore.SELECTED_PAL_DATA.Rank_HP) }}%)
        </p>
        <input class="slider" type="range" name="Rank_HP" min="0"
          :max="palStore.HIDE_INVALID_OPTIONS ? palStore.MAX_SOULS_LEVEL : 255" :disabled="palStore.LOADING_FLAG"
          v-model="palStore.SELECTED_PAL_DATA.Rank_HP" @mouseup="palStore.updatePal" @touchend="palStore.updatePal">
      </div>
      <div class="editField spaceBetween">
        <p class="const">
          {{ palStore.getTranslatedText("Editor_Souls_ATK") }}
          {{ palStore.SELECTED_PAL_DATA.Rank_Attack }} ({{ soulBonusPercent(palStore.SELECTED_PAL_DATA.Rank_Attack) }}%)
        </p>
        <input class="slider" type="range" name="Rank_Attack" min="0"
          :max="palStore.HIDE_INVALID_OPTIONS ? palStore.MAX_SOULS_LEVEL : 255" :disabled="palStore.LOADING_FLAG"
          v-model="palStore.SELECTED_PAL_DATA.Rank_Attack" @mouseup="palStore.updatePal" @touchend="palStore.updatePal">
      </div>
      <div class="editField spaceBetween">
        <p class="const">
          {{ palStore.getTranslatedText("Editor_Souls_DEF") }}
          {{ palStore.SELECTED_PAL_DATA.Rank_Defence }} ({{ soulBonusPercent(palStore.SELECTED_PAL_DATA.Rank_Defence) }}%)
        </p>
        <input class="slider" type="range" name="Rank_Defence" min="0"
          :max="palStore.HIDE_INVALID_OPTIONS ? palStore.MAX_SOULS_LEVEL : 255" :disabled="palStore.LOADING_FLAG"
          v-model="palStore.SELECTED_PAL_DATA.Rank_Defence" @mouseup="palStore.updatePal"
          @touchend="palStore.updatePal">
      </div>
      <div class="editField spaceBetween">
        <p class="const">
          {{ palStore.getTranslatedText("Editor_Souls_CraftSpeed") }}
          {{ palStore.SELECTED_PAL_DATA.Rank_CraftSpeed }} ({{ soulBonusPercent(palStore.SELECTED_PAL_DATA.Rank_CraftSpeed) }}%)
        </p>
        <input class="slider" type="range" name="Rank_CraftSpeed" min="0"
          :max="palStore.HIDE_INVALID_OPTIONS ? palStore.MAX_SOULS_LEVEL : 255" :disabled="palStore.LOADING_FLAG"
          v-model="palStore.SELECTED_PAL_DATA.Rank_CraftSpeed" @mouseup="palStore.updatePal"
          @touchend="palStore.updatePal">
      </div>
        </section>
      </div>
      <section class="stat-group stat-group--condenser">
        <p class="cat">
          {{ palStore.getTranslatedText("Editor_Condenser") }}
        </p>
      <div class="editField spaceBetween">
        <p class="const">
          {{ palStore.getTranslatedText("Editor_Condenser_Rank") }}
          {{ palStore.SELECTED_PAL_DATA.Rank - 1 }}
        </p>
        <input class="slider" type="range" name="Rank" min="1" :max="palStore.HIDE_INVALID_OPTIONS ? 5 : 255"
          v-model="palStore.SELECTED_PAL_DATA.Rank" :disabled="palStore.LOADING_FLAG" @mouseup="palStore.updatePal"
          @touchend="palStore.updatePal">
      </div>
      </section>
      <section class="stat-group stat-group--suitabilities suitabilityPanel"
        v-if="palStore.PAL_STATIC_DATA[palStore.SELECTED_PAL_DATA.DataAccessKey]?.Suitabilities">
        <header class="stat-group-header">
          <p class="cat">{{ palStore.getTranslatedText("Editor_Suitabilities") }}</p>
          <button type="button" class="edit suitability-max-all"
            :disabled="palStore.LOADING_FLAG || areAllSuitabilitiesMax"
            :title="palStore.getTranslatedText('PalEditor_MaxAllSuitabilities')"
            @click="palStore.SELECTED_PAL_DATA.maxAllSuitabilities">
            {{ palStore.getTranslatedText('Common_Max') }}
          </button>
        </header>
        <div class="editField skillList">
          <div v-for="(value, key) in palStore.SELECTED_PAL_DATA.Suitabilities"
            v-show="palStore.HIDE_INVALID_OPTIONS || value != 'EPalWorkSuitability::OilExtraction'">
            <p class="const">
              <img :class="['suitIcon']" :src="suitabilityIconSrc(key)" alt="">
              {{ value }}
            </p>
            <button class="edit" @click="palStore.SELECTED_PAL_DATA.suitDown" :name="key"
              :disabled="palStore.LOADING_FLAG || isMinSuit(key)" :title="palStore.getTranslatedText('PalEditor_DecreaseSuitability')"><AppIcon name="chevron-down" /></button>
            <button class="edit" @click="palStore.SELECTED_PAL_DATA.suitUp" :name="key"
              :disabled="palStore.LOADING_FLAG || isMaxSuit(key)" :title="palStore.getTranslatedText('PalEditor_IncreaseSuitability')"><AppIcon name="chevron-up" /></button>
            <button class="edit" @click="palStore.SELECTED_PAL_DATA.suitMax" :name="key"
              :disabled="palStore.LOADING_FLAG || isMaxSuit(key)" :title="palStore.getTranslatedText('Common_SetMaximum')"><AppIcon name="chevrons-up" /></button>
          </div>
        </div>
      </section>
    </div>
    <div class="EditorItem item flex-v left skillPanel skillsPanel">
      <section class="skill-section passive-skill-section">
        <header class="skill-section-header">
          <h3>{{ palStore.getTranslatedText("Editor_Passive_Skills") }}</h3>
          <div class="skill-section-actions">
            <button type="button" class="custom-passive-trigger"
              :disabled="palStore.LOADING_FLAG || (palStore.HIDE_INVALID_OPTIONS && palStore.SELECTED_PAL_DATA.PassiveSkillList.length >= 4)"
              @click="customPassiveDialog?.open()">
              {{ palStore.getTranslatedText('PalEditor_AddCustomPassive') }}
            </button>
            <button type="button" class="passive-preset-trigger"
              :disabled="palStore.LOADING_FLAG"
              @click="passivePresetDialog?.open()">
              {{ palStore.getTranslatedText('PalEditor_PassivePresets') }}
            </button>
            <PalSkillPicker
              v-model="palStore.PAL_PASSIVE_SELECTED_ITEM"
              kind="passive"
              icon-only
              :options="palStore.PASSIVE_SKILLS_LIST"
              :selected-option="palStore.PASSIVE_SKILLS[palStore.PAL_PASSIVE_SELECTED_ITEM]"
              :disabled="palStore.LOADING_FLAG || (palStore.HIDE_INVALID_OPTIONS && palStore.SELECTED_PAL_DATA.PassiveSkillList.length >= 4)"
              :show-internal-name="!palStore.HIDE_INVALID_OPTIONS"
              :placeholder="palStore.getTranslatedText('Editor_Select_Passive')"
              :title="palStore.getTranslatedText('Editor_Passive_Picker_Title')"
              :search-placeholder="palStore.getTranslatedText('Editor_Passive_Search_Placeholder')"
              :results-label="palStore.getTranslatedText('Editor_Passive_Results_Label')"
              :empty-text="palStore.getTranslatedText('Editor_Passive_Empty')"
              :close-label="palStore.getTranslatedText('Common_Close')"
              :rating-label="palStore.getTranslatedText('Editor_Skill_Rating')"
              @select="palStore.SELECTED_PAL_DATA.add_PassiveSkillList($event.InternalName)"
            />
          </div>
        </header>
        <CustomPassiveDialog
          ref="customPassiveDialog"
          :disabled="palStore.LOADING_FLAG"
          @add="addCustomPassive"
        />
        <nav
          v-if="pinnedPassivePresets.length"
          class="passive-preset-quickbar"
          :aria-label="palStore.getTranslatedText('PalEditor_PassivePreset_QuickBar')"
        >
          <span class="passive-preset-quickbar__label">
            <AppIcon name="pin" :size="13" />
            {{ palStore.getTranslatedText('PalEditor_PassivePreset_QuickBar') }}
          </span>
          <button
            v-for="preset in pinnedPassivePresets"
            :key="preset.id"
            type="button"
            :class="['passive-preset-quick-action', { 'is-active': passivePresetIsActive(preset) }]"
            :disabled="palStore.LOADING_FLAG || !passivePresetIsAvailable(preset)"
            :aria-pressed="passivePresetIsActive(preset)"
            :title="passivePresetIsAvailable(preset)
              ? palStore.getTranslatedText('PalEditor_PassivePreset_QuickApplyNamed', [preset.name])
              : palStore.getTranslatedText('PalEditor_PassivePreset_Unavailable')"
            @click="applyPassivePreset(preset.skills)"
          >
            <span class="passive-preset-quick-action__label">{{ preset.name }}</span>
          </button>
        </nav>
        <PassivePresetDialog
          ref="passivePresetDialog"
          :options="palStore.PASSIVE_SKILLS_LIST"
          :disabled="palStore.LOADING_FLAG"
          @apply="applyPassivePreset"
          @change="updatePassivePresets"
        />
        <div class="skill-item-grid passive-skill-grid">
          <div
            v-for="(skill, index) in palStore.SELECTED_PAL_DATA.PassiveSkillList"
            :key="`${skill}-${index}`"
            class="skill-item passive-skill-item"
          >
            <div class="skill-item-row passive-skill-row">
              <PassiveSkillCard
                :skill="palStore.PASSIVE_SKILLS[skill]"
                :internal-name="skill"
                :unknown-label="palStore.getTranslatedText('PalEditor_CustomPassive_UnknownBadge')"
              />

              <button type="button" class="edit del skill-item-remove" @click="palStore.SELECTED_PAL_DATA.pop_PassiveSkillList(skill, index)" :name="skill"
              :disabled="palStore.LOADING_FLAG" :title="palStore.getTranslatedText('Common_Remove')"><AppIcon name="x" /></button>
            </div>
          </div>
        </div>
      </section>
      <section class="skill-section">
        <header class="skill-section-header">
          <h3>{{ palStore.getTranslatedText("Editor_Equipped_Skills") }}</h3>
          <PalSkillPicker
            v-model="palStore.PAL_ACTIVE_SELECTED_ITEM"
            kind="active"
            icon-only
            :options="equippableMasteredSkills"
            :selected-option="palStore.ACTIVE_SKILLS[palStore.PAL_ACTIVE_SELECTED_ITEM]"
            :disabled="palStore.LOADING_FLAG || (palStore.HIDE_INVALID_OPTIONS && palStore.SELECTED_PAL_DATA.isEquipSkillFull())"
            :show-internal-name="!palStore.HIDE_INVALID_OPTIONS"
            :placeholder="palStore.getTranslatedText('Editor_Equip_Active')"
            :title="palStore.getTranslatedText('Editor_Equip_Picker_Title')"
            :search-placeholder="palStore.getTranslatedText('Editor_Equip_Search_Placeholder')"
            :results-label="palStore.getTranslatedText('Editor_Active_Results_Label')"
            :empty-text="palStore.getTranslatedText('Editor_Equip_Empty')"
            :close-label="palStore.getTranslatedText('Common_Close')"
            :power-label="palStore.getTranslatedText('Editor_Skill_ATK').trim()"
            :cooldown-label="palStore.getTranslatedText('Editor_Skill_CD').trim()"
            :unique-label="palStore.getTranslatedText('Editor_Skill_Unique')"
            :fruit-label="palStore.getTranslatedText('Editor_Skill_Fruit')"
            @select="palStore.SELECTED_PAL_DATA.add_EquipWaza($event.InternalName)"
          />
        </header>
        <div class="skill-item-grid active-skill-grid">
          <div
            v-for="(skill, index) in palStore.SELECTED_PAL_DATA.EquipWaza"
            :key="`equipped-${skill}-${index}`"
            class="skill-item active-skill-item"
          >
            <div class="skill-item-row">
              <div class="active-skill-card tooltip-container" tabindex="0">
                <div class="active-skill-card__label">
                  <ElementIcon v-if="palStore.ACTIVE_SKILLS[skill]?.Element"
                    :element="palStore.ACTIVE_SKILLS[skill].Element" :size="16" />
                  <span>{{ palStore.ACTIVE_SKILLS[skill]?.I18n[0] || skill }}</span>
                </div>
                <article class="tooltip-text">
                  <h3>{{ palStore.ACTIVE_SKILLS[skill]?.I18n[0] || skill }}</h3>
                  <p>{{ palStore.ACTIVE_SKILLS[skill]?.I18n[1] || "" }}</p>
                  <p>
                    {{ palStore.getTranslatedText("Editor_Skill_ATK") }}
                    {{ palStore.ACTIVE_SKILLS[skill]?.Power }} |
                    {{ palStore.getTranslatedText("Editor_Skill_CD") }}
                    {{ palStore.ACTIVE_SKILLS[skill]?.CT }}
                  </p>
                  <p class="active-skill-element">
                    <strong>{{ palStore.getTranslatedText("Editor_Skill_EL").trim() }}</strong>
                    <ElementIcon v-if="palStore.ACTIVE_SKILLS[skill]?.Element"
                      :element="palStore.ACTIVE_SKILLS[skill].Element" :size="15" />
                  </p>
                  <p v-if="palStore.ACTIVE_SKILLS[skill]?.IsUniqueSkill || palStore.ACTIVE_SKILLS[skill]?.HasSkillFruit"
                    class="active-skill-tags">
                    <span v-if="palStore.ACTIVE_SKILLS[skill]?.IsUniqueSkill" class="active-skill-tag">{{ palStore.getTranslatedText('Editor_Skill_Unique') }}</span>
                    <span v-if="palStore.ACTIVE_SKILLS[skill]?.HasSkillFruit" class="active-skill-tag">{{ palStore.getTranslatedText('Editor_Skill_Fruit') }}</span>
                  </p>
                </article>
              </div>
              <button type="button" class="edit del skill-item-remove" @click="palStore.SELECTED_PAL_DATA.pop_EquipWaza" :name="skill"
                :disabled="palStore.LOADING_FLAG" :title="palStore.getTranslatedText('Common_Remove')"><AppIcon name="x" /></button>
            </div>
          </div>
        </div>
      </section>
      <section class="skill-section">
        <header class="skill-section-header">
          <h3>{{ palStore.getTranslatedText("Editor_Mastered_Skills") }}</h3>
          <PalSkillPicker
            v-model="palStore.PAL_ACTIVE_SELECTED_ITEM"
            kind="active"
            icon-only
            :options="filterInvalid(palStore.ACTIVE_SKILLS_LIST)"
            :selected-option="palStore.ACTIVE_SKILLS[palStore.PAL_ACTIVE_SELECTED_ITEM]"
            :disabled="palStore.LOADING_FLAG"
            :show-internal-name="!palStore.HIDE_INVALID_OPTIONS"
            :placeholder="palStore.getTranslatedText('Editor_Select_Active')"
            :title="palStore.getTranslatedText('Editor_Active_Picker_Title')"
            :search-placeholder="palStore.getTranslatedText('Editor_Active_Search_Placeholder')"
            :results-label="palStore.getTranslatedText('Editor_Active_Results_Label')"
            :empty-text="palStore.getTranslatedText('Editor_Active_Empty')"
            :close-label="palStore.getTranslatedText('Common_Close')"
            :power-label="palStore.getTranslatedText('Editor_Skill_ATK').trim()"
            :cooldown-label="palStore.getTranslatedText('Editor_Skill_CD').trim()"
            :unique-label="palStore.getTranslatedText('Editor_Skill_Unique')"
            :fruit-label="palStore.getTranslatedText('Editor_Skill_Fruit')"
            @select="palStore.SELECTED_PAL_DATA.add_MasteredWaza($event.InternalName)"
          />
        </header>
        <div class="skill-item-grid active-skill-grid">
          <div
            v-for="(skill, index) in palStore.SELECTED_PAL_DATA.MasteredWaza"
            :key="`mastered-${skill}-${index}`"
            class="skill-item active-skill-item"
          >
            <div class="skill-item-row">
              <div class="active-skill-card tooltip-container" tabindex="0">
                <div class="active-skill-card__label">
                  <ElementIcon v-if="palStore.ACTIVE_SKILLS[skill]?.Element"
                    :element="palStore.ACTIVE_SKILLS[skill].Element" :size="16" />
                  <span>{{ palStore.ACTIVE_SKILLS[skill]?.I18n[0] || skill }}</span>
                </div>
                <article class="tooltip-text">
                  <h3>{{ palStore.ACTIVE_SKILLS[skill]?.I18n[0] || skill }}</h3>
                  <p>{{ palStore.ACTIVE_SKILLS[skill]?.I18n[1] || "" }}</p>
                  <p>
                    {{ palStore.getTranslatedText("Editor_Skill_ATK") }}
                    {{ palStore.ACTIVE_SKILLS[skill]?.Power }} |
                    {{ palStore.getTranslatedText("Editor_Skill_CD") }}
                    {{ palStore.ACTIVE_SKILLS[skill]?.CT }}
                  </p>
                  <p class="active-skill-element">
                    <strong>{{ palStore.getTranslatedText("Editor_Skill_EL").trim() }}</strong>
                    <ElementIcon v-if="palStore.ACTIVE_SKILLS[skill]?.Element"
                      :element="palStore.ACTIVE_SKILLS[skill].Element" :size="15" />
                  </p>
                  <p v-if="palStore.ACTIVE_SKILLS[skill]?.IsUniqueSkill || palStore.ACTIVE_SKILLS[skill]?.HasSkillFruit"
                    class="active-skill-tags">
                    <span v-if="palStore.ACTIVE_SKILLS[skill]?.IsUniqueSkill" class="active-skill-tag">{{ palStore.getTranslatedText('Editor_Skill_Unique') }}</span>
                    <span v-if="palStore.ACTIVE_SKILLS[skill]?.HasSkillFruit" class="active-skill-tag">{{ palStore.getTranslatedText('Editor_Skill_Fruit') }}</span>
                  </p>
                </article>
              </div>
              <button type="button" class="edit del skill-item-remove" @click="palStore.SELECTED_PAL_DATA.pop_MasteredWaza" :name="skill"
                :disabled="palStore.LOADING_FLAG" :title="palStore.getTranslatedText('Common_Remove')"><AppIcon name="x" /></button>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.PalEditor {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(500px, 0.9fr);
  grid-template-rows: max-content minmax(min-content, 1fr);
  min-height: var(--sub-height);
  height: auto;
  overflow: visible;
  align-items: flex-start;
  align-content: flex-start;
  gap: 10px;
  background: var(--ui-canvas);
}

.PalEditor.unref {
  filter: grayscale(100%);
}

.EditorItem {
  display: flex;
  min-width: 0;
  background: var(--ui-surface);
  padding: 1.5rem;
  border-radius: var(--ui-radius-md);
}

/* .EditorItem .Basic-Info {} */

/* option.PassiveSkill{
  background-color: red;
} */

div.basicInfo {
  position: relative;
  grid-column: 1;
  width: 100%;
  min-width: 0;
  max-width: none;
  align-items: stretch;
}

.pal-summary {
  display: flex;
  width: 100%;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding-bottom: 14px;
  margin-bottom: 14px;
  border-bottom: 1px solid var(--ui-border);
}

.pal-identity {
  display: flex;
  min-width: 210px;
  align-items: center;
  gap: 12px;
}

.pal-summary__copy {
  display: grid;
  min-width: 0;
  align-items: start;
  gap: 2px;
}

.pal-summary__copy strong {
  overflow: hidden;
  color: var(--ui-text);
  font-size: 18px;
  font-weight: 680;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pal-summary__eyebrow {
  color: var(--ui-text-muted);
  font-size: 11px;
  font-weight: 600;
}

.pal-summary__species {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 4px;
  color: var(--ui-text-secondary);
  font-size: 12px;
}

div.statsPanel { grid-column: 2; width: 100%; }

div.palInfo {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  width: 100%;
  gap: 6px;
}

.metric {
  display: grid;
  min-width: 0;
  gap: 1px;
  padding: 8px 10px;
  background: var(--ui-surface-raised);
  border-radius: var(--ui-radius-sm);
}

.metric span {
  overflow: hidden;
  color: var(--ui-text-muted);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric strong {
  color: var(--ui-text);
  font-size: 14px;
  font-weight: 650;
}

div.skillPanel {
  grid-column: 1 / -1;
  width: 100%;
  min-height: 100%;
  max-width: none;
  align-self: stretch;
  flex-wrap: wrap;
}

div.skillList {
  display: flex;
  width: 100%;
  flex-wrap: wrap;
}

hr {
  border: 0;
  width: 100%;
  height: 2px;
  background-color: var(--ui-border);
  margin: 20px 0;
}

button {
  cursor: pointer;
}

p.cat {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

div {
  display: flex;
  align-items: center;
}

/* div.item {
  margin: .5rem;
} */

div.flex-v {
  flex-direction: column;
  gap: .2rem;
}

div.flex-h {
  flex-direction: row;
  gap: .5rem;
  min-width: 0;
}

div.left {
  justify-content: flex-start;
  align-items: flex-start;
}

p.const {
  display: flex;
  align-items: center;
  min-width: 0;
  min-height: 2rem;
  height: auto;
  margin: .2rem;
  padding: .2rem .4rem;
  border-radius: .5rem;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  box-shadow: none;
  white-space: nowrap;
}

p.const.skill-label {
  gap: 6px;
}

p.out_of_container {
  color: #3db15e !important;
}

.pal-summary__portrait {
  width: 64px;
  height: 64px;
  max-width: none;
  flex: 0 0 auto;
  align-self: auto;
  border-radius: 12px;
  box-shadow: var(--ui-shadow-sm);
  margin: 0;
  object-fit: contain;
}

img.suitIcon {
  display: block;
  width: 24px;
  height: 24px;
  align-self: center;
  margin: 0;
  padding: 0;
  object-fit: contain;
}

img.palIcon.unref {
  filter: grayscale(100%);
}

div.editField {
  /* border-style: dashed;
  border-width: 1px;
  border-color: white; */
  /* width: 100%; */
  /* flex-wrap: nowrap; */
  min-width: 0;
  gap: 6px;
}

button.edit {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  padding: 0rem;
  margin: 0rem;
  background-color: #848484;
  color: whitesmoke;
  border: none;
  outline: none;
  border-radius: 0.5rem;
  transition: all 0.15s ease-in-out;
}

button.edit:hover {
  background-color: #9c9c9c;
  box-shadow: 2px 2px 10px rgb(38, 38, 38);
  transition: all 0.15s ease-in-out;
}

button.edit:disabled {
  background-color: #8b8b8b;
  box-shadow: 0 0 0;
  filter: grayscale(100%);
  cursor: not-allowed;
}

button.text {
  width: 100%;
  background-color: #2c77c2;
  padding: 1rem .5rem;
  margin: .2rem;
}

button.text:hover {
  background-color: #18518a;
}

button.text:disabled {
  background-color: #8a8a8a;
  box-shadow: 0 0 0;
  filter: grayscale(100%);
  cursor: not-allowed;
}

button.edit_text {
  width: 5rem;
  background-color: #2c77c2;
  padding: 1rem .5rem;
  margin: .2rem;
}

button.edit_text:hover {
  background-color: #18518a;
}

button.edit_text:disabled {
  background-color: #8a8a8a;
  box-shadow: 0 0 0;
  filter: grayscale(100%);
  cursor: not-allowed;
}

button.del {
  background-color: #ffcece;
}

button.del:hover {
  background-color: #7c0f0f;
}

button.del:disabled {
  background-color: #8a8a8a;
  box-shadow: 0 0 0;
  filter: grayscale(100%);
  cursor: not-allowed;
}

button#dump_btn {
  position: absolute;
  top: 1rem;
  left: 1rem;

  display: flex;
  align-items: center;
  justify-content: center;
  height: 2rem;
  padding: 1rem;
  margin: 0rem;
  background-color: #636363;
  color: rgb(204, 204, 204);
  border: none;
  outline: none;
  border-radius: 0.5rem;
  transition: all 0.15s ease-in-out;
}

button#dump_btn:hover {
  background-color: #3e3e3e;
  box-shadow: 2px 2px 10px rgb(38, 38, 38);
  color: rgb(204, 204, 204);
}

button#dump_btn:disabled {
  background-color: #8a8a8a;
  box-shadow: 0 0 0;
  filter: grayscale(100%);
  cursor: not-allowed;
}

button#del_btn {
  position: absolute;
  top: 1rem;
  right: 1rem;

  display: flex;
  align-items: center;
  justify-content: center;
  height: 2rem;
  padding: 1rem;
  margin: 0rem;
  background-color: #bd1c3c;
  color: whitesmoke;
  border: none;
  outline: none;
  border-radius: 0.5rem;
  transition: all 0.15s ease-in-out;
}

button#del_btn:hover {
  background-color: #830e25;
  box-shadow: 2px 2px 10px rgb(38, 38, 38);
}

button#del_btn:disabled {
  background-color: #8a8a8a;
  box-shadow: 0 0 0;
  filter: grayscale(100%);
  cursor: not-allowed;
}

button#dupe_btn {
  position: absolute;
  top: 3.5rem;
  left: 1rem;

  display: flex;
  align-items: center;
  justify-content: center;
  height: 2rem;
  padding: 1rem;
  margin: 0rem;
  background-color: #1c8dbd;
  color: whitesmoke;
  border: none;
  outline: none;
  border-radius: 0.5rem;
  transition: all 0.15s ease-in-out;
}

button#dupe_btn:hover {
  background-color: #0e6b92;
  box-shadow: 2px 2px 10px rgb(38, 38, 38);
}

button#dupe_btn:disabled {
  background-color: #8a8a8a;
  box-shadow: 0 0 0;
  filter: grayscale(100%);
  cursor: not-allowed;
}

input.edit {
  height: 2rem;
  background-color: #6a6a6c;
  color: whitesmoke;
  border: none;
  outline: none;
  border-radius: 0.5rem;
  font-size: 13px;
  padding-left: 0.7rem;
  padding-right: 0.7rem;
}

input.edit:focus {
  background-color: #b8b8b8;
  color: black;
  /* border: 2px solid #6a6a6c; */
  box-shadow: 2px 2px 10px rgb(38, 38, 38);
}

input.edit::placeholder {
  color: #cccccca2
}

div.spaceBetween {
  display: flex;
  width: 100%;
  justify-content: space-between;
  gap: 20px;
}

.tooltip-container {
  position: relative;
  display: inline-block;
}

.tooltip-text {
  visibility: hidden;
  width: 200px;
  background-color: rgba(0, 0, 0, 0.85);
  color: white;
  text-align: center;
  border-radius: 6px;
  padding: 1rem;

  /* Position the tooltip */
  position: absolute;
  z-index: 1;
  bottom: 100%;
  left: 50%;
  margin-left: -60px;
  margin-bottom: .25rem;
}

.tooltip-container:hover .tooltip-text {
  visibility: visible;
}

select.selector {
  display: flex;
  align-items: center;
  min-width: 0;
  background-color: var(--ui-surface-raised);
  height: 1.8rem;
  margin: .2rem;
  padding: .2rem .4rem;
  border-radius: .5rem;
  color: var(--ui-text);
  box-shadow: none;
  /* max-width: 50%; */
}

.editor-card-actions {
  display: flex;
  width: auto;
  min-width: 0;
  min-height: 32px;
  flex: 1 1 auto;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}

.editor-card-actions > button {
  min-height: 32px;
  padding: 0 9px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font-size: 11px;
  font-weight: 550;
}

.editor-card-actions > button:hover:not(:disabled) {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
  border-color: var(--ui-border-strong);
}

.editor-card-actions > button.cancel-expedition {
  color: var(--ui-danger);
  border-color: color-mix(in srgb, var(--ui-danger) 35%, var(--ui-border));
}

.editor-card-actions .action-separator {
  width: 1px;
  height: 22px;
  margin: 0 2px;
  background: var(--ui-border);
}

.editor-card-actions #dump_btn,
.editor-card-actions #dupe_btn,
.editor-card-actions #del_btn {
  position: static;
  inset: auto;
  margin: 0;
}

.preset-file-input {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}

.clone-target {
  min-height: 32px;
  margin: 0;
  padding: 0 8px;
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
}

div.basic-fields {
  width: 100%;
  gap: 6px;
}

.basic-fields > .editField {
  display: grid;
  grid-template-columns: minmax(100px, auto) minmax(0, 1fr) 32px;
  width: 100%;
}

:global(#EditorMain .basic-fields > .identity-field) {
  grid-template-columns: 100px minmax(0, 1fr) 32px;
  min-height: 34px;
  align-items: center;
  gap: 6px;
}

:global(#EditorMain .identity-field > p.const),
:global(#EditorMain .identity-field > input.edit),
:global(#EditorMain .identity-field .pal-species-trigger) {
  min-height: 34px;
  height: 34px;
  margin: 0;
}

:global(#EditorMain .identity-field .pal-species-trigger) {
  padding-block: 0;
}

.basic-fields > .editField > p.const { margin-left: 0; }
.basic-fields > .editField > input,
.basic-fields > .editField > select { width: 100%; margin: 0; }

:global(#EditorMain .npc-weapon-field) {
  display: grid;
  grid-template-columns: 100px minmax(0, 1fr);
  min-height: 34px;
  align-items: center;
  gap: 6px;
}

:global(#EditorMain .npc-weapon-field > p.const) {
  min-height: 34px;
  height: 34px;
  margin: 0;
}

:global(#EditorMain .npc-weapon-value) {
  display: flex;
  align-items: center;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.attribute-row {
  width: 100%;
  align-items: stretch;
  flex-wrap: wrap;
  gap: 6px;
}

.attribute-row > .editField {
  display: flex;
  width: auto;
  min-width: 220px;
  flex: 1 1 240px;
}

.attribute-row > .editField > p.const { flex: 1 1 auto; }

:global(#EditorMain) button.edit.variant-toggle {
  width: auto;
  min-width: 58px;
  padding: 0 10px;
  color: var(--ui-text-secondary);
  font-size: 11px;
  font-weight: 720;
  letter-spacing: 0.025em;
}

:global(#EditorMain) button.edit.variant-toggle.is-active {
  color: oklch(0.16 0.025 252);
  background: var(--ui-accent);
  border-color: var(--ui-accent);
}

.metadata-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  width: 100%;
  gap: 6px 8px;
  padding-top: 6px;
}

.meta-field {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  width: 100%;
  align-items: center;
  gap: 8px;
}

.meta-field > span {
  color: var(--ui-text-muted);
  font-size: 12px;
}

.meta-field > strong {
  min-width: 0;
  overflow: hidden;
  color: var(--ui-text-secondary);
  font-size: 12px;
  font-weight: 550;
  font-variant-numeric: tabular-nums;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metadata-grid > .meta-field:last-child { grid-column: 1 / -1; }

.metadata-slot {
  display: flex;
  min-width: 0;
}

.metadata-slot .meta-field { flex: 1 1 auto; }

.statsPanel {
  position: relative;
  container-name: stats-panel;
  container-type: inline-size;
  display: flex;
  flex-direction: column;
  align-content: start;
}

.stat-primary-grid {
  display: grid;
  width: 100%;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr));
  align-items: start;
  gap: 0 18px;
}

:global(#EditorMain .PalEditor > .EditorItem.basicInfo),
:global(#EditorMain .PalEditor > .EditorItem.statsPanel) {
  align-self: stretch;
}

.stat-group {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.stat-group--iv > p.cat,
.stat-group--souls > p.cat { padding-right: 68px; }

.stat-group--souls {
  padding-left: 18px;
  border-left: 1px solid var(--ui-border);
}

.stat-group--condenser {
  width: 100%;
  padding-top: 14px;
  margin-top: 12px;
  border-top: 1px solid var(--ui-border);
}

.stat-group--condenser > p.cat { margin: 0; }

.stat-group--suitabilities {
  width: 100%;
  padding-top: 14px;
  margin-top: 12px;
  border-top: 1px solid var(--ui-border);
}

.estimated-group {
  display: flex;
  width: 100%;
  min-width: 0;
  flex-direction: column;
  padding-top: 14px;
  margin-top: 12px;
  border-top: 1px solid var(--ui-border);
}

.statsPanel .spaceBetween {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(120px, 46%);
  align-items: center;
  gap: 12px;
  min-height: 36px;
  padding-block: 0;
}

.statsPanel .spaceBetween > p.const {
  min-width: 0;
  padding-left: 0;
  background: transparent;
  white-space: normal;
}

.statsPanel input[type="range"] {
  width: 100%;
  min-width: 0;
}

@container stats-panel (max-width: 537px) {
  .stat-group--souls {
    padding: 14px 0 0;
    margin-top: 8px;
    border-top: 1px solid var(--ui-border);
    border-left: 0;
  }
}

.suitabilityPanel .skillList {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  width: 100%;
  align-items: center;
  gap: 8px 12px;
}

.suitabilityPanel {
  container-type: inline-size;
  gap: 10px;
}

.stat-group-header {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.stat-group-header > p.cat { margin: 0; }

.suitabilityPanel .skillList > div {
  display: grid;
  grid-template-columns: minmax(44px, 1fr) repeat(3, 32px);
  width: 100%;
  min-width: 0;
  align-items: center;
  gap: 4px;
}

.suitabilityPanel .skillList p.const {
  width: 100%;
  margin: 0;
  align-items: center;
  gap: 4px;
}

:global(#EditorMain button.edit.stats-max-all),
:global(#EditorMain button.edit.suitability-max-all) {
  width: auto;
  min-width: 54px;
  min-height: 32px;
  padding-inline: 10px;
  font-size: 11px;
  font-weight: 700;
}

:global(#EditorMain button.edit.stats-max-all) {
  position: absolute;
  z-index: 1;
  top: 18px;
  right: 18px;
}

.skill-section {
  container-name: skill-section;
  container-type: inline-size;
  display: flex;
  min-width: 0;
  height: 100%;
  flex-direction: column;
}

@container (max-width: 620px) {
  .suitabilityPanel .skillList {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@container (max-width: 420px) {
  .suitabilityPanel .skillList {
    grid-template-columns: minmax(0, 1fr);
  }
}

.skill-section-header {
  display: flex;
  min-height: 34px;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.skill-section-header h3 {
  min-width: 0;
  margin: 0;
  color: var(--ui-text);
  font-size: 13px;
  font-weight: 680;
  line-height: 1.35;
  text-wrap: balance;
}

.skill-section-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.passive-preset-trigger,
.custom-passive-trigger {
  min-height: 32px;
  margin: 0;
  padding: 0 10px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  font-size: 12px;
  font-weight: 650;
}

.passive-preset-trigger:hover:not(:disabled),
.custom-passive-trigger:hover:not(:disabled) {
  color: var(--ui-accent);
  background: var(--ui-accent-soft);
  border-color: var(--ui-accent);
}

.passive-preset-trigger:focus-visible,
.custom-passive-trigger:focus-visible {
  outline: 2px solid var(--ui-accent);
  outline-offset: 2px;
}

.passive-preset-trigger:disabled,
.custom-passive-trigger:disabled { cursor: not-allowed; opacity: 0.5; }

.custom-passive-trigger {
  color: var(--ui-danger);
  border-color: color-mix(in srgb, var(--ui-danger) 45%, var(--ui-border));
}

.passive-preset-quickbar {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 6px 8px;
  margin: -1px 0 9px;
  padding: 7px 8px;
  background: color-mix(in srgb, var(--ui-accent-soft) 42%, var(--ui-surface-raised));
  border: 1px solid color-mix(in srgb, var(--ui-accent) 24%, var(--ui-border));
  border-radius: 8px;
}

.passive-preset-quickbar__label {
  display: inline-flex;
  flex: 0 0 100%;
  align-items: center;
  gap: 4px;
  padding: 0 3px;
  color: var(--ui-text-muted);
  font-size: 10px;
  font-weight: 700;
}

.passive-preset-quick-action {
  display: inline-flex;
  width: fit-content;
  max-width: 100%;
  flex: 0 1 auto;
  min-width: 0;
  min-height: 32px;
  align-items: center;
  margin: 0;
  padding: 5px 10px;
  overflow: hidden;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  text-align: left;
  transition: color 160ms ease, background-color 160ms ease, border-color 160ms ease, transform 120ms ease;
}

.passive-preset-quick-action:hover:not(:disabled) { color: var(--ui-text); background: var(--ui-surface-hover); border-color: var(--ui-border-strong); }
.passive-preset-quick-action:active:not(:disabled) { transform: translateY(1px) scale(0.98); }
.passive-preset-quick-action:focus-visible { outline: 2px solid var(--ui-accent); outline-offset: 2px; }
.passive-preset-quick-action:disabled { cursor: not-allowed; opacity: 0.48; }
.passive-preset-quick-action.is-active { color: var(--ui-accent); background: var(--ui-accent-soft); border-color: var(--ui-accent); }

.passive-preset-quick-action__label { min-width: 0; overflow: hidden; font-size: 12px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }

.skill-item-grid {
  display: grid;
  width: 100%;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: 40px;
  align-content: start;
  gap: 6px 8px;
}

@container skill-section (max-width: 460px) {
  .skill-item-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

.skill-item {
  min-width: 0;
  height: 40px;
}

.skill-item-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 32px;
  align-items: center;
  width: 100%;
  height: 40px;
  min-width: 0;
  gap: 5px;
}

.active-skill-card {
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 40px;
  align-items: center;
  padding: 0 10px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border);
  border-radius: var(--ui-radius-sm);
  transition: background-color 160ms ease, border-color 160ms ease;
}

.active-skill-card:hover,
.active-skill-card:focus-visible {
  color: var(--ui-text);
  background: var(--ui-surface-hover);
  border-color: var(--ui-accent);
}

.active-skill-card__label {
  display: flex;
  width: 100%;
  min-width: 0;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  font-weight: 650;
}

.active-skill-card__label > span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-item-remove {
  align-self: center;
}

.skillsPanel .active-skill-card .tooltip-text {
  bottom: calc(100% + 8px);
  left: 0;
  width: min(360px, calc(100vw - 48px));
  margin: 0;
  padding: 10px 12px;
  color: var(--ui-text);
  text-align: left;
  white-space: pre-line;
  pointer-events: none;
  opacity: 0;
  transform: translateY(6px) scale(0.985);
  transform-origin: bottom left;
  transition: opacity 160ms cubic-bezier(0.25, 1, 0.5, 1), transform 160ms cubic-bezier(0.25, 1, 0.5, 1);
}

.skillsPanel .active-skill-card:hover .tooltip-text,
.skillsPanel .active-skill-card:focus-visible .tooltip-text {
  visibility: visible;
  opacity: 1;
  transform: translateY(0) scale(1);
}

.skillsPanel .active-skill-card .tooltip-text h3,
.skillsPanel .active-skill-card .tooltip-text p {
  margin: 0;
}

.skillsPanel .active-skill-card .tooltip-text {
  display: grid;
  gap: 6px;
}

.active-skill-element,
.active-skill-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.active-skill-element strong {
  font-weight: 650;
}

.active-skill-tag {
  padding: 1px 6px;
  color: var(--ui-text-secondary);
  background: var(--ui-surface-raised);
  border: 1px solid var(--ui-border-strong);
  border-radius: 5px;
  font-size: 10px;
  line-height: 1.4;
}

@media (max-width: 1500px) {
  .PalEditor {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: max-content max-content minmax(min-content, 1fr);
  }
  div.basicInfo,
  div.statsPanel,
  div.skillPanel { grid-column: 1; }
}

@media (max-width: 760px) {
  .pal-summary { flex-direction: column; }
  .editor-card-actions { justify-content: flex-start; }
  .metadata-grid,
  div.palInfo { grid-template-columns: minmax(0, 1fr); }
  .suitabilityPanel { grid-template-columns: minmax(0, 1fr); }
}
</style>
