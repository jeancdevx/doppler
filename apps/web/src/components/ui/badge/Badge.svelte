<script lang="ts">
  import type { Snippet } from 'svelte'

  import { type VariantProps, tv } from 'tailwind-variants'

  import { cn } from '@/helpers/cn'

  const badgeVariants = tv({
    base: 'caption-4 inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 whitespace-nowrap font-mono',
    variants: {
      tone: {
        neutral:
          'border-[var(--studio-border)] bg-[var(--studio-panel)] text-[var(--studio-muted)]',
        ok: 'border-[var(--badge-ok-border)] bg-[var(--badge-ok-bg)] text-[var(--badge-ok-text)]',
        target:
          'border-[var(--badge-target-border)] bg-[var(--badge-target-bg)] text-[var(--badge-target-text)]',
        info: 'border-[var(--badge-info-border)] bg-[var(--badge-info-bg)] text-[var(--badge-info-text)]',
        error:
          'border-[var(--badge-error-border)] bg-[var(--badge-error-bg)] text-[var(--badge-error-text)]'
      }
    },
    defaultVariants: {
      tone: 'neutral'
    }
  })

  type Props = VariantProps<typeof badgeVariants> & {
    dot?: boolean
    class?: string
    children?: Snippet
  }

  let { tone = 'neutral', dot = false, class: className = '', children }: Props = $props()
</script>

<span class={cn(badgeVariants({ tone }), className)}>
  {#if dot}
    <span class="size-1.5 shrink-0 rounded-full bg-current" aria-hidden="true"></span>
  {/if}
  {#if children}
    {@render children()}
  {/if}
</span>
