<script lang="ts">
  import { Progress as BitsProgress } from 'bits-ui'

  import { cn } from '@/helpers/cn'

  interface Props {
    value: number
    max?: number
    label?: string
    class?: string
  }

  let {
    value,
    max = 100,
    label = 'Progreso',
    class: className = ''
  }: Props = $props()

  let clamped = $derived(Math.max(0, Math.min(max, value)))
  let ratio = $derived(max > 0 ? clamped / max : 0)
</script>

<BitsProgress.Root
  value={clamped}
  {max}
  aria-label={label}
  class={cn(
    'relative h-2 w-full overflow-hidden rounded-full bg-[var(--studio-raised)]',
    className
  )}
>
  <div
    class="h-full w-full origin-left rounded-full bg-[var(--studio-accent)] transition-transform duration-150 ease-out"
    style:transform={`scaleX(${ratio})`}
  ></div>
</BitsProgress.Root>
