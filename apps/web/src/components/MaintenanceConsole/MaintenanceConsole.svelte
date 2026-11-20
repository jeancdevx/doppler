<script lang="ts">
  import ArrowClockwise from 'phosphor-svelte/lib/ArrowClockwise'
  import LockKey from 'phosphor-svelte/lib/LockKey'
  import SignOut from 'phosphor-svelte/lib/SignOut'
  import Wrench from 'phosphor-svelte/lib/Wrench'
  import { Toaster, toast } from 'svelte-sonner'

  import { Badge } from '@/components/ui/badge'
  import { Button } from '@/components/ui/button'
  import { Skeleton } from '@/components/ui/skeleton'
  import type { FeedbackReviewStatus } from '@/helpers/api'
  import {
    type AdminFeedbackList,
    type AdminOverview,
    type DriftStatusResponse,
    evaluateAdminDrift,
    fetchAdminDrift,
    fetchAdminFeedback,
    fetchAdminOverview,
    setMaintenanceState,
    triggerAdminProbe,
    updateAdminFeedback
  } from '@/helpers/maintenanceApi'

  import DeploymentsPanel from './DeploymentsPanel.svelte'
  import DriftPanel from './DriftPanel.svelte'
  import FeedbackAdminPanel from './FeedbackAdminPanel.svelte'
  import OperationalPanel from './OperationalPanel.svelte'

  // Token mantenido exclusivamente en memoria (nunca localStorage, sessionStorage ni URL)
  let tokenInput = $state('')
  let adminToken = $state<string | null>(null)
  let authError = $state<string | null>(null)
  let authenticating = $state(false)

  let activeTab = $state<'ops' | 'drift' | 'feedback' | 'deployments'>('ops')
  let loading = $state(false)
  let probing = $state(false)
  let evaluatingDrift = $state(false)
  let togglingMaintenance = $state(false)

  let overview = $state.raw<AdminOverview | null>(null)
  let drift = $state.raw<DriftStatusResponse | null>(null)
  let feedbackData = $state.raw<AdminFeedbackList | null>(null)
  let feedbackStatusFilter = $state('')

  async function loadAll(token: string, filterStatus = feedbackStatusFilter) {
    loading = true

    try {
      const [ov, dr, fb] = await Promise.all([
        fetchAdminOverview(token, 30),
        fetchAdminDrift(token),
        fetchAdminFeedback(token, filterStatus || undefined)
      ])

      overview = ov
      drift = dr
      feedbackData = fb
    } finally {
      loading = false
    }
  }

  async function handleLogin(event: SubmitEvent) {
    event.preventDefault()
    const trimmed = tokenInput.trim()

    if (!trimmed) {
      authError = 'Ingresa el token administrativo configurado en el servidor.'

      return
    }

    authenticating = true
    authError = null

    try {
      await loadAll(trimmed)
      adminToken = trimmed
      tokenInput = ''
      toast.success('Sesión administrativa iniciada en memoria.')
    } catch (err) {
      adminToken = null
      overview = null
      drift = null
      feedbackData = null
      authError =
        err instanceof Error
          ? err.message
          : 'Token administrativo inválido o no autorizado.'
    } finally {
      authenticating = false
    }
  }

  function handleLogout() {
    adminToken = null
    tokenInput = ''
    overview = null
    drift = null
    feedbackData = null
    authError = null
    toast.info('Sesión administrativa cerrada.')
  }

  async function handleProbeNow() {
    if (!adminToken) {
      return
    }

    probing = true

    try {
      await triggerAdminProbe(adminToken)
      await loadAll(adminToken)
      toast.success('Sonda de dependencias ejecutada y registrada.')
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : 'No se pudo ejecutar la sonda.'
      )
    } finally {
      probing = false
    }
  }

  async function handleToggleMaintenance() {
    if (!adminToken || !overview) {
      return
    }

    const nextEnabled = !overview.live.maintenance_mode

    togglingMaintenance = true

    try {
      await setMaintenanceState(
        adminToken,
        nextEnabled,
        nextEnabled
          ? 'Modo mantenimiento activado desde consola administrativa.'
          : null
      )
      await loadAll(adminToken)
      toast.success(
        nextEnabled
          ? 'Modo mantenimiento activado (nuevas cargas devuelven HTTP 503).'
          : 'Modo mantenimiento desactivado.'
      )
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : 'No se pudo cambiar el modo mantenimiento.'
      )
    } finally {
      togglingMaintenance = false
    }
  }

  async function handleEvaluateDrift() {
    if (!adminToken) {
      return
    }

    evaluatingDrift = true

    try {
      await evaluateAdminDrift(adminToken, 30)
      drift = await fetchAdminDrift(adminToken)
      toast.success('Evaluación de drift ejecutada y almacenada.')
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : 'No se pudo evaluar drift.'
      )
    } finally {
      evaluatingDrift = false
    }
  }

  async function handleFilterFeedback(status: string) {
    feedbackStatusFilter = status

    if (!adminToken) {
      return
    }

    try {
      feedbackData = await fetchAdminFeedback(adminToken, status || undefined)
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : 'Error filtrando reportes.'
      )
    }
  }

  async function handleUpdateFeedback(
    reportId: string,
    payload: {
      review_status: FeedbackReviewStatus
      verified_label?: string | null
      resolution_note?: string | null
    }
  ) {
    if (!adminToken) {
      return
    }

    await updateAdminFeedback(adminToken, reportId, payload)
    feedbackData = await fetchAdminFeedback(
      adminToken,
      feedbackStatusFilter || undefined
    )
  }
</script>

<Toaster position="bottom-right" theme="dark" richColors />

<div
  data-studio-theme="dark"
  class="rounded-2xl border border-[var(--studio-border)] bg-[var(--studio-bg)] p-4 text-[var(--studio-text)] shadow-[0_24px_64px_-24px_rgba(9,15,29,0.55)] sm:p-6"
>
  {#if !adminToken}
    <div class="mx-auto max-w-md py-10">
      <div class="flex items-center gap-2.5">
        <div
          class="flex size-10 items-center justify-center rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] text-[var(--studio-accent)]"
        >
          <LockKey class="size-5" aria-hidden="true" />
        </div>
        <div>
          <h1 class="heading-4 text-[var(--studio-text)]">
            Consola de Monitoreo y Mantenimiento
          </h1>
          <p class="text-xs text-[var(--studio-muted)]">
            Acceso restringido mediante encabezado <code>X-Admin-Token</code>.
          </p>
        </div>
      </div>

      <form
        class="mt-6 flex flex-col gap-4 rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-5"
        onsubmit={e => void handleLogin(e)}
      >
        <div class="flex flex-col gap-1.5">
          <label
            for="doppler-admin-token"
            class="font-mono text-[11px] text-[var(--studio-muted)] uppercase"
          >
            Token administrativo local
          </label>
          <input
            id="doppler-admin-token"
            type="password"
            autocomplete="off"
            bind:value={tokenInput}
            placeholder="Ingresa ADMIN_API_TOKEN"
            class="min-h-[42px] rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] px-3 text-sm text-[var(--studio-text)] focus:border-[var(--studio-accent)]"
          />
        </div>

        {#if authError}
          <p
            role="alert"
            class="rounded-lg border border-[var(--badge-error-border)] bg-[var(--badge-error-bg)] px-3 py-2 text-xs text-[var(--badge-error-text)]"
          >
            {authError}
          </p>
        {/if}

        <p class="text-[11px] text-[var(--studio-muted)]">
          El token se conserva únicamente en la memoria de esta pestaña y nunca se guarda en almacenamiento local ni se expone en el bundle.
        </p>

        <Button type="submit" variant="primary" disabled={authenticating}>
          {authenticating ? 'Verificando…' : 'Ingresar a mantenimiento'}
        </Button>
      </form>
    </div>
  {:else}
    <!-- Cabecera operativa autenticada -->
    <div
      class="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--studio-border)] pb-4"
    >
      <div>
        <div class="flex flex-wrap items-center gap-2">
          <h1 class="heading-4 text-[var(--studio-text)]">
            Monitoreo, Drift y Mantenimiento
          </h1>
          {#if overview?.live.maintenance_mode}
            <Badge tone="target" dot>MODO MANTENIMIENTO ACTIVO</Badge>
          {/if}
        </div>
        <p class="mt-0.5 text-xs text-[var(--studio-muted)]">
          Validación local Linux Manjaro + Cloudflare R2 privado · Capítulo 10
        </p>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={togglingMaintenance || !overview}
          onclick={() => void handleToggleMaintenance()}
        >
          <Wrench class="size-4" aria-hidden="true" />
          <span>
            {overview?.live.maintenance_mode
              ? 'Desactivar mantenimiento'
              : 'Activar mantenimiento'}
          </span>
        </Button>
        <Button
          variant="subtle"
          size="sm"
          disabled={loading}
          onclick={() => adminToken && void loadAll(adminToken)}
        >
          <ArrowClockwise class="size-4" aria-hidden="true" />
          <span>Actualizar</span>
        </Button>
        <Button variant="outline" size="sm" onclick={handleLogout}>
          <SignOut class="size-4" aria-hidden="true" />
          <span>Salir</span>
        </Button>
      </div>
    </div>

    <!-- Pestañas de la consola -->
    <div
      class="mt-4 flex flex-wrap gap-1.5 rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-1.5"
      role="tablist"
      aria-label="Secciones de mantenimiento"
    >
      {#each [
        { id: 'ops', label: 'Operación y salud' },
        { id: 'drift', label: 'Detección de drift' },
        {
          id: 'feedback',
          label: `Retroalimentación (${feedbackData?.reports.length ?? 0})`
        },
        { id: 'deployments', label: 'Modelo y despliegues' }
      ] as tab (tab.id)}
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === tab.id}
          class={[
            'cursor-pointer rounded-lg px-3.5 py-2 text-xs font-medium transition-colors',
            activeTab === tab.id
              ? 'bg-[var(--studio-raised)] text-[var(--studio-text)]'
              : 'text-[var(--studio-muted)] hover:text-[var(--studio-text)]'
          ]}
          onclick={() => {
            activeTab = tab.id as typeof activeTab
          }}
        >
          {tab.label}
        </button>
      {/each}
    </div>

    <div class="mt-5">
      {#if loading && !overview}
        <div class="flex flex-col gap-4">
          <Skeleton class="h-32 w-full" />
          <Skeleton class="h-48 w-full" />
        </div>
      {:else if overview}
        {#if activeTab === 'ops'}
          <OperationalPanel
            {overview}
            {probing}
            onProbeNow={() => void handleProbeNow()}
          />
        {:else if activeTab === 'drift'}
          <DriftPanel
            {drift}
            evaluating={evaluatingDrift}
            onEvaluate={() => void handleEvaluateDrift()}
          />
        {:else if activeTab === 'feedback'}
          <FeedbackAdminPanel
            data={feedbackData}
            statusFilter={feedbackStatusFilter}
            onFilterChange={status => void handleFilterFeedback(status)}
            onUpdateReport={handleUpdateFeedback}
          />
        {:else}
          <DeploymentsPanel {overview} />
        {/if}
      {/if}
    </div>
  {/if}
</div>
