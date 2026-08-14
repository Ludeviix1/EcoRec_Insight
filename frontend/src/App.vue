<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

interface NavItem {
  path: string
  title: string
  icon: string
}

const navItems: NavItem[] = [
  { path: '/dashboard', title: '仪表盘', icon: 'Odometer' },
  { path: '/users', title: '用户管理', icon: 'User' },
  { path: '/items', title: '商品管理', icon: 'Goods' },
  { path: '/analysis', title: '深度分析', icon: 'DataAnalysis' },
  { path: '/recommendations', title: '智能推荐', icon: 'MagicStick' },
  { path: '/models', title: '预测模型', icon: 'Cpu' },
]

const route = useRoute()
const router = useRouter()

const activePath = computed(() => {
  // 一级路径高亮：/users/123 归属 用户管理
  const seg = '/' + (route.path.split('/')[1] || 'dashboard')
  return seg
})

const currentTitle = computed(() => {
  const item = navItems.find((n) => n.path === activePath.value)
  return item?.title ?? '电商用户行为分析与智能推荐'
})

function go(path: string) {
  router.push(path)
}
</script>

<template>
  <div class="app-layout">
    <aside class="app-sidebar">
      <div class="app-sidebar__brand">
        <div class="app-sidebar__brand-mark">数</div>
        <div class="app-sidebar__brand-text">电商行为分析<br />与智能推荐平台</div>
      </div>
      <nav class="app-sidebar__menu">
        <div
          v-for="item in navItems"
          :key="item.path"
          class="nav-item"
          :class="{ 'is-active': activePath === item.path }"
          @click="go(item.path)"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </div>
      </nav>
    </aside>

    <div class="app-main">
      <header class="app-header">
        <div class="flex-center">
          <span class="app-header__title">{{ currentTitle }}</span>
        </div>
        <div class="flex-center gap-8 muted" style="font-size: 12.5px">
          <el-icon><Connection /></el-icon>
          <span>FastAPI · Vue3 · ECharts</span>
        </div>
      </header>

      <main class="app-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
