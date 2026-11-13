import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from './pages/Dashboard.vue'
import Jobs from './pages/Jobs.vue'
import Orchestrate from './pages/Orchestrate.vue'
import Attempts from './pages/Attempts.vue'
import Watermarks from './pages/Watermarks.vue'
import Settings from './pages/Settings.vue'
import Ledger from './pages/Ledger.vue'
import Quota from './pages/Quota.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Dashboard },
    { path: '/jobs', component: Jobs },
    { path: '/orchestrate', component: Orchestrate },
    { path: '/attempts', component: Attempts },
    { path: '/ledger', component: Ledger },
    { path: '/quota', component: Quota },
    { path: '/watermarks', component: Watermarks },
    { path: '/settings', component: Settings },
  ],
})
