import { createRouter, createWebHashHistory } from 'vue-router'
import EntryView from '../views/EntryView.vue'
import OverviewView from '../views/OverviewView.vue'
import EditorView from '../views/EditorView.vue'
import ArenaLeaderboardView from '../views/ArenaLeaderboardView.vue'
import RemoteServerView from '../views/RemoteServerView.vue'

const router = createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'Entry',
      component: EntryView
    },
    {
      path: '/remote',
      name: 'RemoteServer',
      component: RemoteServerView,
      meta: { requiresRemoteSession: true }
    },
    {
      path: '/editor',
      name: 'Editor',
      component: EditorView,
      meta: { requiresSession: true, editorMode: 'pal' }
    },
    {
      path: '/players',
      name: 'Players',
      component: EditorView,
      meta: { requiresSession: true, editorMode: 'player' }
    },
    {
      path: '/guilds',
      name: 'Guilds',
      component: () => import('../views/GuildView.vue'),
      meta: { requiresSession: true }
    },
    {
      path: '/overview',
      name: 'Overview',
      component: OverviewView,
      meta: { requiresSession: true }
    },
    {
      path: '/editor/player/:playerId',
      name: 'PlayerEditor',
      component: EditorView,
      meta: { requiresSession: true, editorMode: 'player' }
    },
    {
      path: '/editor/player/:playerId/pal/:palId',
      name: 'PlayerPalEditor',
      component: EditorView,
      meta: { requiresSession: true, editorMode: 'pal' }
    },
    {
      path: '/editor/base/:baseKey/pal/:palId',
      name: 'BasePalEditor',
      component: EditorView,
      meta: { requiresSession: true, editorMode: 'pal' }
    },
    {
      path: '/editor/base/:baseKey',
      name: 'BaseEditor',
      component: EditorView,
      meta: { requiresSession: true, editorMode: 'pal' }
    },
    {
      path: '/arena',
      name: 'ArenaLeaderboard',
      component: ArenaLeaderboardView,
      meta: { requiresSession: true }
    },
    {
      path: '/map',
      name: 'Map',
      component: () => import('../views/MapView.vue'),
      meta: { requiresSession: true }
    },
    {
      path: '/expeditions',
      name: 'Expeditions',
      component: () => import('../views/ExpeditionView.vue'),
      meta: { requiresSession: true }
    },
    {
      path: '/json-editor',
      name: 'JsonEditor',
      component: () => import('../views/JsonEditorView.vue'),
      meta: { requiresSession: true }
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/'
    }
  ]
})

export default router
