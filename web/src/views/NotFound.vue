<template>
  <div class="nf-wrap">
    <el-result icon="warning" title="404" sub-title="页面不存在或已被移除">
      <template #extra>
        <el-button type="primary" @click="router.push('/dashboard')">返回概览</el-button>
      </template>
    </el-result>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
const router = useRouter()
</script>

<style scoped>
.nf-wrap { display: flex; align-items: center; justify-content: center; min-height: 60vh; }
</style>
