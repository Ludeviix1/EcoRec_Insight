<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import { itemsApi } from '@/api'
import { fmtInt, fmtMoney, fmtDate, fmtPct } from '@/utils/format'
import type { ItemRow, RankingCategory } from '@/types'

const router = useRouter()
const loading = ref(false)
const items = ref<ItemRow[]>([])
const total = ref(0)
const keyword = ref('')
const categoryId = ref('')
const status = ref<'' | 0 | 1>('')
const sortBy = ref<'' | 'brand' | 'price' | 'stock'>('')
const sortOrder = ref<'asc' | 'desc'>('asc')
const categories = ref<RankingCategory[]>([])
const page = ref(1)
const pageSize = ref(20)

async function loadCategories() {
  try {
    const rk = await itemsApi.ranking(100)
    categories.value = rk.categories
  } catch {
    /* 忽略 */
  }
}

async function load() {
  loading.value = true
  try {
    const res = await itemsApi.list({
      keyword: keyword.value || undefined,
      category_id: categoryId.value || undefined,
      status: status.value === '' ? undefined : status.value,
      sort_by: sortBy.value || undefined,
      order: sortOrder.value,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    })
    items.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

function onSearch() {
  page.value = 1
  load()
}
function onSortByChange() {
  sortOrder.value = 'asc'
  onSearch()
}
function toggleOrder() {
  sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  onSearch()
}
function onPageChange(p: number) {
  page.value = p
  load()
}
function goDetail(row: ItemRow) {
  router.push(`/items/${row.item_id}`)
}

onMounted(() => {
  loadCategories()
  load()
})
</script>

<template>
  <div>
    <PageHeader title="商品管理" desc="浏览与检索商品，查看商品画像与热度统计">
      <el-input v-model="keyword" placeholder="搜索商品 ID / 名称" clearable style="width: 200px" @keyup.enter="onSearch" @clear="onSearch">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="categoryId" placeholder="分类" clearable filterable style="width: 160px" @change="onSearch">
        <el-option v-for="c in categories" :key="c.category_id" :label="c.category_name || c.category_id" :value="c.category_id" />
      </el-select>
      <el-select v-model="status" placeholder="状态" clearable style="width: 110px" @change="onSearch">
        <el-option label="上架" :value="1" />
        <el-option label="下架" :value="0" />
      </el-select>
      <el-select v-model="sortBy" placeholder="排序字段" clearable style="width: 120px" @change="onSortByChange">
        <el-option label="品牌" value="brand" />
        <el-option label="价格" value="price" />
        <el-option label="库存" value="stock" />
      </el-select>
      <el-button :disabled="!sortBy" @click="toggleOrder">
        {{ sortOrder === 'asc' ? '升序 ↑' : '降序 ↓' }}
      </el-button>
      <el-button type="primary" @click="onSearch">搜索</el-button>
    </PageHeader>

    <div class="card card-pad">
      <el-table v-loading="loading" :data="items" size="default" stripe highlight-current-row @row-click="goDetail" style="cursor: pointer">
        <el-table-column prop="item_id" label="商品 ID" width="130" />
        <el-table-column prop="item_name" label="商品名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="category_name" label="分类" width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.category_name || row.category_id }}</template>
        </el-table-column>
        <el-table-column prop="brand" label="品牌" width="110" show-overflow-tooltip />
        <el-table-column label="价格" width="110" align="right">
          <template #default="{ row }">{{ fmtMoney(row.price) }}</template>
        </el-table-column>
        <el-table-column label="库存" width="90" align="right">
          <template #default="{ row }">{{ fmtInt(row.stock) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="(row.status === 1 ? 'success' : 'info') as any" size="small" effect="light">{{ row.status === 1 ? '上架' : '下架' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click.stop="goDetail(row)">查看画像</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="暂无商品数据" /></template>
      </el-table>

      <div class="flex-between mt-16">
        <span class="muted" style="font-size: 12.5px">共 {{ total }} 件商品</span>
        <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next, jumper" background @current-change="onPageChange" />
      </div>
    </div>
  </div>
</template>
