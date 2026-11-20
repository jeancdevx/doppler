<script lang="ts">
  import { AlertDialog } from 'bits-ui'

  import { Button } from '@/components/ui/button'

  interface Props {
    open: boolean
    filename: string
    busy?: boolean
    onConfirm: () => void
    onCancel: () => void
  }

  let {
    open = $bindable(false),
    filename,
    busy = false,
    onConfirm,
    onCancel
  }: Props = $props()
</script>

<AlertDialog.Root bind:open>
  <AlertDialog.Portal>
    <AlertDialog.Overlay
      class="fixed inset-0 z-50 bg-[#090f1d]/75 backdrop-blur-xs"
    />
    <AlertDialog.Content
      class="fixed top-1/2 left-1/2 z-50 w-[min(92vw,440px)] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-[#34435c] bg-[#101b30] p-6 text-[#f5f3ec] shadow-2xl"
    >
      <AlertDialog.Title class="heading-4 text-[#f5f3ec]">
        Eliminar archivo y resultados
      </AlertDialog.Title>
      <AlertDialog.Description class="body-6 mt-2 text-[#bdc4d1]">
        Se eliminarán de forma permanente el audio WAV almacenado en Cloudflare
        R2 y las ventanas calculadas en SQLite para
        <span class="font-mono text-[#f5f3ec] break-all">{filename}</span>. Esta
        acción no se puede deshacer.
      </AlertDialog.Description>
      <div class="mt-6 flex flex-wrap justify-end gap-3">
        <AlertDialog.Cancel>
          {#snippet child({ props })}
            <Button
              {...props}
              variant="outline"
              size="sm"
              disabled={busy}
              onclick={onCancel}
            >
              Cancelar
            </Button>
          {/snippet}
        </AlertDialog.Cancel>
        <Button variant="danger" size="sm" disabled={busy} onclick={onConfirm}>
          {busy ? 'Eliminando…' : 'Eliminar permanentemente'}
        </Button>
      </div>
    </AlertDialog.Content>
  </AlertDialog.Portal>
</AlertDialog.Root>
