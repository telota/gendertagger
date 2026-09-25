<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { useBranding } from '@/composables/useBranding'

import { SOURCE_CODE_LICENSE } from './publication'

const { t } = useI18n()
const { state } = useBranding()
const data = computed(() => (state.value.status === 'ready' ? state.value.data : null))
const hasAnyPublicationFact = computed(
  () =>
    !!data.value &&
    (data.value.editors.length > 0 ||
      !!data.value.institution_name ||
      data.value.initiatives.length > 0 ||
      data.value.published_since_year !== null),
)
</script>

<template>
  <footer class="app-footer">
    <div class="app-footer-inner">
      <section class="app-footer-publication" aria-labelledby="publication-heading">
        <h2 id="publication-heading" class="app-footer-heading">
          {{ t('publication.heading') }}
        </h2>
        <p v-if="state.status === 'error'" class="app-footer-branding-error" role="alert">
          {{ t('publication.loadError') }}
        </p>
        <p
          v-else-if="state.status === 'ready' && !hasAnyPublicationFact"
          class="app-footer-publication-empty"
        >
          {{ t('publication.notConfigured') }}
        </p>
        <dl v-else-if="hasAnyPublicationFact" class="app-footer-facts">
          <div v-if="data?.editors.length" class="app-footer-fact">
            <dt>{{ t('publication.editors') }}</dt>
            <dd>
              <ul class="app-footer-list">
                <li v-for="editor in data.editors" :key="editor">{{ editor }}</li>
              </ul>
            </dd>
          </div>
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
          <div v-if="data?.published_since_year" class="app-footer-fact">
            <dt>{{ t('publication.published') }}</dt>
            <dd>
              {{ t('publication.publishedSince', { year: String(data.published_since_year) }) }}
            </dd>
          </div>
        </dl>
      </section>
      <div class="app-footer-utilities">
        <dl class="app-footer-facts">
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
  display: grid;
  gap: var(--space-6);
  max-width: 72rem;
  margin: 0 auto;
  padding: var(--space-6) var(--space-4);
}

.app-footer-heading {
  margin: 0 0 var(--space-4);
  color: var(--text-primary);
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-body-strong);
}

.app-footer-publication-empty {
  margin: 0;
}

.app-footer-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4) var(--space-8);
  margin: 0;
}

.app-footer-publication .app-footer-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 12rem), 1fr));
}

.app-footer-fact {
  min-width: 0;
  overflow-wrap: anywhere;
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
  color: var(--critical-text);
}

.app-footer-publisher {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
}

.app-footer-publisher > a,
.app-footer-publisher > span {
  min-width: 0;
}

.app-footer-logo {
  display: block;
  flex-shrink: 0;
  max-height: 2.5rem;
  max-width: var(--space-12);
  width: auto;
}

.app-footer-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.app-footer-utilities {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: var(--space-4) var(--space-8);
  border-top: 1px solid var(--border);
  padding-top: var(--space-4);
}

.app-footer-utilities > .app-footer-facts {
  flex: 1 1 24rem;
  min-width: 0;
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
