<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useBranding } from '@/composables/useBranding'

import { SOURCE_CODE_LICENSE } from '../../app/publication'

const { t } = useI18n()
const { state, refresh } = useBranding()
const data = computed(() => (state.value.status === 'ready' ? state.value.data : null))
const legalEntity = computed(() => data.value?.legal_entity ?? null)
</script>

<template>
  <main class="legal app-page-frame app-page-frame--reading">
    <header class="legal-heading app-page-heading">
      <h1 class="legal-title app-page-heading__title">{{ t('legal.title') }}</h1>
    </header>

    <AppFeedback v-if="state.status === 'loading'" class="app-card" announcement="polite">
      {{ t('legal.loading') }}
    </AppFeedback>

    <AppFeedback
      v-else-if="state.status === 'error'"
      class="legal-error app-card"
      announcement="assertive"
      tone="critical"
    >
      {{ t('legal.loadError') }}
      <template #actions>
        <AppButton type="button" class="legal-retry" variant="ghost" @click="refresh">
          {{ t('legal.retry') }}
        </AppButton>
      </template>
    </AppFeedback>

    <div v-else class="legal-content app-card app-card--sectioned">
      <section class="legal-section" aria-labelledby="legal-provider-heading">
        <h2 id="legal-provider-heading">{{ t('legal.provider.heading') }}</h2>
        <p v-if="!legalEntity" class="legal-not-configured">{{ t('legal.notConfigured') }}</p>
        <template v-else>
          <p>{{ legalEntity.name }}</p>
          <p v-if="legalEntity.legal_form">{{ legalEntity.legal_form }}</p>
          <dl class="legal-facts app-fact-list">
            <div v-if="legalEntity.address_lines.length > 0" class="app-fact-list__item">
              <dt>{{ t('legal.provider.address') }}</dt>
              <dd>
                <address class="legal-address">
                  <span v-for="line in legalEntity.address_lines" :key="line">{{ line }}</span>
                </address>
              </dd>
            </div>
            <div v-if="legalEntity.telephone" class="app-fact-list__item">
              <dt>{{ t('legal.provider.telephone') }}</dt>
              <dd>
                <a v-if="legalEntity.telephone_href" :href="legalEntity.telephone_href">{{
                  legalEntity.telephone
                }}</a>
                <template v-else>{{ legalEntity.telephone }}</template>
              </dd>
            </div>
            <div v-if="legalEntity.representative" class="app-fact-list__item">
              <dt>{{ t('legal.provider.representative') }}</dt>
              <dd>{{ legalEntity.representative }}</dd>
            </div>
            <div v-if="legalEntity.vat_id" class="app-fact-list__item">
              <dt>{{ t('legal.provider.vatId') }}</dt>
              <dd>{{ legalEntity.vat_id }}</dd>
            </div>
          </dl>
        </template>
      </section>

      <section class="legal-section" aria-labelledby="legal-responsibility-heading">
        <h2 id="legal-responsibility-heading">{{ t('legal.responsibility.heading') }}</h2>
        <p v-if="data?.institution_name">
          {{ t('legal.responsibility.operator', { operator: data.institution_name }) }}
        </p>
        <p v-if="data?.contact_email">
          {{ t('legal.responsibility.contact') }}
          <a :href="`mailto:${data.contact_email}`">{{ data.contact_email }}</a>
        </p>
        <p v-if="!data?.institution_name && !data?.contact_email" class="legal-not-configured">
          {{ t('legal.notConfigured') }}
        </p>
      </section>

      <section class="legal-section" aria-labelledby="legal-copyright-heading">
        <h2 id="legal-copyright-heading">{{ t('legal.copyright.heading') }}</h2>
        <p>
          {{
            t('legal.copyright.sourceCode', {
              license: SOURCE_CODE_LICENSE.name,
              year: String(SOURCE_CODE_LICENSE.copyrightYear),
              holder: SOURCE_CODE_LICENSE.copyrightHolder,
            })
          }}
          <a :href="SOURCE_CODE_LICENSE.url">{{ t('legal.copyright.licenseText') }}</a>
        </p>
        <p>{{ t('legal.copyright.registerData') }}</p>
      </section>

      <section class="legal-section" aria-labelledby="legal-liability-heading">
        <h2 id="legal-liability-heading">{{ t('legal.liability.heading') }}</h2>
        <p>{{ t('legal.liability.content') }}</p>
        <p>{{ t('legal.liability.machineAnnotations') }}</p>
      </section>

      <section class="legal-section" aria-labelledby="legal-privacy-heading">
        <h2 id="legal-privacy-heading">{{ t('legal.privacy.heading') }}</h2>
        <p v-if="data?.privacy_notice_url">
          <a :href="data.privacy_notice_url">{{ t('legal.privacy.link') }}</a>
        </p>
        <p v-else class="legal-not-configured">{{ t('legal.notConfigured') }}</p>
      </section>
    </div>
  </main>
</template>

<style scoped>
.legal-section {
  padding: var(--space-4);
  border-bottom: 1px solid var(--grid);
}

.legal-section:last-child {
  border-bottom: 0;
}

.legal-section h2 {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-title);
}

.legal-section p {
  margin: 0 0 var(--space-2);
}

.legal-not-configured {
  color: var(--muted);
}

.legal-facts {
  margin-block-start: var(--space-3);
}

.legal-facts dt {
  color: var(--muted);
  font-size: var(--font-size-caption);
  line-height: var(--line-height-caption);
  text-transform: uppercase;
}

.legal-address {
  display: flex;
  flex-direction: column;
  font-style: normal;
}

.legal a {
  color: var(--accent);
  text-underline-offset: 0.2em;
}
</style>
