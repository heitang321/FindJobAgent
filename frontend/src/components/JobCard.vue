<template>
  <el-card
    class="job-card"
    :class="{ 'job-card--selected': selected }"
    shadow="hover"
    @click="$emit('select', job)"
  >
    <div class="job-card__header">
      <div class="job-card__title" :title="job.title">{{ job.title }}</div>
      <span class="job-card__salary">{{ job.salary }}</span>
    </div>
    <div class="job-card__skills">
      <el-tag
        v-for="skill in job.skills.slice(0, 6)"
        :key="skill"
        size="small"
        type="info"
        effect="plain"
      >
        {{ skill }}
      </el-tag>
      <el-tag v-if="job.skills.length > 6" size="small" type="info" effect="plain">
        +{{ job.skills.length - 6 }}
      </el-tag>
    </div>
    <div class="job-card__meta">
      <span class="job-card__meta-item">
        <el-icon><Location /></el-icon>
        {{ job.location || '地点不限' }}
      </span>
      <el-tag v-if="job.experience" size="small" type="warning" effect="plain">
        {{ job.experience }}
      </el-tag>
      <el-tag v-if="job.education" size="small" type="success" effect="plain">
        {{ job.education }}
      </el-tag>
    </div>
    <div class="job-card__company">
      <span class="job-card__company-name">{{ job.company }}</span>
      <el-tag
        v-for="tag in job.company_tags.slice(0, 3)"
        :key="tag"
        size="small"
        effect="plain"
      >
        {{ tag }}
      </el-tag>
    </div>
    <div class="job-card__action">
      <el-button
        :type="selected ? 'primary' : 'default'"
        size="small"
        :icon="selected ? Check : Position"
        @click.stop="$emit('select', job)"
      >
        {{ selected ? '已选择' : '选择此岗位' }}
      </el-button>
      <el-button
        tag="a"
        :href="job.url"
        target="_blank"
        type="primary"
        link
        size="small"
      >
        查看详情
      </el-button>
    </div>
  </el-card>
</template>

<script setup>
import { Location, Position, Check } from '@element-plus/icons-vue'

defineProps({
  job: {
    type: Object,
    required: true,
  },
  selected: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['select'])
</script>

<style scoped>
.job-card {
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 12px;
}
.job-card:hover {
  transform: translateY(-2px);
}
.job-card--selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-5);
}
.job-card__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 8px;
}
.job-card__title {
  font-weight: 600;
  font-size: 15px;
  color: var(--el-text-color-primary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.job-card__salary {
  color: var(--el-color-danger);
  font-weight: 600;
  white-space: nowrap;
}
.job-card__skills {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}
.job-card__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  color: var(--el-text-color-regular);
  font-size: 13px;
}
.job-card__meta-item {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.job-card__company {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}
.job-card__company-name {
  color: var(--el-text-color-regular);
  font-size: 13px;
}
.job-card__action {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
