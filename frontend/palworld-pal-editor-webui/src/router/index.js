import { createRouter, createWebHashHistory } from 'vue-router'
import EntryView from '../views/EntryView.vue'
import EditorView from '../views/EditorView.vue'

const router = createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'Entry',
      component: EntryView
    },
    {
      path: '/editor',
      name: 'Editor',
      component: EditorView,
      meta: { requiresSession: true }
    },
    {
      path: '/editor/player/:playerId',
      name: 'PlayerEditor',
      component: EditorView,
      meta: { requiresSession: true }
    },
    {
      path: '/editor/player/:playerId/pal/:palId',
      name: 'PlayerPalEditor',
      component: EditorView,
      meta: { requiresSession: true }
    },
    {
      path: '/editor/base/:baseKey/pal/:palId',
      name: 'BasePalEditor',
      component: EditorView,
      meta: { requiresSession: true }
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/'
    }
  ]
})

export default router
