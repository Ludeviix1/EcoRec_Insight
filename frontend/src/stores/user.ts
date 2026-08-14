import { ref } from 'vue'

/**
 * 跨页面共享的"当前选中用户"。
 * 用于从用户列表 / 详情跳转到推荐页时保持选中的用户。
 */
const selectedUserId = ref<string>('')

export function useUserStore() {
  function setUserId(id: string) {
    selectedUserId.value = id
  }
  function clear() {
    selectedUserId.value = ''
  }
  return { selectedUserId, setUserId, clear }
}
