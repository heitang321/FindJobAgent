import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  getOptimizationResult,
  getResumeAnalysis,
  searchJobs as searchJobsApi,
  submitJdUrl,
  triggerOptimization,
  uploadResume,
} from '@/api'

/**
 * 三 Agent 工作流 store。
 * 单页流水线中跨组件共享 taskId 与各阶段产出。
 *
 * 阶段流转：
 *   idle → uploading → job_input（待用户提交 JD URL 或自动推荐岗位）
 *        → job_analyzing（同步等 Agent2）
 *        → optimizing（轮询 Agent3，生成三个版本）
 *        → done / error
 *
 * job_input 阶段有两个入口：
 *   1. 手动：用户粘贴 JD URL → submitJob(jdUrl)
 *   2. 自动：用户点"自动推荐" → searchJobs() → 展示卡片列表 → selectJobCard(card)
 *           → 自动填入 card.url 到 jdUrl → submitJob
 */
export const useWorkflowStore = defineStore('workflow', () => {
  // ===== 任务标识 =====
  const taskId = ref('')

  // ===== 阶段状态 =====
  const stage = ref('idle') // idle|uploading|analyzing|job_input|job_analyzing|optimizing|done|error
  const error = ref('')

  // ===== Agent 1 产出 =====
  const structuredResume = ref(null)
  const resumeEvaluation = ref(null)

  // ===== 岗位搜索（job_input 阶段的自动推荐分支）=====
  const jobSearchResults = ref([]) // 当前页卡片列表
  const searchKeywords = ref('') // 实际使用的搜索关键词
  const searchingJobs = ref(false) // 是否正在搜索
  const selectedJobCard = ref(null) // 用户选中的卡片对象

  // 筛选+分页状态
  const searchTotal = ref(0) // 筛选后总数
  const searchPage = ref(1) // 当前页码
  const searchPageSize = ref(10) // 每页条数
  const searchTotalPages = ref(1) // 总页数
  const searchFilterCity = ref('')
  const searchFilterExperience = ref('')
  const searchFilterEducation = ref('')
  const searchFilterKeyword = ref('')

  // ===== Agent 2 产出 =====
  const jobRequirements = ref(null)
  const matchResult = ref(null)
  const gapReport = ref(null)

  // ===== Agent 3 产出 =====
  const optimizedResume = ref(null)
  const diffReport = ref(null)
  const optimizationSummary = ref(null)
  const downloadReady = ref(false)

  // ===== 多版本优化 =====
  const optimizationVersions = ref([]) // [{strategy, label, description, optimized_resume, diff_report, optimization_summary, download_ready}]
  const selectedVersion = ref('balanced') // 当前查看的版本 tab

  // ===== 轮询控制 =====
  let optimizePollTimer = null

  // ===== 计算属性 =====
  const matchScore = computed(() => matchResult.value?.overall_score ?? null)
  const isRunning = computed(() =>
    ['uploading', 'analyzing', 'job_analyzing', 'optimizing'].includes(stage.value),
  )
  const hasSearchResults = computed(() => jobSearchResults.value.length > 0)

  // 当前选中版本的 diff report
  const currentVersionDiff = computed(() => {
    if (!optimizationVersions.value.length) return diffReport.value
    const v = optimizationVersions.value.find((v) => v.strategy === selectedVersion.value)
    return v?.diff_report || null
  })

  // 当前选中版本的 summary
  const currentVersionSummary = computed(() => {
    if (!optimizationVersions.value.length) return optimizationSummary.value
    const v = optimizationVersions.value.find((v) => v.strategy === selectedVersion.value)
    return v?.optimization_summary || null
  })

  // 当前选中版本是否可下载
  const currentVersionDownloadReady = computed(() => {
    if (!optimizationVersions.value.length) return downloadReady.value
    const v = optimizationVersions.value.find((v) => v.strategy === selectedVersion.value)
    return v?.download_ready || false
  })

  // 当前选中版本的错误信息
  const currentVersionError = computed(() => {
    if (!optimizationVersions.value.length) return ''
    const v = optimizationVersions.value.find((v) => v.strategy === selectedVersion.value)
    return v?.error || ''
  })

  // ===== 内部工具 =====
  function clearTimers() {
    if (optimizePollTimer) {
      window.clearInterval(optimizePollTimer)
      optimizePollTimer = null
    }
  }

  async function syncResumeAnalysis() {
    const data = await getResumeAnalysis(taskId.value)
    if (Object.keys(data.structured_resume || {}).length) {
      structuredResume.value = data.structured_resume
      resumeEvaluation.value = data.evaluation || null
    }
    if (Array.isArray(data.job_search_results)) {
      jobSearchResults.value = data.job_search_results
    }
    return data
  }

  function reset() {
    clearTimers()
    taskId.value = ''
    stage.value = 'idle'
    error.value = ''
    structuredResume.value = null
    resumeEvaluation.value = null
    jobSearchResults.value = []
    searchKeywords.value = ''
    searchingJobs.value = false
    selectedJobCard.value = null
    jobRequirements.value = null
    matchResult.value = null
    gapReport.value = null
    optimizedResume.value = null
    diffReport.value = null
    optimizationSummary.value = null
    downloadReady.value = false
    optimizationVersions.value = []
    selectedVersion.value = 'balanced'
  }

  // ===== 步骤 1：上传简历 =====
  async function upload(file) {
    reset()
    stage.value = 'uploading'
    try {
      const data = await uploadResume(file)
      taskId.value = data.task_id
      // 关键优化：立即进入 job_input 阶段，让用户可以输入 JD URL
      // 不再等 A1 完成 —— 后端编排函数会并行跑 A1 和 A2 前 3 步
      stage.value = 'job_input'
      return data
    } catch (e) {
      stage.value = 'error'
      error.value = e.response?.data?.detail || e.message || '上传失败'
      throw e
    }
  }

  // ===== 步骤 2a：自动推荐岗位（job_input 阶段的一个入口）=====
  async function searchJobs(params = {}) {
    if (!taskId.value) throw new Error('还没有上传简历')
    searchingJobs.value = true
    error.value = ''
    try {
      const data = await searchJobsApi(taskId.value, {
        keywords: params.keywords || '',
        city: params.city || '',
        filterCity: params.filterCity ?? searchFilterCity.value,
        filterExperience: params.filterExperience ?? searchFilterExperience.value,
        filterEducation: params.filterEducation ?? searchFilterEducation.value,
        filterKeyword: params.filterKeyword ?? searchFilterKeyword.value,
        page: params.page ?? searchPage.value,
        pageSize: params.pageSize ?? searchPageSize.value,
      })
      jobSearchResults.value = data.job_search_results || []
      searchKeywords.value = data.keywords || ''
      searchTotal.value = data.total || 0
      searchPage.value = data.page || 1
      searchPageSize.value = data.page_size || 10
      searchTotalPages.value = data.total_pages || 1
      selectedJobCard.value = null
      await syncResumeAnalysis()
      return data
    } catch (e) {
      error.value = e.response?.data?.detail || e.message || '岗位检索失败'
      throw e
    } finally {
      searchingJobs.value = false
    }
  }

  // 重置筛选条件
  function resetSearchFilters() {
    searchFilterCity.value = ''
    searchFilterExperience.value = ''
    searchFilterEducation.value = ''
    searchFilterKeyword.value = ''
    searchPage.value = 1
  }

  // 选中一个岗位卡片：自动填 URL，进入提交分析流程
  function selectJobCard(card) {
    selectedJobCard.value = card
    // 不自动提交 —— 让用户确认后再调 submitJob
    return card
  }

  // ===== 步骤 2b：提交 JD URL（手动 URL 或自动推荐选中的卡片都走这里）=====
  async function submitJob(jdUrl) {
    if (!taskId.value) throw new Error('还没有上传简历')
    stage.value = 'job_analyzing'
    try {
      const data = await submitJdUrl(taskId.value, jdUrl)
      jobRequirements.value = data.job_requirements || null
      matchResult.value = data.match_result || null
      gapReport.value = data.gap_report || null
      await syncResumeAnalysis()
      stage.value = 'ready_to_optimize'
    } catch (e) {
      stage.value = 'error'
      error.value = e.response?.data?.detail || e.message || '岗位分析失败'
      throw e
    }
  }

  // ===== 步骤 3：触发优化 =====
  async function optimize() {
    if (!taskId.value) throw new Error('还没有上传简历')
    error.value = ''
    optimizedResume.value = null
    diffReport.value = null
    optimizationSummary.value = null
    downloadReady.value = false
    optimizationVersions.value = []
    selectedVersion.value = 'balanced'
    stage.value = 'optimizing'
    try {
      await triggerOptimization(taskId.value)
      startOptimizePolling()
    } catch (e) {
      stage.value = 'error'
      error.value = e.response?.data?.detail || e.message || '触发优化失败'
      throw e
    }
  }

  function startOptimizePolling() {
    clearTimers()
    optimizePollTimer = window.setInterval(async () => {
      try {
        const data = await getOptimizationResult(taskId.value)
        const sections = data.diff_report?.sections
        optimizedResume.value = Object.keys(data.optimized_resume || {}).length
          ? data.optimized_resume
          : null
        diffReport.value = Array.isArray(sections) && sections.length
          ? data.diff_report
          : null
        optimizationSummary.value = Object.keys(data.optimization_summary || {}).length
          ? data.optimization_summary
          : null
        downloadReady.value = Boolean(data.download_ready)
        optimizationVersions.value = data.optimization_versions || []

        if (data.current_stage !== 'optimizing') {
          if (optimizePollTimer) {
            window.clearInterval(optimizePollTimer)
            optimizePollTimer = null
          }
          if (data.current_stage === 'error' || data.error) {
            stage.value = 'error'
            error.value = data.error || '简历优化失败'
          } else if (data.current_stage === 'done') {
            stage.value = 'done'
            error.value = ''
          } else {
            stage.value = 'error'
            error.value = `未知的优化任务状态：${data.current_stage || '空'}`
          }
        }
      } catch (e) {
        if (optimizePollTimer) {
          window.clearInterval(optimizePollTimer)
          optimizePollTimer = null
        }
        stage.value = 'error'
        error.value = e.response?.data?.detail || e.message || '轮询优化结果失败'
      }
    }, 1500)
  }

  // 切换查看的版本
  function selectVersion(strategy) {
    selectedVersion.value = strategy
  }

  return {
    // state
    taskId,
    stage,
    error,
    structuredResume,
    resumeEvaluation,
    jobSearchResults,
    searchKeywords,
    searchingJobs,
    selectedJobCard,
    jobRequirements,
    matchResult,
    gapReport,
    optimizedResume,
    diffReport,
    optimizationSummary,
    downloadReady,
    optimizationVersions,
    selectedVersion,
    // computed
    matchScore,
    isRunning,
    hasSearchResults,
    // 筛选+分页
    searchTotal,
    searchPage,
    searchPageSize,
    searchTotalPages,
    searchFilterCity,
    searchFilterCity,
    searchFilterExperience,
    searchFilterEducation,
    searchFilterKeyword,
    resetSearchFilters,
    currentVersionDiff,
    currentVersionSummary,
    currentVersionDownloadReady,
    currentVersionError,
    // actions
    upload,
    searchJobs,
    selectJobCard,
    submitJob,
    optimize,
    reset,
    selectVersion,
  }
})
