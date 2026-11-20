<script lang="ts">
  import Cube from 'phosphor-svelte/lib/Cube'

  import { Badge } from '@/components/ui/badge'
  import type { AdminOverview } from '@/helpers/maintenanceApi'

  interface Props {
    overview: AdminOverview
  }

  let { overview }: Props = $props()
</script>

<div class="flex flex-col gap-5">
  <section
    class="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-4 sm:p-5"
  >
    <div class="flex items-start gap-2.5">
      <Cube
        class="mt-0.5 size-5 shrink-0 text-[var(--studio-accent)]"
        aria-hidden="true"
      />
      <div>
        <h2 class="title-3 font-semibold text-[var(--studio-text)]">
          Artefacto activo en inferencia CPU
        </h2>
        <p class="mt-0.5 text-xs text-[var(--studio-muted)]">
          Identidad criptográfica verificada en vivo contra el servicio interno FastAPI / PyTorch CPU.
        </p>
      </div>
    </div>

    <dl class="mt-4 grid grid-cols-1 gap-3 text-xs sm:grid-cols-2">
      <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
        <dt class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
          Checkpoint SHA-256
        </dt>
        <dd class="mt-1 break-all font-mono text-[11px] text-[var(--studio-text)]">
          {overview.live.inference_detail?.model_sha256 ?? 'No disponible'}
        </dd>
      </div>
      <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
        <dt class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
          Contrato SHA-256 / Versión
        </dt>
        <dd class="mt-1 break-all font-mono text-[11px] text-[var(--studio-text)]">
          v{overview.live.inference_detail?.contract_version ?? '—'} · {overview.live.inference_detail?.contract_sha256 ?? '—'}
        </dd>
      </div>
      <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
        <dt class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
          Umbral congelado / Tipo de score
        </dt>
        <dd class="mt-1 font-mono text-[11px] text-[var(--studio-text)]">
          {overview.live.inference_detail?.threshold?.toFixed(16) ?? '—'} · {overview.live.inference_detail?.score_type ?? '—'}
        </dd>
      </div>
      <div class="rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3">
        <dt class="font-mono text-[10px] text-[var(--studio-muted)] uppercase">
          Runtime PyTorch CPU
        </dt>
        <dd class="mt-1 font-mono text-[11px] text-[var(--studio-text)]">
          PyTorch {overview.live.inference_detail?.torch_version ?? '—'} · {overview.live.inference_detail?.torch_num_threads ?? '—'} hilos · carga {overview.live.inference_detail?.startup_load_ms?.toFixed(1) ?? '—'} ms
        </dd>
      </div>
    </dl>
  </section>

  <section
    class="rounded-xl border border-[var(--studio-border)] bg-[var(--studio-panel)] p-4 sm:p-5"
  >
    <h3 class="title-3 font-semibold text-[var(--studio-text)]">
      Bitácora de validaciones, activaciones y restauraciones
    </h3>
    <p class="mt-0.5 text-xs text-[var(--studio-muted)]">
      Registro auditable alimentado por <code>scripts/model_manager.py</code> durante ciclos controlados de actualización y rollback.
    </p>

    {#if overview.model_deployments.length === 0}
      <p class="mt-4 rounded-lg border border-[var(--studio-border)] bg-[var(--studio-bg)] p-3.5 text-xs text-[var(--studio-muted)]">
        Todavía no se registran eventos de despliegue en esta base de datos.
      </p>
    {:else}
      <div class="mt-4 overflow-x-auto">
        <table class="w-full min-w-[640px] border-collapse text-left text-xs">
          <thead>
            <tr class="border-b border-[var(--studio-border)] font-mono text-[10px] text-[var(--studio-muted)] uppercase">
              <th class="py-2 pr-3">Fecha</th>
              <th class="py-2 pr-3">Acción</th>
              <th class="py-2 pr-3">Paquete</th>
              <th class="py-2 pr-3">Estado</th>
              <th class="py-2 pr-3">SHA-256 (prefijo)</th>
              <th class="py-2">Motivo</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-[var(--studio-border)]/60 font-mono">
            {#each overview.model_deployments as dep (dep.id)}
              <tr>
                <td class="py-2 pr-3 text-[var(--studio-muted)]">
                  {dep.created_at}
                </td>
                <td class="py-2 pr-3 text-[var(--studio-text)]">
                  {dep.action}
                </td>
                <td class="py-2 pr-3 text-[var(--studio-text)]">
                  {dep.package_version}
                </td>
                <td class="py-2 pr-3">
                  <Badge
                    tone={dep.status === 'ok'
                      ? 'ok'
                      : dep.status === 'rolled_back'
                        ? 'target'
                        : 'error'}
                  >
                    {dep.status}
                  </Badge>
                </td>
                <td class="py-2 pr-3 text-[var(--studio-muted)]">
                  {dep.model_sha256 ? dep.model_sha256.slice(0, 12) : '—'}
                </td>
                <td class="py-2 font-sans text-[var(--studio-muted)]">
                  {dep.reason}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>
</div>
