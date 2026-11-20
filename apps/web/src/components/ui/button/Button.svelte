<script lang="ts">
  import type { Snippet } from 'svelte'
  import type { HTMLButtonAttributes } from 'svelte/elements'

  import { type VariantProps, tv } from 'tailwind-variants'

  import { cn } from '@/helpers/cn'

  const buttonVariants = tv({
    base: 'interactive-lift inline-flex min-h-[40px] cursor-pointer items-center justify-center gap-2 rounded-lg border font-medium whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-50',
    variants: {
      variant: {
        primary:
          'border-transparent bg-[var(--studio-accent)] text-[var(--studio-on-accent)] hover:bg-[var(--studio-accent-hover)]',
        brand:
          'border-transparent bg-[#3156d3] text-white hover:bg-[#2643a8]',
        outline:
          'border-[var(--studio-border)] bg-transparent text-[var(--studio-text)] hover:border-[var(--studio-accent)]',
        subtle:
          'border-[var(--studio-border)] bg-[var(--studio-raised)] text-[var(--studio-text)] hover:border-[var(--studio-accent)]',
        ghost:
          'border-transparent bg-transparent text-[var(--studio-muted)] hover:bg-[var(--studio-raised)] hover:text-[var(--studio-text)]',
        danger:
          'border-[var(--badge-error-border)] bg-[var(--badge-error-bg)] text-[var(--badge-error-text)] hover:opacity-90'
      },
      size: {
        sm: 'button-sm min-h-[36px] px-3 py-1.5',
        md: 'button-sm min-h-[40px] px-4 py-2',
        lg: 'button-md min-h-[44px] px-5 py-2.5',
        icon: 'size-10 p-0'
      }
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md'
    }
  })

  type Props = HTMLButtonAttributes &
    VariantProps<typeof buttonVariants> & {
      children?: Snippet
    }

  let {
    variant = 'primary',
    size = 'md',
    type = 'button',
    class: className = '',
    children,
    ...rest
  }: Props = $props()
</script>

<button
  {type}
  class={cn(buttonVariants({ variant, size }), className)}
  {...rest}
>
  {#if children}
    {@render children()}
  {/if}
</button>
