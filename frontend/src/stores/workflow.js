import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  getOptimizationResult,
  getResumeAnalysis,
  submitJdUrl,
  triggerOptimization,
  uploadResume,
} from '@/api'

/**
 * 三 Agent 工作流 store。
 * 单页流水线中跨组件共享 taskId 与各阶段产出。
 *
 * 阶段流转：
 *   idle → uploading → analyzing（轮询 Agent1）
 *        → job_input（待用户提交 JD URL）
 *        → job_analyzing（同步等 Agent2）
 *        → optimizing（轮询 Agent3）
 *        → done / error
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

  // ===== Agent 2 产出 =====
  const jobRequirements = ref(null)
  const matchResult = ref(null)
  const gapReport = ref(null)

  // ===== Agent 3 产出 =====
  const optimizedResume = ref(null)
  const diffReport = ref(null)
  const optimizationSummary = ref(null)
  const downloadReady = ref(false)

  // ===== 轮询控制 =====
  let resumePollTimer = null
  let optimizePollTimer = null

  // ===== 计算属性 =====
  const matchScore = computed(() => matchResult.value?.overall_score ?? null)
  const isRunning = computed(() =>
    ['uploading', 'analyzing', 'job_analyzing', 'optimizing'].includes(stage.value),
  )

  // ===== 内部工具 =====
  function clearTimers() {
    if (resumePollTimer) {
      window.clearInterval(resumePollTimer)
      resumePollTimer = null
    }
    if (optimizePollTimer) {
      window.clearInterval(optimizePollTimer)
      optimizePollTimer = null
    }
  }

  function reset() {
    clearTimers()
    taskId.value = ''
    stage.value = 'idle'
    error.value = ''
    structuredResume.value = null
    resumeEvaluation.value = null
    jobRequirements.value = null
    matchResult.value = null
    gapReport.value = null
    optimizedResume.value = null
    diffReport.value = null
    optimizationSummary.value = null
    downloadReady.value = false
  }

  // ===== 步骤 1：上传简历 =====
  async function upload(file) {
    reset()
    stage.value = 'uploading'
    try {
      const data = await uploadResume(file)
      taskId.value = data.task_id
      stage.value = 'analyzing'
      startResumePolling()
      return data
    } catch (e) {
      stage.value = 'error'
      error.value = e.response?.data?.detail || e.message || '上传失败'
      throw e
    }
  }

  function startResumePolling() {
    clearTimers()
    resumePollTimer = window.setInterval(async () => {
      try {
        const data = await getResumeAnalysis(taskId.value)
        if (data.structured_resume) {
          structuredResume.value = data.structured_resume
          resumeEvaluation.value = data.evaluation || null
        }
        if (data.current_stage === 'done' || data.current_stage === 'error') {
          if (resumePollTimer) {
            window.clearInterval(resumePollTimer)
            resumePollTimer = null
          }
          if (data.error) {
            stage.value = 'error'
            error.value = data.error
          } else if (data.structured_resume) {
            stage.value = 'job_input'
          }
        }
      } catch (e) {
        if (resumePollTimer) {
          window.clearInterval(resumePollTimer)
          resumePollTimer = null
        }
        stage.value = 'error'
        error.value = e.response?.data?.detail || e.message || '轮询简历分析失败'
      }
    }, 1500)
  }

  // ===== 步骤 2：提交 JD URL =====
  async function submitJob(jdUrl) {
    if (!taskId.value) throw new Error('还没有上传简历')
    stage.value = 'job_analyzing'
    try {
      const data = await submitJdUrl(taskId.value, jdUrl)
      jobRequirements.value = data.job_requirements || null
      matchResult.value = data.match_result || null
      gapReport.value = data.gap_report || null
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

  return {
    // state
    taskId,
    stage,
    error,
    structuredResume,
    resumeEvaluation,
    jobRequirements,
    matchResult,
    gapReport,
    optimizedResume,
    diffReport,
    optimizationSummary,
    downloadReady,
    // computed
    matchScore,
    isRunning,
    // actions
    upload,
    submitJob,
    optimize,
    reset,
  }
})
