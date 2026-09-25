<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useBranding } from '@/composables/useBranding'
import { useSessionStore } from '@/stores/session'

import GuestHomeView from './GuestHomeView.vue'
import SignedInHomeView from './SignedInHomeView.vue'

const { t } = useI18n()
const session = useSessionStore()
const { state } = useBranding()
const data = computed(() => (state.value.status === 'ready' ? state.value.data : null))

// Anything short of a confirmed session (idle, loading, error, or ready-but-signed-out) gets the
// public guest content: it is harmless to show and avoids a loading flash for the common case of an
// anonymous first visit.
const isSignedIn = computed(() => session.status === 'ready' && session.isSignedIn)

// The BBAW guideline asks for a publication period; nothing is invented while it is unconfigured.
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
  <main class="home">
    <h1 class="home-title">{{ t('app.title') }}</h1>

    <SignedInHomeView v-if="isSignedIn" />
    <GuestHomeView v-else />

    <!-- The BBAW guideline requires title, editors, publisher and date on the start page. -->
    <section class="home-publication" aria-labelledby="publication-heading">
      <h2 id="publication-heading" class="home-publication-heading">
        {{ t('publication.heading') }}
      </h2>
      <p v-if="state.status === 'error'" class="home-publication-empty" role="alert">
        {{ t('publication.loadError') }}
      </p>
      <p v-else-if="!hasAnyPublicationFact" class="home-publication-empty">
        {{ t('publication.notConfigured') }}
      </p>
      <dl v-else class="home-publication-facts">
        <div v-if="data && data.editors.length > 0">
          <dt>{{ t('publication.editors') }}</dt>
          <dd>
            <ul class="home-publication-list">
              <li v-for="editor in data.editors" :key="editor">{{ editor }}</li>
            </ul>
          </dd>
        </div>
        <div v-if="data?.institution_name">
          <dt>{{ t('publication.publisher') }}</dt>
          <dd>{{ data.institution_name }}</dd>
        </div>
        <div v-if="data && data.initiatives.length > 0">
          <dt>{{ t('publication.initiatives') }}</dt>
          <dd>
            <ul class="home-publication-list">
              <li v-for="initiative in data.initiatives" :key="initiative.url">
                <a :href="initiative.url">{{ initiative.name }}</a>
              </li>
            </ul>
          </dd>
        </div>
        <div v-if="data?.published_since_year">
          <dt>{{ t('publication.published') }}</dt>
          <dd>
            {{ t('publication.publishedSince', { year: String(data.published_since_year) }) }}
          </dd>
        </div>
      </dl>
    </section>
  </main>
</template>

<style scoped>
.home {
  flex: 1;
  width: 100%;
  max-width: 40rem;
  margin: 0 auto;
  padding: var(--space-12) var(--space-4);
}

.home-title {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-page);
}

.home-publication {
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.home-publication-heading {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-title);
}

.home-publication-empty {
  margin: 0;
  color: var(--muted);
}

.home-publication-facts {
  display: grid;
  gap: var(--space-3);
  margin: 0;
}

.home-publication-facts dt {
  color: var(--muted);
  font-size: var(--font-size-caption);
  line-height: var(--line-height-caption);
  text-transform: uppercase;
}

.home-publication-facts dd {
  margin: 0;
}

.home-publication-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.home-publication a {
  color: var(--accent);
  text-underline-offset: 0.2em;
}
</style>
