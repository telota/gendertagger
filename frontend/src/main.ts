import { createApplication } from '@/app/bootstrap'
import '@/styles/index.css'

createApplication({
  storage: window.localStorage,
  languages: navigator.languages,
  root: document.documentElement,
}).mount('#app')
