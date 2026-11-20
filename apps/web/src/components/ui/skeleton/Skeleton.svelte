<script lang="ts">
  import { cn } from '@/helpers/cn'

  interface Props {
    class?: string
  }

  let { class: className = '' }: Props = $props()
</script>

<div
  class={cn('rounded-lg bg-[var(--studio-raised)] opacity-70', className)}
  aria-hidden="true"
></div>
