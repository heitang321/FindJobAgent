/**
 * Scroll Reveal Directive
 *
 * 用法: <div v-reveal> 或 <div v-reveal="{ delay: 200 }">
 * 当元素进入视口时自动添加 .is-visible 类触发 CSS 动画。
 */
const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        const delay = entry.target.__revealDelay || 0
        setTimeout(() => {
          entry.target.classList.add('is-visible')
        }, delay)
        observer.unobserve(entry.target)
      }
    })
  },
  { threshold: 0.1, rootMargin: '0px 0px -60px 0px' },
)

export const vReveal = {
  mounted(el, binding) {
    el.classList.add('reveal')
    if (binding.value?.delay) {
      el.__revealDelay = binding.value.delay
    }
    requestAnimationFrame(() => {
      observer.observe(el)
    })
  },
  unmounted(el) {
    observer.unobserve(el)
  },
}
