<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { useBranding } from '@/composables/useBranding'

import { SOURCE_CODE_LICENSE } from './publication'

const { t } = useI18n()
const { state } = useBranding()

// `null` while loading, on error, or once loaded with nothing configured: every row below is
// conditional on a field, so all three collapse to the same honest, minimal footer.
const data = computed(() => (state.value.status === 'ready' ? state.value.data : null))
</script>

<template>
  <footer class="app-footer">
    <div class="app-footer-inner">
      <p v-if="state.status === 'error'" class="app-footer-branding-error" role="alert">
        {{ t('footer.brandingUnavailable') }}
      </p>
      <dl class="app-footer-facts">
        <div v-if="data?.institution_name" class="app-footer-fact">
          <dt>{{ t('footer.publisher') }}</dt>
          <dd class="app-footer-publisher">
            <!-- Decorative: the publisher's name follows in text. -->
            <img v-if="data.logo_url" class="app-footer-logo" :src="data.logo_url" alt="" />
            <a v-if="data.institution_url" :href="data.institution_url">{{
              data.institution_name
            }}</a>
            <span v-else>{{ data.institution_name }}</span>
          </dd>
        </div>
        <div v-if="data?.initiatives.length" class="app-footer-fact">
          <dt>{{ t('footer.initiatives') }}</dt>
          <dd>
            <ul class="app-footer-list">
              <li v-for="initiative in data.initiatives" :key="initiative.url">
                <a :href="initiative.url">{{ initiative.name }}</a>
              </li>
            </ul>
          </dd>
        </div>
        <div v-if="data?.contact_email" class="app-footer-fact">
          <dt>{{ t('footer.contact') }}</dt>
          <dd>
            <a :href="`mailto:${data.contact_email}`">{{ data.contact_email }}</a>
          </dd>
        </div>
        <div class="app-footer-fact">
          <dt>{{ t('footer.license') }}</dt>
          <dd>
            <a :href="SOURCE_CODE_LICENSE.url">
              {{ t('footer.sourceCodeLicense', { license: SOURCE_CODE_LICENSE.name }) }}
            </a>
          </dd>
        </div>
      </dl>
      <nav :aria-label="t('footer.legalNavigation')">
        <ul class="app-footer-links">
          <li>
            <RouterLink :to="{ name: 'legalNotice' }">{{ t('footer.legalNotice') }}</RouterLink>
          </li>
          <li v-if="data?.privacy_notice_url">
            <a :href="data.privacy_notice_url">{{ t('footer.privacyNotice') }}</a>
          </li>
        </ul>
      </nav>
    </div>
  </footer>
</template>

<style scoped>
.app-footer {
  border-top: 1px solid var(--border);
  background: var(--panel);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  line-height: var(--line-height-small);
}

.app-footer-inner {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4) var(--space-8);
  justify-content: space-between;
  max-width: 72rem;
  margin: 0 auto;
  padding: var(--space-6) var(--space-4);
}

.app-footer-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4) var(--space-8);
  margin: 0;
}

.app-footer-fact dt {
  color: var(--muted);
  font-size: var(--font-size-caption);
  line-height: var(--line-height-caption);
  text-transform: uppercase;
}

.app-footer-fact dd {
  margin: 0;
}

.app-footer-branding-error {
  margin: 0;
  color: var(--critical);
}

.app-footer-publisher {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.app-footer-logo {
  display: block;
  max-height: 2.5rem;
  width: auto;
}

.app-footer-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.app-footer-links {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-6);
  margin: 0;
  padding: 0;
  list-style: none;
}

.app-footer a {
  color: var(--accent);
  text-underline-offset: 0.2em;
}
</style>
