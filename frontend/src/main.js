import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { vReveal } from './directives/reveal'
import './assets/main.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)

// 全局滚动动画指令
app.directive('reveal', vReveal)

app.mount('#app')
